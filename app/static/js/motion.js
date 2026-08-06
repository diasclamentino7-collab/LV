/*
 * LV Motion System
 *
 * Dependency-free, progressive and data-driven. The public API is exposed as
 * window.LVMotion and the engine initializes automatically when loaded.
 *
 * Individual live updates:
 *   LVMotion.update(elementOrSelector, realValue, { type: "number" });
 *   LVMotion.update(elementOrSelector, realPercent, { type: "progress" });
 *   document.dispatchEvent(new CustomEvent("lv:motion:update", {
 *     detail: { target: "#budget-total", type: "number", value: 12500 }
 *   }));
 */

(function () {
  "use strict";

  var doc = document;
  var rootElement = doc.documentElement;
  var reduceQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  var finePointerQuery = window.matchMedia(
    "(hover: hover) and (pointer: fine)"
  );
  var coarsePointerQuery = window.matchMedia("(pointer: coarse)");

  var VALID_MODES = ["full", "reduced", "none"];
  var AUTO = {
    pages: ".content,.auth-page",
    cards: [
      ".countdown",
      ".metric-card",
      ".moodboard-item",
      ".budget-summary",
      ".guest-card",
      ".supplier-card.is-featured",
    ].join(","),
    numbers: [
      "[data-countdown-days]",
      "[data-countdown-hours]",
      "[data-countdown-minutes]",
      "[data-countdown-seconds]",
      ".metric-card > div > strong",
      ".budget-total > strong",
    ].join(","),
    progress: ".progress-fill",
    lists: [
      ".metric-grid",
      ".activity-list",
      ".record-list",
      ".moodboard-grid",
    ].join(","),
    tilt: [
      ".countdown",
      ".metric-card",
      ".moodboard-item",
      ".budget-summary",
      ".guest-card",
      ".supplier-card.is-featured",
    ].join(","),
    buttons: [
      ".primary-button",
      ".secondary-button",
      ".text-button",
      ".card-link",
      ".icon-button",
      ".quiet-button",
      ".record-actions button",
      ".moodboard-actions button",
    ].join(","),
    parallax: ".countdown .flower-mark",
  };

  var SELECTORS = {
    page: "[data-motion-page],.motion-page",
    card: "[data-motion-card],.motion-card",
    number: "[data-motion-number],.motion-number",
    progress: "[data-motion-progress],.motion-progress",
    list: "[data-motion-list],.motion-list",
    modal: "[data-motion-modal],.motion-modal",
    toast: "[data-motion-toast],.motion-toast",
    tilt: "[data-motion-tilt],.motion-tilt",
    parallax: "[data-motion-parallax],.motion-parallax",
    button: "[data-motion-button],.motion-button",
    chartLine: "[data-motion-chart-line],.motion-chart-line",
    chartSegment: "[data-motion-chart-segment],.motion-chart-segment",
  };

  var state = {
    initialized: false,
    destroyed: false,
    requestedMode: "full",
    effectiveMode: "full",
    revealObserver: null,
    valueObserver: null,
    parallaxObserver: null,
    mutationObserver: null,
    observedReveal: new WeakSet(),
    observedValue: new WeakSet(),
    numberStates: new WeakMap(),
    progressStates: new WeakMap(),
    tiltStates: new WeakMap(),
    tilts: new Set(),
    parallaxStates: new WeakMap(),
    parallaxes: new Set(),
    modalTriggers: new WeakMap(),
    modalIsolation: new WeakMap(),
    modalStack: [],
    formBaselines: new WeakMap(),
    highlightTimers: new WeakMap(),
    toastRegion: null,
    parallaxFrame: 0,
    navigationApproved: false,
    systemPreferenceChanged: null,
    pointerCapabilityChanged: null,
    refreshRequested: null,
    highlightRequested: null,
    toastRequested: null,
    buttonSuccessRequested: null,
  };

  function isElement(value) {
    return value && value.nodeType === Node.ELEMENT_NODE;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), maximum);
  }

  function finiteNumber(value, fallback) {
    if (value === null || value === undefined || value === "") {
      return fallback;
    }
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function cssMilliseconds(variableName, fallback) {
    var raw = window
      .getComputedStyle(rootElement)
      .getPropertyValue(variableName)
      .trim();
    if (!raw) {
      return fallback;
    }
    if (raw.endsWith("ms")) {
      return finiteNumber(raw.slice(0, -2), fallback);
    }
    if (raw.endsWith("s")) {
      return finiteNumber(raw.slice(0, -1), fallback / 1000) * 1000;
    }
    return fallback;
  }

  function easeOutCubic(progress) {
    return 1 - Math.pow(1 - progress, 3);
  }

  function normalizeMode(value) {
    var normalized = String(value || "").toLowerCase().trim();
    return VALID_MODES.indexOf(normalized) >= 0 ? normalized : "full";
  }

  function modeFromDocument() {
    var htmlMode = rootElement.getAttribute("data-motion");
    var bodyMode = doc.body && doc.body.getAttribute("data-motion");
    var savedMode = "";
    if (!htmlMode && !bodyMode) {
      try {
        savedMode = window.localStorage.getItem("lv-motion-mode") || "";
      } catch (_error) {
        // Private browsing can deny storage; full motion remains the fallback.
      }
    }
    return normalizeMode(htmlMode || bodyMode || savedMode || "full");
  }

  function effectiveMode(requested) {
    if (requested === "none") {
      return "none";
    }
    if (requested === "reduced" || reduceQuery.matches) {
      return "reduced";
    }
    return "full";
  }

  function emit(name, detail, target) {
    (target || doc).dispatchEvent(
      new CustomEvent(name, {
        bubbles: target ? true : false,
        detail: detail || {},
      })
    );
  }

  function setMode(mode, options) {
    var requested = normalizeMode(mode);
    var settings = options || {};
    state.requestedMode = requested;
    state.effectiveMode = effectiveMode(requested);
    rootElement.setAttribute("data-motion", requested);
    rootElement.setAttribute("data-motion-effective", state.effectiveMode);

    if (settings.persist === true) {
      try {
        window.localStorage.setItem("lv-motion-mode", requested);
      } catch (_error) {
        // Storage is optional; server-rendered data-motion remains authoritative.
      }
    }

    if (state.effectiveMode !== "full") {
      resetAllTilts();
      resetParallax();
    } else {
      scheduleParallax();
    }

    if (state.effectiveMode === "none") {
      revealEverything();
      finishRunningValues();
    }

    emit("lv:motion:mode-changed", {
      requested: requested,
      effective: state.effectiveMode,
    });
    return state.effectiveMode;
  }

  function getMode() {
    return {
      requested: state.requestedMode,
      effective: state.effectiveMode,
      systemReduced: reduceQuery.matches,
    };
  }

  function elementsWithin(scope, selector) {
    var results = [];
    if (isElement(scope) && scope.matches(selector)) {
      results.push(scope);
    }
    if (scope && typeof scope.querySelectorAll === "function") {
      results = results.concat(Array.from(scope.querySelectorAll(selector)));
    }
    return results;
  }

  function resolveTargets(target) {
    if (!target) {
      return [];
    }
    if (typeof target === "string") {
      try {
        return Array.from(doc.querySelectorAll(target));
      } catch (_error) {
        return [];
      }
    }
    if (isElement(target)) {
      return [target];
    }
    if (typeof target.length === "number") {
      return Array.from(target).filter(isElement);
    }
    return [];
  }

  function isTrackedForm(form) {
    if (!form || form.nodeName !== "FORM") {
      return false;
    }
    var method = String(form.getAttribute("method") || "get").toLowerCase();
    if (method === "get" || form.getAttribute("data-dirty-check") === "false") {
      return false;
    }
    return Boolean(
      form.querySelector(
        [
          "input:not([type='hidden']):not([type='submit']):not([type='button'])",
          "select",
          "textarea",
        ].join(",")
      )
    );
  }

  function formSignature(form) {
    return Array.from(form.elements)
      .filter(function (control) {
        if (!control.name || control.disabled) {
          return false;
        }
        return ["button", "submit", "reset"].indexOf(control.type) < 0;
      })
      .map(function (control) {
        var value = control.value;
        if (control.type === "checkbox" || control.type === "radio") {
          value = control.checked ? "checked:" + control.value : "unchecked";
        } else if (control.type === "file") {
          value = Array.from(control.files || [])
            .map(function (file) {
              return [file.name, file.size, file.lastModified].join(":");
            })
            .join("|");
        } else if (control.multiple && control.options) {
          value = Array.from(control.selectedOptions || [])
            .map(function (option) {
              return option.value;
            })
            .join("|");
        }
        return [control.name, control.type, value].join("\u001f");
      })
      .join("\u001e");
  }

  function registerDirtyForms(scope) {
    elementsWithin(scope, "form").forEach(function (form) {
      if (!isTrackedForm(form) || state.formBaselines.has(form)) {
        return;
      }
      state.formBaselines.set(form, formSignature(form));
    });
  }

  function updateFormDirtyState(form) {
    if (!isTrackedForm(form)) {
      return;
    }
    if (!state.formBaselines.has(form)) {
      state.formBaselines.set(form, formSignature(form));
      return;
    }
    var dirty = state.formBaselines.get(form) !== formSignature(form);
    form.toggleAttribute("data-motion-dirty", dirty);
  }

  function hasDirtyForms() {
    return Boolean(doc.querySelector("form[data-motion-dirty]"));
  }

  function approveDirtyNavigation(destination) {
    if (!hasDirtyForms()) {
      return true;
    }
    var approved = window.confirm(
      "Existem alterações por guardar. Queres sair desta página sem as guardar?"
    );
    if (!approved) {
      return false;
    }
    state.navigationApproved = true;
    emit("lv:motion:navigation-confirmed", {
      destination: destination,
    });
    return true;
  }

  function normalizedPath(pathname) {
    var clean = String(pathname || "/").replace(/\/+$/, "");
    return clean || "/";
  }

  function isDashboardLocation(locationLike) {
    var path = normalizedPath(locationLike.pathname);
    return path === "/" || path === "/dashboard";
  }

  function routeEntryKind() {
    return rootElement.getAttribute("data-route-entry") || "";
  }

  function clearRouteExit() {
    state.navigationApproved = false;
  }

  function finishRouteArrival() {
    var entry = routeEntryKind();
    if (!entry) {
      return;
    }
    var mode = state.effectiveMode;
    var isHome = entry === "home" && isDashboardLocation(window.location);
    if (isHome) {
      var main = doc.querySelector("#main-content");
      if (main) {
        main.focus({ preventScroll: true });
      }
    }
    var duration =
      mode === "none" ? 0 : mode === "reduced" ? 90 : isHome ? 220 : 140;
    window.setTimeout(function () {
      rootElement.removeAttribute("data-route-entry");
      emit("lv:motion:route-entered", {
        kind: entry,
        destination: window.location.href,
      });
    }, duration);
  }

  function storeRouteEntry(kind) {
    try {
      window.sessionStorage.setItem(
        "lv-route-transition",
        JSON.stringify({ kind: kind, at: Date.now() })
      );
    } catch (_error) {
      // The visual transition is optional if private storage is unavailable.
    }
  }

  function navigate(destination, options) {
    var settings = options || {};
    var url;
    try {
      url = new URL(destination, window.location.href);
    } catch (_error) {
      return false;
    }
    if (
      url.origin !== window.location.origin ||
      (url.protocol !== "http:" && url.protocol !== "https:")
    ) {
      return false;
    }
    if (
      settings.confirmDirty !== false &&
      !approveDirtyNavigation(url.href)
    ) {
      return false;
    }

    var kind = settings.kind === "home" ? "home" : "subtle";
    storeRouteEntry(kind);
    emit("lv:motion:route-leaving", {
      kind: kind,
      destination: url.href,
    });
    window.location.assign(url.href);
    return true;
  }

  function pulseHomeBrand(brand) {
    if (!brand || state.effectiveMode === "none") {
      return;
    }
    brand.classList.remove("is-home-brand-pulse");
    void brand.offsetWidth;
    brand.classList.add("is-home-brand-pulse");
    window.setTimeout(function () {
      brand.classList.remove("is-home-brand-pulse");
    }, state.effectiveMode === "reduced" ? 120 : 260);
  }

  function isSkippedRouteLink(anchor, event) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      anchor.hasAttribute("download")
    ) {
      return true;
    }
    var target = String(anchor.getAttribute("target") || "").toLowerCase();
    if (target && target !== "_self") {
      return true;
    }
    var rawHref = String(anchor.getAttribute("href") || "").trim();
    if (
      !rawHref ||
      rawHref.charAt(0) === "#" ||
      /^(mailto|tel|javascript):/i.test(rawHref)
    ) {
      return true;
    }
    return (
      /\.pdf(?:$|[?#])/i.test(rawHref) ||
      anchor.hasAttribute("data-export") ||
      anchor.getAttribute("rel") === "external"
    );
  }

  function handleRouteLinkClick(event) {
    var anchor = event.target.closest(
      "a[data-motion-home],a.nav-item,.breadcrumb a"
    );
    if (!anchor || isSkippedRouteLink(anchor, event)) {
      return false;
    }
    var url;
    try {
      url = new URL(anchor.href, window.location.href);
    } catch (_error) {
      return false;
    }
    if (
      url.origin !== window.location.origin ||
      (url.protocol !== "http:" && url.protocol !== "https:")
    ) {
      return false;
    }

    var isHomeBrand = anchor.hasAttribute("data-motion-home");
    if (isHomeBrand && isDashboardLocation(window.location)) {
      event.preventDefault();
      pulseHomeBrand(anchor);
      return true;
    }

    var sameLocation =
      normalizedPath(url.pathname) ===
        normalizedPath(window.location.pathname) &&
      url.search === window.location.search &&
      url.hash === window.location.hash;
    if (sameLocation) {
      event.preventDefault();
      highlight(anchor, { duration: 260 });
      return true;
    }

    if (!approveDirtyNavigation(url.href)) {
      event.preventDefault();
      anchor.focus();
      return true;
    }
    event.preventDefault();
    navigate(url.href, {
      kind: isHomeBrand ? "home" : "subtle",
      confirmDirty: false,
    });
    return true;
  }

  function autoEnhance(scope) {
    elementsWithin(scope, AUTO.pages).forEach(function (element) {
      element.classList.add("motion-page");
    });
    elementsWithin(scope, AUTO.cards).forEach(function (element) {
      element.classList.add("motion-card");
    });
    elementsWithin(scope, AUTO.numbers).forEach(function (element) {
      element.classList.add("motion-number");
    });
    elementsWithin(scope, AUTO.progress).forEach(function (element) {
      element.classList.add("motion-progress");
    });
    elementsWithin(scope, AUTO.lists).forEach(function (element) {
      element.classList.add("motion-list");
    });
    if (tiltAllowed()) {
      // Touch devices (or reduced/no-motion preference) never render tilt;
      // skip even applying the 3D-transform class (perspective/preserve-3d
      // forces its own compositor layer per element, which is real
      // GPU/memory cost on weaker phones for no visible benefit there).
      elementsWithin(scope, AUTO.tilt).forEach(function (element) {
        element.classList.add("motion-tilt");
      });
    }
    elementsWithin(scope, AUTO.buttons).forEach(function (element) {
      element.classList.add("motion-button");
    });
    if (parallaxAllowed()) {
      elementsWithin(scope, AUTO.parallax).forEach(function (element) {
        element.classList.add("motion-parallax");
        if (!element.hasAttribute("data-motion-range")) {
          element.setAttribute("data-motion-range", "7");
        }
      });
    }

    elementsWithin(scope, ".moodboard-item img").forEach(function (image) {
      if (!image.hasAttribute("loading")) {
        image.setAttribute("loading", "lazy");
      }
      if (!image.hasAttribute("decoding")) {
        image.setAttribute("decoding", "async");
      }
    });
  }

  function reveal(element) {
    if (!isElement(element)) {
      return;
    }
    element.classList.remove("is-motion-pending");
    element.classList.add("is-motion-visible");
    if (state.revealObserver) {
      state.revealObserver.unobserve(element);
    }
    emit("lv:motion:revealed", { element: element }, element);
  }

  function prepareReveal(element, index) {
    if (!isElement(element) || state.observedReveal.has(element)) {
      return;
    }
    state.observedReveal.add(element);
    element.classList.add("motion-reveal", "is-motion-pending");
    if (Number.isFinite(index)) {
      element.style.setProperty("--motion-index", String(index));
      element.style.setProperty(
        "--motion-delay",
        "calc(" + index + " * var(--motion-stagger))"
      );
    }

    if (state.effectiveMode === "none" || !state.revealObserver) {
      window.requestAnimationFrame(function () {
        reveal(element);
      });
      return;
    }
    state.revealObserver.observe(element);
  }

  function prepareList(list) {
    var children = Array.from(list.children).filter(isElement);
    children.forEach(function (child, index) {
      child.classList.add("motion-list-item");
      prepareReveal(child, index);
    });
  }

  function revealEverything() {
    doc
      .querySelectorAll(".motion-reveal.is-motion-pending")
      .forEach(function (element) {
        reveal(element);
      });
  }

  function findNumberNode(element) {
    var explicit = element.querySelector("[data-motion-number-value]");
    if (explicit) {
      return findNumberNode(explicit);
    }
    var childNodes = Array.from(element.childNodes);
    var directText = childNodes.find(function (node) {
      return node.nodeType === Node.TEXT_NODE && /\d/.test(node.nodeValue || "");
    });
    if (directText) {
      return directText;
    }
    if (element.children.length === 0) {
      return element;
    }
    return null;
  }

  function nodeText(node) {
    return node.nodeType === Node.TEXT_NODE
      ? node.nodeValue || ""
      : node.textContent || "";
  }

  function writeNodeText(node, value) {
    if (node.nodeType === Node.TEXT_NODE) {
      node.nodeValue = value;
    } else {
      node.textContent = value;
    }
  }

  function numberTemplate(rawText, element) {
    var raw = String(rawText || "");
    var match = raw.match(/[-+]?\d[\d\s\u00a0\u202f.,'’]*/);
    if (!match) {
      return null;
    }

    var originalToken = match[0].replace(/[\s\u00a0\u202f.,'’]+$/, "");
    if (!originalToken) {
      return null;
    }
    var compact = originalToken.replace(/[\s\u00a0\u202f'’]/g, "");
    var comma = compact.lastIndexOf(",");
    var dot = compact.lastIndexOf(".");
    var decimalSeparator = "";
    var explicitDecimals = element.getAttribute("data-motion-decimals");
    var decimalCount = explicitDecimals === null
      ? null
      : clamp(Math.round(finiteNumber(explicitDecimals, 0)), 0, 8);

    if (comma >= 0 && dot >= 0) {
      decimalSeparator = comma > dot ? "," : ".";
    } else if (comma >= 0 || dot >= 0) {
      var candidate = comma >= 0 ? "," : ".";
      var separatorIndex = compact.lastIndexOf(candidate);
      var places = compact.length - separatorIndex - 1;
      var occurrences = compact.split(candidate).length - 1;
      if (
        decimalCount !== null ||
        (occurrences === 1 && places > 0 && places <= 2)
      ) {
        decimalSeparator = candidate;
      }
    }

    if (decimalCount === null) {
      decimalCount = decimalSeparator
        ? compact.length - compact.lastIndexOf(decimalSeparator) - 1
        : 0;
    }

    var normalized = compact;
    if (decimalSeparator) {
      var decimalIndex = normalized.lastIndexOf(decimalSeparator);
      normalized =
        normalized.slice(0, decimalIndex).replace(/[.,]/g, "") +
        "." +
        normalized.slice(decimalIndex + 1).replace(/[.,]/g, "");
    } else {
      normalized = normalized.replace(/[.,]/g, "");
    }

    var value = Number(normalized);
    if (!Number.isFinite(value)) {
      return null;
    }

    var integerPart = originalToken
      .replace(/^[-+]/, "")
      .split(decimalSeparator || "\u0000")[0]
      .replace(/\D/g, "");
    var minimumIntegerDigits =
      integerPart.length > 1 && integerPart.charAt(0) === "0"
        ? clamp(integerPart.length, 1, 21)
        : 1;
    var hasGrouping =
      /[\s\u00a0\u202f'’]/.test(originalToken) ||
      (!decimalSeparator && /[.,]/.test(originalToken)) ||
      (decimalSeparator === "," && originalToken.indexOf(".") >= 0) ||
      (decimalSeparator === "." && originalToken.indexOf(",") >= 0);

    return {
      value: value,
      prefix: raw.slice(0, match.index),
      suffix: raw.slice(match.index + originalToken.length),
      decimals: decimalCount,
      minimumIntegerDigits: minimumIntegerDigits,
      useGrouping: hasGrouping,
      locale:
        element.getAttribute("data-motion-locale") ||
        rootElement.lang ||
        "pt-PT",
    };
  }

  function formatNumber(value, template) {
    var formatted;
    try {
      formatted = new Intl.NumberFormat(template.locale, {
        minimumFractionDigits: template.decimals,
        maximumFractionDigits: template.decimals,
        minimumIntegerDigits: template.minimumIntegerDigits,
        useGrouping: template.useGrouping,
      }).format(value);
    } catch (_error) {
      formatted = Number(value).toFixed(template.decimals);
    }
    return template.prefix + formatted + template.suffix;
  }

  function prepareNumber(element) {
    if (state.numberStates.has(element)) {
      return state.numberStates.get(element);
    }
    var node = findNumberNode(element);
    if (!node) {
      return null;
    }
    var displayTemplate = numberTemplate(nodeText(node), element);
    var dataValue = element.getAttribute("data-motion-value");
    var valueTemplate =
      dataValue !== null
        ? numberTemplate(dataValue, element) || displayTemplate
        : displayTemplate;
    if (!displayTemplate && !valueTemplate) {
      return null;
    }
    var template = displayTemplate || valueTemplate;
    var numberState = {
      node: node,
      template: template,
      target: valueTemplate.value,
      current: valueTemplate.value,
      started: false,
      frame: 0,
    };
    state.numberStates.set(element, numberState);
    if (state.valueObserver && state.effectiveMode !== "none") {
      state.valueObserver.observe(element);
      state.observedValue.add(element);
    } else {
      animateNumber(element, template.value, { initial: true });
    }
    return numberState;
  }

  function renderNumber(element, numberState, value) {
    numberState.current = value;
    writeNodeText(
      numberState.node,
      formatNumber(value, numberState.template)
    );
    element.setAttribute("data-motion-current-value", String(value));
  }

  function animateNumber(element, nextValue, options) {
    if (!isElement(element)) {
      return false;
    }
    var settings = options || {};
    var numberState =
      state.numberStates.get(element) || prepareNumber(element);
    if (!numberState) {
      return false;
    }

    var parsedTarget;
    if (typeof nextValue === "number") {
      parsedTarget = nextValue;
    } else {
      var nextTemplate = numberTemplate(String(nextValue), element);
      if (!nextTemplate) {
        return false;
      }
      parsedTarget = nextTemplate.value;
      if (settings.preserveFormat !== true) {
        numberState.template = nextTemplate;
      }
    }
    if (!Number.isFinite(parsedTarget)) {
      return false;
    }

    if (numberState.frame) {
      window.cancelAnimationFrame(numberState.frame);
      numberState.frame = 0;
    }

    var initial = settings.initial === true && !numberState.started;
    var explicitStart = finiteNumber(
      element.getAttribute("data-motion-start"),
      NaN
    );
    var from = initial
      ? Number.isFinite(explicitStart)
        ? explicitStart
        : 0
      : numberState.current;
    var target = parsedTarget;
    numberState.target = target;
    numberState.started = true;

    var duration = clamp(
      finiteNumber(
        settings.duration,
        cssMilliseconds("--motion-duration-number", 680)
      ),
      0,
      2400
    );
    if (
      state.effectiveMode === "none" ||
      doc.hidden ||
      duration <= 1 ||
      Math.abs(target - from) < Number.EPSILON
    ) {
      renderNumber(element, numberState, target);
      element.classList.remove("is-motion-updating");
      emit(
        "lv:motion:number-complete",
        { element: element, value: target },
        element
      );
      return true;
    }

    element.classList.add("is-motion-updating");
    var startedAt = window.performance.now();

    function step(now) {
      var elapsed = clamp((now - startedAt) / duration, 0, 1);
      var displayed = from + (target - from) * easeOutCubic(elapsed);
      renderNumber(element, numberState, displayed);
      if (elapsed < 1) {
        numberState.frame = window.requestAnimationFrame(step);
        return;
      }
      numberState.frame = 0;
      renderNumber(element, numberState, target);
      element.classList.remove("is-motion-updating");
      emit(
        "lv:motion:number-complete",
        { element: element, value: target },
        element
      );
    }

    numberState.frame = window.requestAnimationFrame(step);
    return true;
  }

  function readProgress(element) {
    var values = [
      element.getAttribute("data-motion-value"),
      element.getAttribute("aria-valuenow"),
      element.style.width,
    ];
    for (var index = 0; index < values.length; index += 1) {
      if (values[index] !== null && values[index] !== "") {
        var parsed = parseFloat(values[index]);
        if (Number.isFinite(parsed)) {
          return clamp(parsed, 0, 100);
        }
      }
    }
    var parentWidth = element.parentElement
      ? element.parentElement.getBoundingClientRect().width
      : 0;
    var ownWidth = element.getBoundingClientRect().width;
    return parentWidth > 0 ? clamp((ownWidth / parentWidth) * 100, 0, 100) : 0;
  }

  function prepareProgress(element) {
    if (state.progressStates.has(element)) {
      return state.progressStates.get(element);
    }
    var target = readProgress(element);
    var progressState = {
      target: target,
      current: target,
      started: false,
      frame: 0,
      originalWidth: element.style.width,
    };
    state.progressStates.set(element, progressState);
    element.setAttribute("role", element.getAttribute("role") || "progressbar");
    element.setAttribute("aria-valuemin", "0");
    element.setAttribute("aria-valuemax", "100");
    element.setAttribute("aria-valuenow", String(target));
    if (state.valueObserver && state.effectiveMode !== "none") {
      state.valueObserver.observe(element);
      state.observedValue.add(element);
    } else {
      animateProgress(element, target, { initial: true });
    }
    return progressState;
  }

  function renderProgress(element, progressState, value) {
    var normalized = clamp(value, 0, 100);
    progressState.current = normalized;
    element.style.setProperty(
      "--motion-progress-current",
      String(normalized / 100)
    );
  }

  function animateProgress(element, nextValue, options) {
    if (!isElement(element)) {
      return false;
    }
    var settings = options || {};
    var progressState =
      state.progressStates.get(element) || prepareProgress(element);
    if (!progressState) {
      return false;
    }
    var target = clamp(finiteNumber(nextValue, NaN), 0, 100);
    if (!Number.isFinite(target)) {
      return false;
    }
    if (progressState.frame) {
      window.cancelAnimationFrame(progressState.frame);
      progressState.frame = 0;
    }

    var initial = settings.initial === true && !progressState.started;
    var from = initial ? 0 : progressState.current;
    progressState.started = true;
    progressState.target = target;
    element.setAttribute("aria-valuenow", String(target));
    element.setAttribute("data-motion-current-value", String(target));

    var duration = clamp(
      finiteNumber(
        settings.duration,
        cssMilliseconds("--motion-duration-slow", 520)
      ),
      0,
      2400
    );
    if (
      state.effectiveMode === "none" ||
      doc.hidden ||
      duration <= 1 ||
      Math.abs(target - from) < Number.EPSILON
    ) {
      renderProgress(element, progressState, target);
      element.classList.remove("is-motion-updating");
      emit(
        "lv:motion:progress-complete",
        { element: element, value: target },
        element
      );
      return true;
    }

    element.classList.add("is-motion-updating");
    var startedAt = window.performance.now();

    function step(now) {
      var elapsed = clamp((now - startedAt) / duration, 0, 1);
      renderProgress(
        element,
        progressState,
        from + (target - from) * easeOutCubic(elapsed)
      );
      if (elapsed < 1) {
        progressState.frame = window.requestAnimationFrame(step);
        return;
      }
      progressState.frame = 0;
      renderProgress(element, progressState, target);
      element.classList.remove("is-motion-updating");
      emit(
        "lv:motion:progress-complete",
        { element: element, value: target },
        element
      );
    }

    progressState.frame = window.requestAnimationFrame(step);
    return true;
  }

  function prepareChartLine(path) {
    if (typeof path.getTotalLength !== "function") {
      return;
    }
    try {
      var length = path.getTotalLength();
      if (Number.isFinite(length) && length > 0) {
        path.style.setProperty("--motion-path-length", String(length));
        path.classList.add("motion-chart-line");
        prepareReveal(path);
      }
    } catch (_error) {
      // A detached or invalid SVG path simply remains static.
    }
  }

  function prepareChartSegment(segment, index) {
    segment.classList.add("motion-chart-segment");
    segment.style.setProperty("--motion-index", String(index || 0));
    prepareReveal(segment, index);
  }

  function onValueIntersection(entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) {
        return;
      }
      var element = entry.target;
      if (element.matches(SELECTORS.number)) {
        var numberState = state.numberStates.get(element);
        if (numberState && !numberState.started) {
          animateNumber(element, numberState.target, { initial: true });
        }
      }
      if (element.matches(SELECTORS.progress)) {
        var progressState = state.progressStates.get(element);
        if (progressState && !progressState.started) {
          animateProgress(element, progressState.target, { initial: true });
        }
      }
      state.valueObserver.unobserve(element);
    });
  }

  function prepareTilt(element) {
    if (state.tiltStates.has(element) || !tiltAllowed()) {
      // Touch devices (and reduced/no-motion preference) never render
      // tilt; skip the 3D transform + listeners entirely instead of
      // setting them up and immediately no-op'ing every frame.
      return;
    }
    element.classList.add("motion-tilt");
    var tiltState = {
      frame: 0,
      x: 0,
      y: 0,
      touchTimer: 0,
      move: null,
      leave: null,
      down: null,
      up: null,
    };

    function renderTilt() {
      tiltState.frame = 0;
      if (
        state.effectiveMode !== "full" ||
        !finePointerQuery.matches ||
        doc.hidden
      ) {
        resetTilt(element);
        return;
      }
      var maximum = clamp(
        finiteNumber(
          element.getAttribute("data-motion-tilt"),
          finiteNumber(
            window
              .getComputedStyle(rootElement)
              .getPropertyValue("--motion-tilt-max"),
            3
          )
        ),
        0,
        3
      );
      var rotateX = -tiltState.y * maximum;
      var rotateY = tiltState.x * maximum;
      element.style.setProperty("--motion-rotate-x", rotateX.toFixed(3) + "deg");
      element.style.setProperty("--motion-rotate-y", rotateY.toFixed(3) + "deg");
      element.classList.add("is-motion-active");
    }

    tiltState.move = function (event) {
      if (
        event.pointerType === "touch" ||
        state.effectiveMode !== "full" ||
        !finePointerQuery.matches
      ) {
        return;
      }
      var bounds = element.getBoundingClientRect();
      if (!bounds.width || !bounds.height) {
        return;
      }
      tiltState.x = clamp(
        ((event.clientX - bounds.left) / bounds.width - 0.5) * 2,
        -1,
        1
      );
      tiltState.y = clamp(
        ((event.clientY - bounds.top) / bounds.height - 0.5) * 2,
        -1,
        1
      );
      if (!tiltState.frame) {
        tiltState.frame = window.requestAnimationFrame(renderTilt);
      }
    };
    tiltState.leave = function () {
      resetTilt(element);
    };
    tiltState.down = function (event) {
      if (event.pointerType === "touch" || coarsePointerQuery.matches) {
        window.clearTimeout(tiltState.touchTimer);
        element.classList.add("is-motion-pressed");
        tiltState.touchTimer = window.setTimeout(function () {
          element.classList.remove("is-motion-pressed");
        }, 180);
      }
    };
    tiltState.up = function () {
      window.clearTimeout(tiltState.touchTimer);
      element.classList.remove("is-motion-pressed");
    };

    element.addEventListener("pointermove", tiltState.move, { passive: true });
    element.addEventListener("pointerleave", tiltState.leave, { passive: true });
    element.addEventListener("pointercancel", tiltState.leave, { passive: true });
    element.addEventListener("pointerdown", tiltState.down, { passive: true });
    element.addEventListener("pointerup", tiltState.up, { passive: true });
    state.tiltStates.set(element, tiltState);
    state.tilts.add(element);
  }

  function resetTilt(element) {
    var tiltState = state.tiltStates.get(element);
    if (tiltState && tiltState.frame) {
      window.cancelAnimationFrame(tiltState.frame);
      tiltState.frame = 0;
    }
    element.style.setProperty("--motion-rotate-x", "0deg");
    element.style.setProperty("--motion-rotate-y", "0deg");
    element.classList.remove("is-motion-active", "is-motion-pressed");
  }

  function resetAllTilts() {
    state.tilts.forEach(resetTilt);
  }

  function lowPerformanceDevice() {
    var connection =
      navigator.connection ||
      navigator.mozConnection ||
      navigator.webkitConnection;
    var saveData = Boolean(connection && connection.saveData);
    var fewCores =
      Number.isFinite(navigator.hardwareConcurrency) &&
      navigator.hardwareConcurrency <= 4;
    var lowMemory =
      Number.isFinite(navigator.deviceMemory) && navigator.deviceMemory <= 4;
    return saveData || fewCores || lowMemory || coarsePointerQuery.matches;
  }

  function tiltAllowed() {
    return state.effectiveMode === "full" && finePointerQuery.matches;
  }

  function parallaxAllowed() {
    return state.effectiveMode === "full" && !lowPerformanceDevice();
  }

  function prepareParallax(element) {
    if (state.parallaxStates.has(element)) {
      return;
    }
    var parallaxState = { visible: true };
    state.parallaxStates.set(element, parallaxState);
    state.parallaxes.add(element);
    element.classList.add("motion-parallax");
    if (state.parallaxObserver) {
      parallaxState.visible = false;
      state.parallaxObserver.observe(element);
    }
  }

  function updateParallax() {
    state.parallaxFrame = 0;
    if (
      state.effectiveMode !== "full" ||
      lowPerformanceDevice() ||
      doc.hidden
    ) {
      resetParallax();
      return;
    }
    var viewportHeight = window.innerHeight || 1;
    state.parallaxes.forEach(function (element) {
      var parallaxState = state.parallaxStates.get(element);
      if (!parallaxState || !parallaxState.visible) {
        return;
      }
      var bounds = element.getBoundingClientRect();
      var center = bounds.top + bounds.height / 2;
      var normalized = clamp(
        (center - viewportHeight / 2) / viewportHeight,
        -1,
        1
      );
      var range = clamp(
        finiteNumber(element.getAttribute("data-motion-range"), 10),
        0,
        14
      );
      var offset = -normalized * range;
      element.style.setProperty(
        "--motion-parallax-y",
        offset.toFixed(2) + "px"
      );
      element.classList.add("is-motion-active");
    });
  }

  function scheduleParallax() {
    if (!state.parallaxFrame) {
      state.parallaxFrame = window.requestAnimationFrame(updateParallax);
    }
  }

  function resetParallax() {
    if (state.parallaxFrame) {
      window.cancelAnimationFrame(state.parallaxFrame);
      state.parallaxFrame = 0;
    }
    state.parallaxes.forEach(function (element) {
      element.style.setProperty("--motion-parallax-x", "0px");
      element.style.setProperty("--motion-parallax-y", "0px");
      element.classList.remove("is-motion-active");
    });
  }

  function prepareModal(modal) {
    modal.classList.add("motion-modal");
    if (!modal.hasAttribute("role")) {
      modal.setAttribute("role", "dialog");
    }
    modal.setAttribute("aria-modal", "true");
    if (!modal.hasAttribute("open") && !modal.classList.contains("is-open")) {
      modal.setAttribute("aria-hidden", "true");
      if (modal.tagName !== "DIALOG") {
        modal.hidden = true;
      }
    }
  }

  function focusableElements(container) {
    return Array.from(
      container.querySelectorAll(
        [
          "a[href]",
          "button:not([disabled])",
          "input:not([disabled]):not([type='hidden'])",
          "select:not([disabled])",
          "textarea:not([disabled])",
          "[tabindex]:not([tabindex='-1'])",
        ].join(",")
      )
    ).filter(function (element) {
      return !element.hidden && element.getClientRects().length > 0;
    });
  }

  function isolateModal(modal) {
    if (modal.tagName === "DIALOG" || state.modalIsolation.has(modal)) {
      return;
    }
    var isolated = [];
    var branch = modal;
    var parent = branch.parentElement;
    while (parent) {
      Array.from(parent.children).forEach(function (sibling) {
        if (
          sibling === branch ||
          sibling.tagName === "SCRIPT" ||
          sibling.tagName === "STYLE"
        ) {
          return;
        }
        isolated.push({
          element: sibling,
          inert: sibling.inert,
          ariaHidden: sibling.getAttribute("aria-hidden"),
        });
        sibling.inert = true;
        sibling.setAttribute("aria-hidden", "true");
      });
      if (parent === doc.body) {
        break;
      }
      branch = parent;
      parent = parent.parentElement;
    }
    state.modalIsolation.set(modal, isolated);
  }

  function restoreModalIsolation(modal) {
    var isolated = state.modalIsolation.get(modal) || [];
    isolated.forEach(function (entry) {
      entry.element.inert = entry.inert;
      if (entry.ariaHidden === null) {
        entry.element.removeAttribute("aria-hidden");
      } else {
        entry.element.setAttribute("aria-hidden", entry.ariaHidden);
      }
    });
    state.modalIsolation.delete(modal);
  }

  function openModal(target, trigger) {
    var modal = resolveTargets(target)[0];
    if (!modal) {
      return false;
    }
    prepareModal(modal);
    state.modalTriggers.set(modal, trigger || doc.activeElement);
    if (state.modalStack.indexOf(modal) < 0) {
      state.modalStack.push(modal);
    }
    isolateModal(modal);
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    if (
      modal.tagName === "DIALOG" &&
      typeof modal.showModal === "function" &&
      !modal.open
    ) {
      modal.showModal();
    }
    window.requestAnimationFrame(function () {
      modal.classList.remove("is-closing");
      modal.classList.add("is-open");
      var focusable = focusableElements(modal);
      var focusTarget =
        modal.querySelector("[autofocus]") || focusable[0] || modal;
      if (focusTarget === modal && !modal.hasAttribute("tabindex")) {
        modal.setAttribute("tabindex", "-1");
      }
      focusTarget.focus({ preventScroll: true });
    });
    emit("lv:motion:modal-opened", { modal: modal }, modal);
    return true;
  }

  function closeModal(target, options) {
    var modal = resolveTargets(target)[0];
    if (!modal) {
      return false;
    }
    var settings = options || {};
    modal.classList.remove("is-open");
    modal.classList.add("is-closing");
    var duration =
      state.effectiveMode === "none"
        ? 0
        : cssMilliseconds("--motion-duration-normal", 260);

    window.setTimeout(function () {
      modal.classList.remove("is-closing");
      modal.setAttribute("aria-hidden", "true");
      if (
        modal.tagName === "DIALOG" &&
        typeof modal.close === "function" &&
        modal.open
      ) {
        modal.close(settings.returnValue || "");
      } else {
        modal.hidden = true;
      }
      state.modalStack = state.modalStack.filter(function (entry) {
        return entry !== modal;
      });
      restoreModalIsolation(modal);
      var trigger = state.modalTriggers.get(modal);
      if (settings.restoreFocus !== false && trigger && trigger.isConnected) {
        trigger.focus({ preventScroll: true });
      }
      emit("lv:motion:modal-closed", { modal: modal }, modal);
    }, duration);
    return true;
  }

  function trapModalKeyboard(event) {
    var modal = state.modalStack[state.modalStack.length - 1];
    if (!modal) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal(modal);
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    var focusable = focusableElements(modal);
    if (!focusable.length) {
      event.preventDefault();
      modal.focus();
      return;
    }
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && doc.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && doc.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function ensureToastRegion() {
    if (state.toastRegion && state.toastRegion.isConnected) {
      return state.toastRegion;
    }
    var existing = doc.querySelector("[data-motion-toast-region]");
    var region = existing || doc.createElement("div");
    region.classList.add("motion-toast-region");
    region.setAttribute("data-motion-toast-region", "");
    region.setAttribute("aria-live", "polite");
    region.setAttribute("aria-atomic", "false");
    if (!existing) {
      doc.body.appendChild(region);
    }
    state.toastRegion = region;
    return region;
  }

  function toast(message, options) {
    var settings = options || {};
    var region = ensureToastRegion();
    var element = doc.createElement("div");
    var kind = ["success", "error", "info"].indexOf(settings.kind) >= 0
      ? settings.kind
      : "success";
    element.className = "motion-toast";
    element.setAttribute("data-motion-toast", "");
    element.setAttribute("data-kind", kind);
    element.setAttribute("role", kind === "error" ? "alert" : "status");
    element.textContent = String(message || "");
    region.appendChild(element);
    window.requestAnimationFrame(function () {
      element.classList.add("is-open");
    });

    var visibleFor = clamp(
      finiteNumber(settings.duration, kind === "error" ? 5200 : 3400),
      1000,
      12000
    );
    var closeTimer = window.setTimeout(function () {
      element.classList.remove("is-open");
      element.classList.add("is-closing");
      window.setTimeout(function () {
        element.remove();
      }, cssMilliseconds("--motion-duration-normal", 260));
    }, visibleFor);
    element.addEventListener(
      "click",
      function () {
        window.clearTimeout(closeTimer);
        element.remove();
      },
      { once: true }
    );
    return element;
  }

  function highlight(target, options) {
    var settings = options || {};
    resolveTargets(target).forEach(function (element) {
      var previous = state.highlightTimers.get(element);
      if (previous) {
        window.clearTimeout(previous);
      }
      element.classList.remove("is-motion-highlighted");
      // Force only the animation state to restart; no geometry is measured.
      void element.offsetWidth;
      element.classList.add("is-motion-highlighted");
      var timer = window.setTimeout(function () {
        element.classList.remove("is-motion-highlighted");
      }, clamp(finiteNumber(settings.duration, 700), 100, 1800));
      state.highlightTimers.set(element, timer);
    });
  }

  function buttonSuccess(target) {
    resolveTargets(target).forEach(function (element) {
      element.classList.add("is-motion-success");
      window.setTimeout(function () {
        element.classList.remove("is-motion-success");
      }, cssMilliseconds("--motion-duration-slow", 520));
    });
  }

  function update(target, value, options) {
    var settings = options || {};
    var updated = false;
    resolveTargets(target).forEach(function (element) {
      var type = settings.type;
      if (!type) {
        if (element.matches(SELECTORS.progress)) {
          type = "progress";
        } else {
          type = "number";
        }
      }
      var result =
        type === "progress"
          ? animateProgress(element, value, settings)
          : animateNumber(element, value, settings);
      if (result) {
        updated = true;
        if (settings.highlight !== false) {
          highlight(element);
        }
      }
    });
    return updated;
  }

  function refresh(scope) {
    var container = scope && (isElement(scope) || scope === doc) ? scope : doc;
    autoEnhance(container);

    elementsWithin(container, SELECTORS.page).forEach(function (element) {
      prepareReveal(element, 0);
    });
    elementsWithin(container, SELECTORS.card).forEach(function (element, index) {
      prepareReveal(element, index);
    });
    elementsWithin(container, SELECTORS.list).forEach(prepareList);
    elementsWithin(container, SELECTORS.number).forEach(prepareNumber);
    elementsWithin(container, SELECTORS.progress).forEach(prepareProgress);
    if (tiltAllowed()) {
      elementsWithin(container, SELECTORS.tilt).forEach(prepareTilt);
    }
    if (parallaxAllowed()) {
      elementsWithin(container, SELECTORS.parallax).forEach(prepareParallax);
    }
    elementsWithin(container, SELECTORS.modal).forEach(prepareModal);
    elementsWithin(container, SELECTORS.button).forEach(function (element) {
      element.classList.add("motion-button");
    });
    elementsWithin(container, SELECTORS.chartLine).forEach(prepareChartLine);
    elementsWithin(container, SELECTORS.chartSegment).forEach(
      prepareChartSegment
    );
    registerDirtyForms(container);

    scheduleParallax();
    return container;
  }

  function finishRunningValues() {
    doc.querySelectorAll(SELECTORS.number).forEach(function (element) {
      var numberState = state.numberStates.get(element);
      if (numberState) {
        if (numberState.frame) {
          window.cancelAnimationFrame(numberState.frame);
          numberState.frame = 0;
        }
        renderNumber(element, numberState, numberState.target);
        element.classList.remove("is-motion-updating");
      }
    });
    doc.querySelectorAll(SELECTORS.progress).forEach(function (element) {
      var progressState = state.progressStates.get(element);
      if (progressState) {
        if (progressState.frame) {
          window.cancelAnimationFrame(progressState.frame);
          progressState.frame = 0;
        }
        renderProgress(element, progressState, progressState.target);
        element.classList.remove("is-motion-updating");
      }
    });
  }

  function createObservers() {
    if ("IntersectionObserver" in window) {
      state.revealObserver = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              reveal(entry.target);
            }
          });
        },
        { rootMargin: "0px 0px -5% 0px", threshold: 0.08 }
      );
      state.valueObserver = new IntersectionObserver(onValueIntersection, {
        rootMargin: "0px 0px -3% 0px",
        threshold: 0.18,
      });
      state.parallaxObserver = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            var parallaxState = state.parallaxStates.get(entry.target);
            if (parallaxState) {
              parallaxState.visible = entry.isIntersecting;
            }
          });
          scheduleParallax();
        },
        { rootMargin: "15% 0px", threshold: 0 }
      );
    }

    state.mutationObserver = new MutationObserver(function (mutations) {
      var added = [];
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (isElement(node)) {
            added.push(node);
          }
        });
      });
      if (added.length) {
        window.requestAnimationFrame(function () {
          added.forEach(refresh);
        });
      }
    });
    state.mutationObserver.observe(doc.body, {
      childList: true,
      subtree: true,
    });
  }

  function onDocumentClick(event) {
    if (handleRouteLinkClick(event)) {
      return;
    }

    var opener = event.target.closest("[data-motion-modal-open]");
    if (opener) {
      event.preventDefault();
      var target =
        opener.getAttribute("data-motion-modal-open") ||
        opener.getAttribute("aria-controls");
      if (target) {
        if (target.charAt(0) !== "#" && doc.getElementById(target)) {
          target = "#" + target;
        }
        openModal(target, opener);
      }
      return;
    }

    var closer = event.target.closest("[data-motion-modal-close]");
    if (closer) {
      event.preventDefault();
      closeModal(closer.closest(SELECTORS.modal));
      return;
    }

    var modal = event.target.closest(SELECTORS.modal);
    if (
      modal &&
      event.target === modal &&
      modal.getAttribute("data-motion-backdrop-close") !== "false"
    ) {
      closeModal(modal);
    }
  }

  function onMotionUpdate(event) {
    var detail = event.detail || {};
    update(
      detail.element || detail.target || detail.selector,
      detail.value,
      detail
    );
  }

  function onVisibilityChange() {
    if (doc.hidden) {
      resetAllTilts();
      return;
    }
    scheduleParallax();
  }

  function onFormValueChanged(event) {
    var form = event.target && event.target.closest("form");
    if (form) {
      updateFormDirtyState(form);
    }
  }

  function onFormSubmitted(event) {
    var form = event.target;
    if (!isTrackedForm(form)) {
      return;
    }
    state.formBaselines.set(form, formSignature(form));
    form.removeAttribute("data-motion-dirty");
  }

  function onFormReset(event) {
    var form = event.target;
    window.requestAnimationFrame(function () {
      updateFormDirtyState(form);
    });
  }

  function onBeforeUnload(event) {
    if (state.navigationApproved || !hasDirtyForms()) {
      return;
    }
    event.preventDefault();
    event.returnValue = "";
  }

  function onPageShow() {
    clearRouteExit();
  }

  function addGlobalListeners() {
    doc.addEventListener("click", onDocumentClick);
    doc.addEventListener("keydown", trapModalKeyboard);
    doc.addEventListener("input", onFormValueChanged);
    doc.addEventListener("change", onFormValueChanged);
    doc.addEventListener("submit", onFormSubmitted);
    doc.addEventListener("reset", onFormReset);
    doc.addEventListener("visibilitychange", onVisibilityChange);
    doc.addEventListener("lv:motion:update", onMotionUpdate);
    state.refreshRequested = function (event) {
      refresh((event.detail && event.detail.root) || doc);
    };
    state.highlightRequested = function (event) {
      var detail = event.detail || {};
      highlight(detail.element || detail.target || detail.selector, detail);
    };
    state.toastRequested = function (event) {
      var detail = event.detail || {};
      toast(detail.message, detail);
    };
    state.buttonSuccessRequested = function (event) {
      var detail = event.detail || {};
      buttonSuccess(detail.element || detail.target || detail.selector);
    };
    doc.addEventListener("lv:motion:refresh", state.refreshRequested);
    doc.addEventListener("lv:motion:highlight", state.highlightRequested);
    doc.addEventListener("lv:motion:toast", state.toastRequested);
    doc.addEventListener(
      "lv:motion:button-success",
      state.buttonSuccessRequested
    );
    window.addEventListener("scroll", scheduleParallax, { passive: true });
    window.addEventListener("resize", scheduleParallax, { passive: true });
    window.addEventListener("beforeunload", onBeforeUnload);
    window.addEventListener("pageshow", onPageShow);

    state.systemPreferenceChanged = function () {
      setMode(state.requestedMode);
    };
    state.pointerCapabilityChanged = function () {
      resetAllTilts();
      scheduleParallax();
    };
    if (typeof reduceQuery.addEventListener === "function") {
      reduceQuery.addEventListener("change", state.systemPreferenceChanged);
      finePointerQuery.addEventListener(
        "change",
        state.pointerCapabilityChanged
      );
      coarsePointerQuery.addEventListener(
        "change",
        state.pointerCapabilityChanged
      );
    } else if (typeof reduceQuery.addListener === "function") {
      reduceQuery.addListener(state.systemPreferenceChanged);
    }
  }

  function init() {
    if (state.initialized || state.destroyed || !doc.body) {
      return api;
    }
    state.initialized = true;
    setMode(modeFromDocument());
    createObservers();
    refresh(doc);
    rootElement.classList.add("motion-system-ready");
    addGlobalListeners();
    finishRouteArrival();
    window.requestAnimationFrame(function () {
      scheduleParallax();
      emit("lv:motion:ready", { api: api, mode: getMode() });
    });
    return api;
  }

  function destroy() {
    if (state.destroyed) {
      return;
    }
    state.destroyed = true;
    if (state.revealObserver) {
      state.revealObserver.disconnect();
    }
    if (state.valueObserver) {
      state.valueObserver.disconnect();
    }
    if (state.parallaxObserver) {
      state.parallaxObserver.disconnect();
    }
    if (state.mutationObserver) {
      state.mutationObserver.disconnect();
    }
    finishRunningValues();
    resetAllTilts();
    resetParallax();
    state.tilts.forEach(function (element) {
      var tiltState = state.tiltStates.get(element);
      if (!tiltState) {
        return;
      }
      element.removeEventListener("pointermove", tiltState.move);
      element.removeEventListener("pointerleave", tiltState.leave);
      element.removeEventListener("pointercancel", tiltState.leave);
      element.removeEventListener("pointerdown", tiltState.down);
      element.removeEventListener("pointerup", tiltState.up);
    });
    doc.removeEventListener("click", onDocumentClick);
    doc.removeEventListener("keydown", trapModalKeyboard);
    doc.removeEventListener("input", onFormValueChanged);
    doc.removeEventListener("change", onFormValueChanged);
    doc.removeEventListener("submit", onFormSubmitted);
    doc.removeEventListener("reset", onFormReset);
    doc.removeEventListener("visibilitychange", onVisibilityChange);
    doc.removeEventListener("lv:motion:update", onMotionUpdate);
    doc.removeEventListener("lv:motion:refresh", state.refreshRequested);
    doc.removeEventListener("lv:motion:highlight", state.highlightRequested);
    doc.removeEventListener("lv:motion:toast", state.toastRequested);
    doc.removeEventListener(
      "lv:motion:button-success",
      state.buttonSuccessRequested
    );
    window.removeEventListener("scroll", scheduleParallax);
    window.removeEventListener("resize", scheduleParallax);
    window.removeEventListener("beforeunload", onBeforeUnload);
    window.removeEventListener("pageshow", onPageShow);
    if (typeof reduceQuery.removeEventListener === "function") {
      reduceQuery.removeEventListener(
        "change",
        state.systemPreferenceChanged
      );
      finePointerQuery.removeEventListener(
        "change",
        state.pointerCapabilityChanged
      );
      coarsePointerQuery.removeEventListener(
        "change",
        state.pointerCapabilityChanged
      );
    } else if (typeof reduceQuery.removeListener === "function") {
      reduceQuery.removeListener(state.systemPreferenceChanged);
    }
    rootElement.classList.remove("motion-system-ready");
  }

  var api = Object.freeze({
    init: init,
    refresh: refresh,
    reveal: reveal,
    update: update,
    animateNumber: animateNumber,
    animateProgress: animateProgress,
    highlight: highlight,
    buttonSuccess: buttonSuccess,
    openModal: openModal,
    closeModal: closeModal,
    toast: toast,
    navigate: navigate,
    setMode: setMode,
    getMode: getMode,
    destroy: destroy,
  });

  window.LVMotion = api;
  if (doc.readyState === "loading") {
    doc.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
