(function () {
  "use strict";

  var workspace = document.querySelector("[data-guest-workspace]");
  if (!workspace) {
    return;
  }

  document.documentElement.classList.add("guest-enhanced");

  var apiUrl = workspace.getAttribute("data-api-url") || "/api/guests";
  var csrfToken = workspace.getAttribute("data-csrf-token") || "";
  var pollInterval = Math.max(
    10000,
    Number(workspace.getAttribute("data-poll-interval")) || 18000
  );
  var rowsContainer = workspace.querySelector("[data-guest-rows]");
  var rowTemplate = workspace.querySelector("[data-guest-row-template]");
  var quickRow = workspace.querySelector("[data-guest-quick-row]");
  var quickForm = workspace.querySelector("[data-guest-quick-form]");
  var quickName = workspace.querySelector("[data-guest-quick-name]");
  var filterForm = workspace.querySelector("[data-guest-filters]");
  var searchInput = workspace.querySelector("[data-guest-search]");
  var directionInput = workspace.querySelector("[data-guest-direction]");
  var directionToggle = workspace.querySelector(
    "[data-guest-direction-toggle]"
  );
  var sortSelect = filterForm && filterForm.elements.namedItem("sort");
  var selectAll = workspace.querySelector("[data-guest-select-all]");
  var bulkToolbar = workspace.querySelector("[data-guest-bulk-toolbar]");
  var selectedCount = workspace.querySelector("[data-guest-selected-count]");
  var liveState = workspace.querySelector("[data-guest-live-state]");
  var visibleCount = workspace.querySelector("[data-guest-visible-count]");
  var emptyState = workspace.querySelector("[data-guest-empty]");
  var celebration = workspace.querySelector("[data-guest-celebration]");
  var selected = new Set();
  var saveChains = new Map();
  var refreshTimer = 0;
  var searchTimer = 0;
  var activeRequest = null;
  var isRefreshing = false;
  var revision = workspace.getAttribute("data-revision") || "";
  var channel = null;
  var guestFields = [
    "name",
    "congregation",
    "sex",
    "side",
    "age_group",
    "rsvp_status",
    "table_name",
    "phone",
    "email",
    "dietary_requirements",
    "special_needs",
    "address",
    "invitation_sent",
    "gift_received",
    "notes",
  ];

  function motionMode() {
    if (window.LVMotion) {
      return window.LVMotion.getMode().effective;
    }
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "reduced"
      : "full";
  }

  function toast(message, kind) {
    if (window.LVMotion && message) {
      window.LVMotion.toast(message, {
        kind: kind || "success",
        duration: kind === "error" ? 5200 : 3000,
      });
    }
  }

  function errorMessage(payload, fallback) {
    if (payload && typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload && Array.isArray(payload.detail) && payload.detail.length) {
      var first = payload.detail[0];
      if (first && typeof first.msg === "string") {
        return first.msg.replace(/^Value error,\s*/i, "");
      }
    }
    return fallback || "Não foi possível concluir esta alteração.";
  }

  async function jsonRequest(url, options) {
    var settings = options || {};
    var headers = new Headers(settings.headers || {});
    headers.set("Accept", "application/json");
    headers.set("X-CSRF-Token", csrfToken);
    if (settings.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    var response = await window.fetch(url, {
      method: settings.method || "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: headers,
      body: settings.body,
      signal: settings.signal,
    });
    var payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (response.status === 401) {
      window.location.assign("/login");
      throw new Error("Session expired");
    }
    if (!response.ok) {
      var failure = new Error(errorMessage(payload));
      failure.status = response.status;
      failure.payload = payload;
      throw failure;
    }
    return payload;
  }

  function setLiveState(message, state) {
    if (!liveState) {
      return;
    }
    liveState.lastChild.textContent = message;
    liveState.classList.toggle("is-syncing", state === "syncing");
    liveState.classList.toggle("is-error", state === "error");
  }

  function rowControls(row) {
    return Array.prototype.slice.call(
      row.querySelectorAll("[data-guest-field]")
    );
  }

  function controlValue(control) {
    return control.type === "checkbox" ? Boolean(control.checked) : control.value;
  }

  function comparableValue(value) {
    if (typeof value === "boolean") {
      return value ? "true" : "false";
    }
    return String(value === null || value === undefined ? "" : value);
  }

  function setControlValue(control, value) {
    if (control.type === "checkbox") {
      control.checked = Boolean(value);
    } else {
      var normalized = comparableValue(value);
      if (
        control.tagName === "SELECT" &&
        !Array.prototype.some.call(control.options, function (option) {
          return option.value === normalized;
        })
      ) {
        var option = document.createElement("option");
        option.value = normalized;
        option.textContent = normalized || "—";
        control.appendChild(option);
      }
      control.value = normalized;
      if (control.tagName === "SELECT") {
        control.dataset.value = normalized;
      }
    }
    control.dataset.originalValue = comparableValue(controlValue(control));
    control.classList.remove("is-dirty");
    control.removeAttribute("aria-invalid");
  }

  function enableRow(row) {
    rowControls(row).forEach(function (control) {
      control.removeAttribute("readonly");
      control.removeAttribute("disabled");
      if (!Object.prototype.hasOwnProperty.call(control.dataset, "originalValue")) {
        control.dataset.originalValue = comparableValue(controlValue(control));
      }
    });
  }

  function rowIsProtected(row) {
    return (
      row.contains(document.activeElement) ||
      row.classList.contains("is-saving") ||
      Boolean(row.querySelector(".is-dirty"))
    );
  }

  function populateRow(row, guest, force) {
    if (!row || !guest || (!force && rowIsProtected(row))) {
      return false;
    }
    var guestId = String(guest.id || "");
    row.dataset.guestId = guestId;
    row.dataset.updatedAt = guest.updated_at || "";
    row.setAttribute("data-guest-row", "");

    var check = row.querySelector(".guest-row-check");
    if (check) {
      check.value = guestId;
      check.checked = selected.has(guestId);
      check.setAttribute(
        "aria-label",
        "Selecionar " + String(guest.name || "convidado")
      );
    }

    guestFields.forEach(function (field) {
      var control = row.querySelector('[data-guest-field="' + field + '"]');
      if (control) {
        setControlValue(control, guest[field]);
      }
    });

    var editLink = row.querySelector(".guest-edit-link");
    if (editLink) {
      editLink.href = "/guests/" + encodeURIComponent(guestId) + "/edit";
    }
    var archiveForm = row.querySelector("[data-guest-archive-form]");
    if (archiveForm) {
      archiveForm.action =
        "/guests/" + encodeURIComponent(guestId) + "/archive";
    }
    var archiveButton = archiveForm && archiveForm.querySelector("button");
    if (archiveButton) {
      archiveButton.setAttribute(
        "aria-label",
        "Eliminar " + String(guest.name || "convidado")
      );
    }
    var state = row.querySelector("[data-guest-save-state]");
    if (state) {
      state.textContent = guest.updated_by
        ? "Por " + String(guest.updated_by)
        : "Guardado";
      if (guest.updated_at) {
        state.title = "Última atualização: " + formatDate(guest.updated_at);
      }
    }
    row.classList.remove("is-save-error", "is-saving");
    enableRow(row);
    return true;
  }

  function createRow(guest) {
    if (!rowTemplate || !rowsContainer) {
      return null;
    }
    var row = rowTemplate.content.firstElementChild.cloneNode(true);
    populateRow(row, guest, true);
    row.classList.add("is-entering");
    rowsContainer.appendChild(row);
    window.setTimeout(function () {
      row.classList.remove("is-entering");
    }, 350);
    if (window.LVMotion) {
      window.LVMotion.refresh(row);
    }
    return row;
  }

  function removeRow(row) {
    if (!row || rowIsProtected(row)) {
      return;
    }
    if (motionMode() === "none") {
      row.remove();
      return;
    }
    row.classList.add("is-leaving");
    window.setTimeout(function () {
      row.remove();
    }, motionMode() === "reduced" ? 80 : 220);
  }

  function formatDate(value) {
    var parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "—";
    }
    try {
      return new Intl.DateTimeFormat(document.documentElement.lang || "pt-PT", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(parsed);
    } catch (_error) {
      return parsed.toLocaleString();
    }
  }

  function animateMetric(element, value) {
    if (!element) {
      return;
    }
    var formatted = comparableValue(value);
    if (element.textContent === formatted) {
      return;
    }
    if (window.LVMotion && element.hasAttribute("data-motion-number")) {
      element.dataset.motionValue = formatted;
      window.LVMotion.update(element, formatted, { type: "number" });
    } else {
      element.textContent = formatted;
    }
  }

  function updateStats(stats) {
    if (!stats) {
      return;
    }
    Object.keys(stats).forEach(function (key) {
      workspace
        .querySelectorAll('[data-guest-metric="' + key + '"]')
        .forEach(function (element) {
          animateMetric(element, stats[key]);
        });
    });
  }

  function replaceSelectOptions(select, values, placeholder) {
    if (!select || select === document.activeElement || !Array.isArray(values)) {
      return;
    }
    var current = select.value;
    while (select.firstChild) {
      select.removeChild(select.firstChild);
    }
    var first = document.createElement("option");
    first.value = "";
    first.textContent = placeholder;
    select.appendChild(first);
    values.forEach(function (value) {
      var option = document.createElement("option");
      option.value = String(value);
      option.textContent = String(value);
      select.appendChild(option);
    });
    if (
      current &&
      !Array.prototype.some.call(select.options, function (option) {
        return option.value === current;
      })
    ) {
      var retained = document.createElement("option");
      retained.value = current;
      retained.textContent = current;
      select.appendChild(retained);
    }
    select.value = current;
  }

  function updateFilterOptions(filters) {
    if (!filters || !filterForm) {
      return;
    }
    replaceSelectOptions(
      filterForm.elements.namedItem("congregation"),
      filters.congregations,
      "Todas"
    );
    replaceSelectOptions(
      filterForm.elements.namedItem("table_name"),
      filters.tables,
      "Todas"
    );
    replaceSelectOptions(
      workspace.querySelector("[data-guest-bulk-table]"),
      filters.tables,
      "Escolher mesa…"
    );
  }

  function currentRows() {
    return Array.prototype.slice.call(
      rowsContainer.querySelectorAll("[data-guest-row]")
    );
  }

  function updateEmptyState() {
    var total = currentRows().length;
    if (emptyState) {
      emptyState.hidden = total > 0;
    }
  }

  function reconcile(payload) {
    if (!payload || !Array.isArray(payload.items)) {
      throw new Error("Invalid guests payload");
    }
    var existing = new Map();
    currentRows().forEach(function (row) {
      existing.set(row.dataset.guestId, row);
    });
    var incoming = new Set();

    payload.items.forEach(function (guest) {
      var guestId = String(guest.id);
      incoming.add(guestId);
      var row = existing.get(guestId);
      if (!row) {
        row = createRow(guest);
      } else {
        populateRow(row, guest, false);
      }
      if (row && !rowIsProtected(row)) {
        rowsContainer.appendChild(row);
      }
    });

    existing.forEach(function (row, guestId) {
      if (!incoming.has(guestId)) {
        selected.delete(guestId);
        removeRow(row);
      }
    });

    updateStats(payload.stats);
    updateFilterOptions(payload.filters);
    if (visibleCount) {
      animateMetric(
        visibleCount,
        payload.filtered === undefined ? payload.items.length : payload.filtered
      );
    }
    if (payload.revision !== undefined) {
      revision = payload.revision || "";
    }
    updateSelectionToolbar();
    window.setTimeout(updateEmptyState, 230);
  }

  function filterEndpoint() {
    var endpoint = new URL(apiUrl, window.location.origin);
    if (!filterForm) {
      return endpoint.toString();
    }
    new FormData(filterForm).forEach(function (value, key) {
      var normalized = String(value).trim();
      if (normalized) {
        endpoint.searchParams.set(key, normalized);
      }
    });
    endpoint.searchParams.set("limit", "500");
    return endpoint.toString();
  }

  function syncFilterUrl() {
    if (!filterForm || !window.history || !window.history.replaceState) {
      return;
    }
    var url = new URL("/guests", window.location.origin);
    new FormData(filterForm).forEach(function (value, key) {
      var normalized = String(value).trim();
      var isDefault =
        (key === "sort" && normalized === "name") ||
        (key === "direction" && normalized === "asc");
      if (normalized && !isDefault) {
        url.searchParams.set(key, normalized);
      }
    });
    window.history.replaceState({}, "", url.pathname + url.search);
  }

  function scheduleRefresh(delay) {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(function () {
      refreshGuests("poll");
    }, delay);
  }

  async function refreshGuests(reason) {
    if (document.hidden) {
      scheduleRefresh(pollInterval);
      return;
    }
    if (reason === "filter" && activeRequest) {
      activeRequest.abort();
    } else if (isRefreshing) {
      scheduleRefresh(pollInterval);
      return;
    }
    var controller = new AbortController();
    activeRequest = controller;
    isRefreshing = true;
    if (reason !== "poll") {
      setLiveState("A sincronizar…", "syncing");
    }
    try {
      var payload = await jsonRequest(filterEndpoint(), {
        signal: controller.signal,
      });
      reconcile(payload);
      setLiveState("Dados sincronizados", "ready");
    } catch (error) {
      if (error.name !== "AbortError") {
        setLiveState(
          "Sem ligação · as alterações guardadas mantêm-se seguras",
          "error"
        );
      }
    } finally {
      if (activeRequest === controller) {
        isRefreshing = false;
        activeRequest = null;
        scheduleRefresh(pollInterval);
      }
    }
  }

  function setRowSaveState(row, state, message) {
    var indicator = row.querySelector("[data-guest-save-state]");
    row.classList.toggle("is-saving", state === "saving");
    row.classList.toggle("is-save-error", state === "error");
    if (state === "saved") {
      row.classList.remove("is-saved");
      window.requestAnimationFrame(function () {
        row.classList.add("is-saved");
      });
      window.setTimeout(function () {
        row.classList.remove("is-saved");
      }, 750);
    }
    if (indicator) {
      indicator.textContent = message;
    }
  }

  function markControlDirty(control) {
    var changed =
      comparableValue(controlValue(control)) !== control.dataset.originalValue;
    control.classList.toggle("is-dirty", changed);
    if (control.tagName === "SELECT") {
      control.dataset.value = control.value;
    }
  }

  function celebrate(control) {
    if (!celebration || motionMode() !== "full") {
      return;
    }
    var rect = control.getBoundingClientRect();
    var colors = ["#D88BA7", "#C9A46A", "#7eac88", "#F8DCE8"];
    for (var index = 0; index < 9; index += 1) {
      var sparkle = document.createElement("span");
      var angle = (Math.PI * 2 * index) / 9;
      var distance = 24 + (index % 3) * 7;
      sparkle.className = "guest-sparkle";
      sparkle.style.left = rect.left + rect.width / 2 + "px";
      sparkle.style.top = rect.top + rect.height / 2 + "px";
      sparkle.style.setProperty(
        "--sparkle-x",
        Math.cos(angle) * distance + "px"
      );
      sparkle.style.setProperty(
        "--sparkle-y",
        Math.sin(angle) * distance + "px"
      );
      sparkle.style.setProperty("--sparkle-color", colors[index % colors.length]);
      celebration.appendChild(sparkle);
      window.setTimeout(function (particle) {
        particle.remove();
      }, 760, sparkle);
    }
  }

  function signalMutation() {
    var marker = String(Date.now());
    try {
      window.localStorage.setItem("lv-guests-changed", marker);
    } catch (_error) {
      // Cross-tab sync is optional; polling remains active.
    }
    if (channel) {
      channel.postMessage({ type: "guests-changed", at: marker });
    }
  }

  function saveControl(control) {
    var row = control.closest("[data-guest-row]");
    if (!row || !control.dataset.guestField) {
      return Promise.resolve();
    }
    markControlDirty(control);
    if (!control.classList.contains("is-dirty")) {
      return Promise.resolve();
    }
    var guestId = row.dataset.guestId;
    var field = control.dataset.guestField;
    var previous = saveChains.get(guestId) || Promise.resolve();
    var operation = previous
      .catch(function () {
        // A later edit must still be able to save after an earlier failure.
      })
      .then(async function () {
        markControlDirty(control);
        if (!control.classList.contains("is-dirty")) {
          return;
        }
        var value = controlValue(control);
        if (field === "name" && !String(value).trim()) {
          control.setAttribute("aria-invalid", "true");
          setRowSaveState(row, "error", "Nome obrigatório");
          toast("O nome do convidado não pode ficar vazio.", "error");
          return;
        }
        var body = {
          expected_updated_at: row.dataset.updatedAt || null,
        };
        var submittedValue = comparableValue(value);
        body[field] = value;
        setRowSaveState(row, "saving", "A guardar…");
        try {
          var payload = await jsonRequest(
            apiUrl + "/" + encodeURIComponent(guestId),
            {
              method: "PATCH",
              body: JSON.stringify(body),
            }
          );
          row.dataset.updatedAt = payload.guest.updated_at || "";
          if (comparableValue(controlValue(control)) === submittedValue) {
            setControlValue(control, payload.guest[field]);
          } else {
            control.dataset.originalValue = comparableValue(payload.guest[field]);
            markControlDirty(control);
          }
          updateStats(payload.stats);
          revision = payload.revision || revision;
          setRowSaveState(
            row,
            "saved",
            payload.guest.updated_by
              ? "Por " + String(payload.guest.updated_by)
              : "Guardado"
          );
          setLiveState("Alteração guardada agora", "ready");
          if (field === "rsvp_status" && value === "Confirmado") {
            celebrate(control);
          }
          signalMutation();
        } catch (error) {
          if (error.status === 409 && error.payload && error.payload.guest) {
            var localValue = controlValue(control);
            var remoteGuest = error.payload.guest;
            var remoteValue = remoteGuest[field];
            populateRow(row, remoteGuest, true);
            setControlValue(control, localValue);
            control.dataset.originalValue = comparableValue(remoteValue);
            markControlDirty(control);
            row.dataset.updatedAt = remoteGuest.updated_at || "";
            setRowSaveState(row, "error", "Rever alteração");
            toast(
              "Outra pessoa alterou este convidado. Prima Esc para aceitar a versão guardada ou Enter para guardar a sua alteração.",
              "error"
            );
          } else {
            control.setAttribute("aria-invalid", "true");
            setRowSaveState(row, "error", "Não guardado");
            setLiveState("Há uma alteração por guardar", "error");
            toast(error.message, "error");
          }
        }
      });
    saveChains.set(guestId, operation);
    operation.finally(function () {
      if (saveChains.get(guestId) === operation) {
        saveChains.delete(guestId);
      }
    });
    return operation;
  }

  function quickPayload() {
    var values = {};
    guestFields.forEach(function (field) {
      values[field] = ["invitation_sent", "gift_received"].indexOf(field) >= 0
        ? false
        : "";
    });
    values.age_group = "Adulto";
    values.rsvp_status = "Pendente";
    document
      .querySelectorAll('[form="guest-quick-add"][name]')
      .forEach(function (control) {
        values[control.name] = control.type === "checkbox"
          ? Boolean(control.checked)
          : control.value;
      });
    return values;
  }

  function clearQuickForm() {
    document
      .querySelectorAll('[form="guest-quick-add"][name]')
      .forEach(function (control) {
        if (control.type === "checkbox") {
          control.checked = false;
        } else if (control.name === "rsvp_status") {
          control.value = "Pendente";
          control.dataset.value = "Pendente";
        } else if (control.name === "age_group") {
          control.value = "Adulto";
        } else {
          control.value = "";
        }
      });
  }

  async function createQuickGuest(event) {
    event.preventDefault();
    var payload = quickPayload();
    if (!String(payload.name).trim()) {
      quickName.focus();
      toast("Escrevam primeiro o nome do convidado.", "error");
      return;
    }
    var button = quickRow.querySelector(".guest-quick-save");
    button.disabled = true;
    quickRow.setAttribute("aria-busy", "true");
    setLiveState("A adicionar convidado…", "syncing");
    try {
      var response = await jsonRequest(apiUrl, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      createRow(response.guest);
      updateStats(response.stats);
      revision = response.revision || revision;
      clearQuickForm();
      setLiveState("Convidado adicionado e guardado", "ready");
      toast(response.message || "Convidado adicionado.", "success");
      celebrate(quickName);
      signalMutation();
      syncFilterUrl();
      scheduleRefresh(650);
      quickName.focus();
    } catch (error) {
      setLiveState("Não foi possível adicionar", "error");
      toast(error.message, "error");
    } finally {
      button.disabled = false;
      quickRow.removeAttribute("aria-busy");
      updateEmptyState();
    }
  }

  function selectedRows() {
    return currentRows().filter(function (row) {
      return selected.has(row.dataset.guestId);
    });
  }

  function updateSelectionToolbar() {
    currentRows().forEach(function (row) {
      var isSelected = selected.has(row.dataset.guestId);
      row.classList.toggle("is-selected", isSelected);
      var check = row.querySelector(".guest-row-check");
      if (check) {
        check.checked = isSelected;
      }
    });
    if (selectedCount) {
      selectedCount.textContent = String(selected.size);
    }
    if (bulkToolbar) {
      bulkToolbar.hidden = selected.size === 0;
    }
    if (selectAll) {
      var total = currentRows().length;
      selectAll.checked = total > 0 && selected.size === total;
      selectAll.indeterminate = selected.size > 0 && selected.size < total;
    }
  }

  function clearSelection() {
    selected.clear();
    updateSelectionToolbar();
  }

  async function performBulk(action, value, explicitIds) {
    var ids = explicitIds || Array.from(selected).map(Number);
    if (!ids.length) {
      return;
    }
    var expected = {};
    currentRows().forEach(function (row) {
      if (ids.indexOf(Number(row.dataset.guestId)) >= 0) {
        expected[row.dataset.guestId] = row.dataset.updatedAt || "";
      }
    });
    bulkToolbar && bulkToolbar.setAttribute("aria-busy", "true");
    setLiveState("A aplicar alteração em grupo…", "syncing");
    try {
      var payload = await jsonRequest(apiUrl + "/bulk", {
        method: "POST",
        body: JSON.stringify({
          ids: ids,
          action: action,
          value: value,
          expected_updated_at: expected,
        }),
      });
      (payload.items || []).forEach(function (guest) {
        var row = rowsContainer.querySelector(
          '[data-guest-id="' + String(guest.id) + '"]'
        );
        if (row) {
          populateRow(row, guest, true);
        }
      });
      (payload.archived_ids || []).forEach(function (guestId) {
        var row = rowsContainer.querySelector(
          '[data-guest-id="' + String(guestId) + '"]'
        );
        selected.delete(String(guestId));
        removeRow(row);
      });
      updateStats(payload.stats);
      revision = payload.revision || revision;
      clearSelection();
      setLiveState("Alteração em grupo guardada", "ready");
      toast(payload.message || "Convidados atualizados.", "success");
      signalMutation();
      scheduleRefresh(650);
    } catch (error) {
      setLiveState("Não foi possível aplicar a alteração", "error");
      toast(error.message, "error");
      if (error.status === 409) {
        scheduleRefresh(350);
      }
    } finally {
      bulkToolbar && bulkToolbar.removeAttribute("aria-busy");
    }
  }

  function moveToRow(control, direction) {
    var row = control.closest("[data-guest-row]");
    if (!row) {
      return;
    }
    var rows = currentRows();
    var index = rows.indexOf(row);
    var target = rows[index + direction];
    if (!target) {
      return;
    }
    var field = control.dataset.guestField;
    var next = target.querySelector('[data-guest-field="' + field + '"]');
    if (next) {
      next.focus();
      if (typeof next.select === "function" && next.type !== "checkbox") {
        next.select();
      }
    }
  }

  function restoreControl(control) {
    var original = control.dataset.originalValue;
    if (control.type === "checkbox") {
      control.checked = original === "true";
    } else {
      control.value = original || "";
      if (control.tagName === "SELECT") {
        control.dataset.value = control.value;
      }
    }
    control.classList.remove("is-dirty");
    control.removeAttribute("aria-invalid");
  }

  function applyFilters() {
    clearSelection();
    syncFilterUrl();
    refreshGuests("filter");
  }

  function clearFilters() {
    if (!filterForm) {
      return;
    }
    Array.prototype.forEach.call(filterForm.elements, function (control) {
      if (!control.name) {
        return;
      }
      if (control.name === "sort") {
        control.value = "name";
      } else if (control.name === "direction") {
        control.value = "asc";
      } else {
        control.value = "";
      }
    });
    if (directionToggle) {
      directionToggle.textContent = "↑";
    }
    applyFilters();
  }

  currentRows().forEach(enableRow);
  updateSelectionToolbar();
  updateEmptyState();

  workspace.addEventListener("focusin", function (event) {
    var control = event.target.closest("[data-guest-field]");
    if (control && !control.classList.contains("is-dirty")) {
      control.dataset.originalValue = comparableValue(controlValue(control));
    }
  });

  workspace.addEventListener("input", function (event) {
    var control = event.target.closest("[data-guest-field]");
    if (control) {
      markControlDirty(control);
    }
  });

  workspace.addEventListener("change", function (event) {
    var control = event.target.closest("[data-guest-field]");
    if (control) {
      saveControl(control);
      return;
    }
    var check = event.target.closest(".guest-row-check");
    if (check) {
      if (check.checked) {
        selected.add(check.value);
      } else {
        selected.delete(check.value);
      }
      updateSelectionToolbar();
    }
  });

  workspace.addEventListener("focusout", function (event) {
    var control = event.target.closest("[data-guest-field]");
    if (control && control.type !== "checkbox" && control.tagName !== "SELECT") {
      saveControl(control);
    }
  });

  workspace.addEventListener("keydown", function (event) {
    var control = event.target.closest("[data-guest-field]");
    if (!control) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      restoreControl(control);
      control.blur();
      return;
    }
    if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      event.preventDefault();
      saveControl(control).then(function () {
        moveToRow(control, event.key === "ArrowDown" ? 1 : -1);
      });
      return;
    }
    if (event.key === "Enter" && control.tagName !== "TEXTAREA") {
      event.preventDefault();
      saveControl(control).then(function () {
        moveToRow(control, event.shiftKey ? -1 : 1);
      });
    }
  });

  workspace.addEventListener("click", function (event) {
    var focusNew = event.target.closest("[data-guest-focus-new]");
    if (focusNew) {
      quickName.focus();
      quickName.scrollIntoView({ behavior: motionMode() === "full" ? "smooth" : "auto", block: "center" });
      return;
    }
    var expand = event.target.closest("[data-guest-expand]");
    if (expand) {
      var row = expand.closest("[data-guest-row]");
      var expanded = !row.classList.contains("is-expanded");
      row.classList.toggle("is-expanded", expanded);
      expand.setAttribute("aria-expanded", String(expanded));
      expand.textContent = expanded ? "Menos" : "Mais";
      return;
    }
    var sortButton = event.target.closest("[data-guest-sort]");
    if (sortButton && sortSelect) {
      var field = sortButton.dataset.guestSort;
      if (sortSelect.value === field) {
        directionInput.value = directionInput.value === "desc" ? "asc" : "desc";
      } else {
        sortSelect.value = field;
        directionInput.value = "asc";
      }
      directionToggle.textContent = directionInput.value === "desc" ? "↓" : "↑";
      applyFilters();
      return;
    }
    var bulkButton = event.target.closest("[data-guest-bulk]");
    if (bulkButton) {
      var action = bulkButton.dataset.guestBulk;
      if (
        action === "archive" &&
        !window.confirm(
          "Eliminar os convidados selecionados da lista? Os dados ficam preservados nos eliminados."
        )
      ) {
        return;
      }
      var value = bulkButton.dataset.guestValue;
      if (value === "true" || value === "false") {
        value = value === "true";
      }
      performBulk(action, value || null);
      return;
    }
    if (event.target.closest("[data-guest-assign-table]")) {
      var tableSelect = workspace.querySelector("[data-guest-bulk-table]");
      if (!tableSelect.value) {
        tableSelect.focus();
        toast("Escolham primeiro uma mesa.", "error");
        return;
      }
      performBulk("table_name", tableSelect.value);
      return;
    }
    if (event.target.closest("[data-guest-selection-clear]")) {
      clearSelection();
      return;
    }
    if (event.target.closest("[data-guest-clear]")) {
      clearFilters();
      return;
    }
    var densityButton = event.target.closest("[data-guest-density]");
    if (densityButton) {
      var compact = !workspace.classList.contains("is-compact");
      workspace.classList.toggle("is-compact", compact);
      densityButton.setAttribute("aria-pressed", String(compact));
      densityButton.textContent = compact ? "Vista confortável" : "Vista compacta";
      try {
        window.localStorage.setItem("lv-guests-density", compact ? "compact" : "comfortable");
      } catch (_error) {
        // Density persistence is optional.
      }
    }
  });

  workspace.addEventListener("submit", function (event) {
    var archiveForm = event.target.closest("[data-guest-archive-form]");
    if (archiveForm) {
      if (event.defaultPrevented) {
        return;
      }
      event.preventDefault();
      var row = archiveForm.closest("[data-guest-row]");
      performBulk("archive", null, [Number(row.dataset.guestId)]);
    }
  });

  quickForm.addEventListener("submit", createQuickGuest);

  filterForm.addEventListener("submit", function (event) {
    event.preventDefault();
    applyFilters();
  });

  filterForm.addEventListener("change", function (event) {
    if (event.target !== searchInput && event.target !== directionInput) {
      applyFilters();
    }
  });

  searchInput.addEventListener("input", function () {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(applyFilters, 320);
  });

  directionToggle.addEventListener("click", function () {
    directionInput.value = directionInput.value === "desc" ? "asc" : "desc";
    directionToggle.textContent = directionInput.value === "desc" ? "↓" : "↑";
    applyFilters();
  });

  selectAll.addEventListener("change", function () {
    selected.clear();
    if (selectAll.checked) {
      currentRows().forEach(function (row) {
        selected.add(row.dataset.guestId);
      });
    }
    updateSelectionToolbar();
  });

  document.addEventListener("keydown", function (event) {
    var target = event.target;
    var isTyping = target instanceof HTMLElement && (
      target.matches("input, select, textarea") ||
      target.isContentEditable
    );
    if (
      event.key === "/" &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.shiftKey &&
      !isTyping
    ) {
      event.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
  });

  window.addEventListener("focus", function () {
    scheduleRefresh(180);
  });
  window.addEventListener("pageshow", function () {
    scheduleRefresh(180);
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      scheduleRefresh(180);
    }
  });
  window.addEventListener("storage", function (event) {
    if (event.key === "lv-guests-changed") {
      scheduleRefresh(280);
    }
  });

  if ("BroadcastChannel" in window) {
    channel = new BroadcastChannel("lv-wedding-guests");
    channel.addEventListener("message", function (event) {
      if (event.data && event.data.type === "guests-changed") {
        scheduleRefresh(280);
      }
    });
  }

  try {
    if (window.localStorage.getItem("lv-guests-density") === "compact") {
      workspace.classList.add("is-compact");
      var density = workspace.querySelector("[data-guest-density]");
      density.setAttribute("aria-pressed", "true");
      density.textContent = "Vista confortável";
    }
  } catch (_error) {
    // Default comfortable density remains available.
  }

  scheduleRefresh(pollInterval);
})();
