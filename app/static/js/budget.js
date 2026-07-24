(function () {
  "use strict";

  var workspace = document.querySelector("[data-budget-live]");
  if (!workspace) {
    return;
  }

  var categoryList = workspace.querySelector("[data-budget-categories]");
  var categoryTemplate = workspace.querySelector(
    "[data-budget-category-template]"
  );
  var distribution = workspace.querySelector("[data-budget-distribution]");
  var liveState = workspace.querySelector("[data-budget-live-state]");
  var emptyState = workspace.querySelector("[data-budget-empty]");
  var chartNote = workspace.querySelector("[data-budget-chart-note]");
  var search = workspace.getAttribute("data-budget-search") || "";
  var currentCurrency =
    workspace.getAttribute("data-budget-currency") || "EUR";
  var isSyncing = false;
  var refreshTimer = 0;
  var channel = null;
  var locale = document.documentElement.lang || "pt-PT";

  function finiteNumber(value) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, finiteNumber(value)));
  }

  function money(value, currency) {
    try {
      return new Intl.NumberFormat(locale, {
        style: "currency",
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(finiteNumber(value));
    } catch (_error) {
      return String(currency) + " " + finiteNumber(value).toFixed(2);
    }
  }

  function percentage(value) {
    try {
      return (
        new Intl.NumberFormat(locale, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }).format(finiteNumber(value)) + "%"
      );
    } catch (_error) {
      return finiteNumber(value).toFixed(2) + "%";
    }
  }

  function integer(value) {
    try {
      return new Intl.NumberFormat(locale, {
        maximumFractionDigits: 0,
      }).format(finiteNumber(value));
    } catch (_error) {
      return String(Math.round(finiteNumber(value)));
    }
  }

  function updateAnimatedNumber(element, value, formattedValue) {
    if (!element) {
      return;
    }
    var normalized = String(value);
    if (
      element.getAttribute("data-budget-value") === normalized &&
      element.textContent.trim() === formattedValue
    ) {
      return;
    }
    element.setAttribute("data-budget-value", normalized);
    element.setAttribute("data-motion-value", normalized);
    if (window.LVMotion) {
      window.LVMotion.update(element, formattedValue, {
        type: "number",
      });
    } else {
      element.textContent = formattedValue;
    }
  }

  function seedAnimatedNumber(element, value, formattedValue) {
    if (!element) {
      return;
    }
    element.textContent = formattedValue;
    element.setAttribute("data-budget-value", String(value));
    element.setAttribute("data-motion-value", String(value));
  }

  function updateProgress(element, value) {
    if (!element) {
      return;
    }
    var normalized = clamp(value, 0, 100);
    element.setAttribute("data-motion-value", String(normalized));
    element.setAttribute("aria-valuenow", String(normalized));
    if (window.LVMotion) {
      window.LVMotion.update(element, normalized, {
        type: "progress",
      });
    } else {
      element.style.width = normalized + "%";
    }
  }

  function setLiveState(message, syncing) {
    if (!liveState) {
      return;
    }
    liveState.textContent = message;
    liveState.classList.toggle("is-syncing", Boolean(syncing));
  }

  function updateSummary(payload) {
    var summary = payload.summary;
    var currency = payload.currency || currentCurrency;
    var moneyFields = ["total", "expenses", "remaining", "allocated"];

    moneyFields.forEach(function (field) {
      workspace
        .querySelectorAll('[data-budget-summary="' + field + '"]')
        .forEach(function (element) {
          updateAnimatedNumber(
            element,
            summary[field],
            money(summary[field], currency)
          );
        });
    });
    workspace
      .querySelectorAll('[data-budget-summary="percentage"]')
      .forEach(function (element) {
        updateAnimatedNumber(
          element,
          summary.percentage,
          percentage(summary.percentage)
        );
      });
    workspace
      .querySelectorAll('[data-budget-summary="categories"]')
      .forEach(function (element) {
        updateAnimatedNumber(
          element,
          summary.categories,
          integer(summary.categories)
        );
      });
    workspace
      .querySelectorAll("[data-budget-summary-progress]")
      .forEach(function (element) {
        updateProgress(element, summary.progress_percentage);
      });

    var remainingCard = workspace.querySelector(
      ".budget-kpi.is-remaining"
    );
    var remainingCopy = workspace.querySelector(
      "[data-budget-remaining-copy]"
    );
    var isOver = finiteNumber(summary.remaining) < 0;
    if (remainingCard) {
      remainingCard.classList.toggle("is-over", isOver);
    }
    if (remainingCopy) {
      remainingCopy.textContent = isOver
        ? "Acima do orçamento definido"
        : "Disponível no orçamento total";
    }
    currentCurrency = currency;
    workspace.setAttribute("data-budget-currency", currency);
  }

  function formatDate(value) {
    if (!value) {
      return "—";
    }
    var parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "—";
    }
    try {
      return new Intl.DateTimeFormat(locale, {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(parsed);
    } catch (_error) {
      return parsed.toLocaleString();
    }
  }

  function field(article, name) {
    return article.querySelector('[data-budget-field="' + name + '"]');
  }

  function populateCategory(article, category, isNew, currency) {
    var categoryId = String(Math.max(0, Math.trunc(finiteNumber(category.id))));
    article.setAttribute("data-category-id", categoryId);
    article.classList.toggle("is-over-limit", Boolean(category.over_limit));

    field(article, "name").textContent = String(category.name || "");
    var updatedAt = field(article, "updated-at");
    updatedAt.textContent = formatDate(category.updated_at);
    updatedAt.setAttribute("datetime", category.updated_at || "");

    var expenseElement = field(article, "expenses");
    var limitElement = field(article, "planned-limit");
    if (isNew) {
      seedAnimatedNumber(
        expenseElement,
        category.expenses,
        money(category.expenses, currency)
      );
      seedAnimatedNumber(
        limitElement,
        category.planned_limit,
        money(category.planned_limit, currency)
      );
    } else {
      updateAnimatedNumber(
        expenseElement,
        category.expenses,
        money(category.expenses, currency)
      );
      updateAnimatedNumber(
        limitElement,
        category.planned_limit,
        money(category.planned_limit, currency)
      );
    }

    var usageCopy = field(article, "usage-copy");
    usageCopy.textContent =
      category.usage_percentage === null
        ? "Sem limite definido"
        : percentage(category.usage_percentage) + " do limite utilizado";

    var remaining = finiteNumber(category.remaining);
    field(article, "remaining-copy").textContent = !category.has_limit
      ? money(category.expenses, currency) + " sem limite atribuído"
      : category.over_limit
        ? money(Math.abs(remaining), currency) + " acima do limite"
        : money(remaining, currency) + " disponíveis";

    var progress = field(article, "progress");
    if (isNew) {
      var initialProgress = clamp(category.progress_percentage, 0, 100);
      progress.setAttribute("data-motion-value", String(initialProgress));
      progress.setAttribute("aria-valuenow", String(initialProgress));
      progress.style.width = initialProgress + "%";
    } else {
      updateProgress(progress, category.progress_percentage);
    }

    var editLink = article.querySelector('[data-budget-action="edit"]');
    editLink.href = "/budget/" + encodeURIComponent(categoryId) + "/edit";
    var archiveForm = article.querySelector("[data-budget-archive]");
    archiveForm.action =
      "/budget/" + encodeURIComponent(categoryId) + "/archive";

    if (isNew) {
      archiveForm.addEventListener("submit", function (event) {
        if (
          !window.confirm(
            "Eliminar esta categoria da lista? Os dados serão preservados e poderão ser recuperados."
          )
        ) {
          event.preventDefault();
        }
      });
    }
  }

  function removeCategory(article) {
    var mode = window.LVMotion ? window.LVMotion.getMode().effective : "none";
    if (mode === "none") {
      article.remove();
      return;
    }
    article.classList.add("is-budget-removing");
    window.setTimeout(function () {
      article.remove();
    }, mode === "reduced" ? 130 : 240);
  }

  function reconcileCategories(categories, currency) {
    if (!categoryList || !categoryTemplate) {
      return;
    }
    var current = new Map();
    categoryList
      .querySelectorAll("[data-budget-category]")
      .forEach(function (article) {
        current.set(article.getAttribute("data-category-id"), article);
      });
    var incoming = new Set();

    categories.forEach(function (category) {
      var categoryId = String(
        Math.max(0, Math.trunc(finiteNumber(category.id)))
      );
      incoming.add(categoryId);
      var article = current.get(categoryId);
      var isNew = !article;
      if (isNew) {
        article = categoryTemplate.content.firstElementChild.cloneNode(true);
      }
      populateCategory(article, category, isNew, currency);
      categoryList.appendChild(article);
      if (isNew && window.LVMotion) {
        window.LVMotion.refresh(article);
        window.LVMotion.highlight(article, { duration: 1000 });
      }
    });

    current.forEach(function (article, categoryId) {
      if (!incoming.has(categoryId)) {
        removeCategory(article);
      }
    });
    if (emptyState) {
      emptyState.hidden = categories.length > 0;
    }
  }

  function reconcileDistribution(categories) {
    if (!distribution) {
      return;
    }
    var visibleCategories = categories.filter(function (category) {
      return finiteNumber(category.share_percentage) > 0;
    });
    var current = new Map();
    distribution
      .querySelectorAll("[data-budget-segment]")
      .forEach(function (segment) {
        current.set(segment.getAttribute("data-category-id"), segment);
      });
    var incoming = new Set();

    visibleCategories.forEach(function (category) {
      var categoryId = String(
        Math.max(0, Math.trunc(finiteNumber(category.id)))
      );
      incoming.add(categoryId);
      var segment = current.get(categoryId);
      var isNew = !segment;
      if (isNew) {
        segment = document.createElement("span");
        segment.setAttribute("data-budget-segment", "");
        segment.setAttribute("data-motion-chart-segment", "");
        segment.setAttribute("data-category-id", categoryId);
      }
      var share = clamp(category.share_percentage, 0, 100);
      segment.style.setProperty("--budget-share", share + "%");
      segment.title =
        String(category.name || "") + " · " + percentage(share);
      distribution.appendChild(segment);
      if (isNew && window.LVMotion) {
        window.LVMotion.refresh(segment);
      }
    });

    current.forEach(function (segment, categoryId) {
      if (!incoming.has(categoryId)) {
        segment.remove();
      }
    });
    distribution.classList.toggle(
      "is-empty",
      visibleCategories.length === 0
    );
    if (chartNote) {
      chartNote.textContent = visibleCategories.length
        ? "Cada segmento representa a proporção real das despesas nas categorias visíveis."
        : "A distribuição surgirá assim que registarem a primeira despesa.";
    }
  }

  function applyPayload(payload) {
    if (
      !payload ||
      !payload.summary ||
      !Array.isArray(payload.categories)
    ) {
      throw new Error("Invalid budget payload");
    }
    var currency = payload.currency || currentCurrency;
    updateSummary(payload);
    reconcileCategories(payload.categories, currency);
    reconcileDistribution(payload.categories);
  }

  function endpoint() {
    var url = new URL("/api/budget-summary", window.location.origin);
    if (search) {
      url.searchParams.set("q", search);
    }
    return url.toString();
  }

  function scheduleRefresh(delay) {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(refreshBudget, delay);
  }

  async function refreshBudget() {
    if (isSyncing || document.hidden) {
      scheduleRefresh(12000);
      return;
    }
    isSyncing = true;
    setLiveState("A sincronizar valores…", true);
    try {
      var response = await window.fetch(endpoint(), {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      if (!response.ok) {
        throw new Error("Budget sync failed");
      }
      applyPayload(await response.json());
      setLiveState("Atualizado agora · valores guardados na base de dados.", false);
    } catch (_error) {
      setLiveState(
        "Não foi possível atualizar agora. Os dados apresentados permanecem guardados.",
        false
      );
    } finally {
      isSyncing = false;
      scheduleRefresh(12000);
    }
  }

  function signalMutation() {
    var marker = String(Date.now());
    try {
      window.localStorage.setItem("lv-budget-changed", marker);
    } catch (_error) {
      // Cross-tab storage is an enhancement; the periodic refresh remains active.
    }
    if (channel) {
      channel.postMessage({ type: "budget-mutation", at: marker });
    }
  }

  workspace.addEventListener(
    "submit",
    function (event) {
      if (event.target.matches("[data-budget-mutation]")) {
        window.setTimeout(signalMutation, 0);
      }
    },
    true
  );

  window.addEventListener("storage", function (event) {
    if (event.key === "lv-budget-changed") {
      scheduleRefresh(500);
    }
  });
  window.addEventListener("focus", function () {
    scheduleRefresh(120);
  });
  window.addEventListener("pageshow", function () {
    scheduleRefresh(120);
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      scheduleRefresh(120);
    }
  });

  if ("BroadcastChannel" in window) {
    channel = new BroadcastChannel("lv-wedding-budget");
    channel.addEventListener("message", function (event) {
      if (event.data && event.data.type === "budget-mutation") {
        scheduleRefresh(650);
      }
    });
  }

  var mutationResult = new URLSearchParams(window.location.search).get(
    "message"
  );
  if (
    ["created", "updated", "archived", "restored"].indexOf(mutationResult) >=
    0
  ) {
    // The redirect only happens after the transaction commits, so other open
    // tabs can now request the definitive database state.
    window.setTimeout(signalMutation, 0);
  }
  scheduleRefresh(800);
})();
