(() => {
  "use strict";

  const dashboard = document.querySelector("[data-dashboard-live]");
  if (!dashboard) return;

  const liveElements = new Map();
  for (const element of dashboard.querySelectorAll("[data-live-key]")) {
    const key = element.dataset.liveKey;
    if (!liveElements.has(key)) liveElements.set(key, []);
    liveElements.get(key).push(element);
  }
  const initialTarget = dashboard.dataset.weddingTarget
    ? new Date(dashboard.dataset.weddingTarget).getTime()
    : null;
  let weddingTarget = Number.isFinite(initialTarget) ? initialTarget : null;
  let refreshTimer = null;

  const announceUpdate = (element, previousValue, nextValue) => {
    if (previousValue === nextValue) return;
    element.classList.remove("is-live-updated");
    void element.offsetWidth;
    element.classList.add("is-live-updated");
  };

  const updateText = (key, value) => {
    const elements = liveElements.get(key) ?? [];
    for (const element of elements) {
      const nextValue = String(value);
      const previousValue = element.textContent.trim();
      if (previousValue === nextValue) continue;
      element.textContent = nextValue;
      announceUpdate(element, previousValue, nextValue);
    }
  };

  const updateNumber = (key, value, options = {}) => {
    const elements = liveElements.get(key) ?? [];
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      updateText(key, options.fallback ?? String(value));
      return;
    }
    for (const element of elements) {
      const nextValue = String(numericValue);
      const previousValue = element.dataset.liveValue ?? "";
      if (previousValue === nextValue) continue;
      element.dataset.liveValue = nextValue;
      if (window.LVMotion?.update(
        element,
        numericValue,
        {
          type: "number",
          duration: options.duration,
          highlight: options.highlight,
          preserveFormat: true,
        }
      )) continue;
      const formatted = options.format ? options.format(numericValue) : nextValue;
      const previousText = element.textContent.trim();
      element.textContent = formatted;
      announceUpdate(element, previousText, formatted);
    }
  };

  const updateMoney = (key, symbol, value) => {
    const amount = Number.parseFloat(value);
    updateNumber(key, amount, {
      format: (number) => `${symbol}${number.toLocaleString("pt-PT", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}`,
    });
  };

  const updateProgress = (value) => {
    const progress = dashboard.querySelector("[data-live-progress]");
    if (!progress) return;
    const bounded = Math.min(100, Math.max(0, Number(value) || 0));
    const previousValue = progress.dataset.liveValue ?? progress.style.width;
    const nextValue = String(bounded);
    if (previousValue === nextValue) return;
    progress.dataset.liveValue = nextValue;
    progress.closest("[role='progressbar']")?.setAttribute("aria-valuenow", String(bounded));
    if (window.LVMotion?.update(
      progress,
      bounded,
      { type: "progress", highlight: false }
    )) return;
    progress.style.width = `${bounded}%`;
    announceUpdate(progress, previousValue, nextValue);
  };

  const updateBudgetAlert = (payload) => {
    const alert = dashboard.querySelector("[data-live-budget-alert]");
    if (!alert) return;
    alert.hidden = !payload.budget_alert;
    if (payload.budget_alert) {
      alert.textContent =
        `A utilização atingiu o alerta definido de ${payload.budget_alert_percent}%.`;
    }
  };

  const updateActivities = (activities, timeZone) => {
    const region = dashboard.querySelector("[data-live-activity-region]");
    if (!region || !Array.isArray(activities)) return;
    const signature = JSON.stringify(
      activities.map(activity => [activity.id, activity.description, activity.occurred_at])
    );
    if (region.dataset.liveSignature === signature) return;
    region.dataset.liveSignature = signature;

    if (!activities.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const icon = document.createElement("span");
      icon.className = "empty-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = "✦";
      const heading = document.createElement("h3");
      heading.textContent = "Ainda não há atividade.";
      const copy = document.createElement("p");
      copy.textContent = "As ações guardadas pelos dois utilizadores vão aparecer aqui.";
      empty.append(icon, heading, copy);
      region.replaceChildren(empty);
      window.LVMotion?.refresh(region);
      return;
    }

    const list = document.createElement("div");
    list.className = "activity-list";
    for (const activity of activities) {
      const article = document.createElement("article");
      const icon = document.createElement("span");
      icon.className = "empty-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = "✦";
      const content = document.createElement("p");
      const title = document.createElement("strong");
      title.textContent = `${activity.user_name} ${activity.description}`;
      const time = document.createElement("small");
      const occurredAt = new Date(activity.occurred_at);
      if (Number.isNaN(occurredAt.getTime())) {
        time.textContent = "";
      } else {
        const options = {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            timeZone: timeZone || "Europe/Lisbon",
        };
        try {
          time.textContent = new Intl.DateTimeFormat("pt-PT", options)
            .format(occurredAt)
            .replace(",", "");
        } catch {
          delete options.timeZone;
          time.textContent = new Intl.DateTimeFormat("pt-PT", options)
            .format(occurredAt)
            .replace(",", "");
        }
      }
      content.append(title, time);
      article.append(icon, content);
      list.append(article);
    }
    region.replaceChildren(list);
    window.LVMotion?.refresh(region);
    window.LVMotion?.highlight(region);
  };

  const applySummary = (payload) => {
    updateNumber("confirmed_guests", payload.confirmed_guests);
    updateText("guest_target", payload.guest_target ? `/${payload.guest_target}` : "");
    updateNumber("guests", payload.guests);
    updateMoney("expenses", payload.currency_symbol, payload.expenses);
    updateNumber("categories", payload.categories);
    updateNumber("task_percentage", payload.task_percentage);
    updateNumber("completed_tasks", payload.completed_tasks);
    updateNumber("tasks", payload.tasks);
    updateNumber("open_tasks", Math.max(0, payload.tasks - payload.completed_tasks));
    updateMoney("budget_expenses", payload.currency_symbol, payload.expenses);
    updateMoney("budget_total", payload.currency_symbol, payload.budget_total);
    updateMoney("budget_allocated", payload.currency_symbol, payload.budget_allocated);
    updateMoney("budget_pending", payload.currency_symbol, payload.budget_pending);
    updateMoney("budget_remaining", payload.currency_symbol, payload.budget_remaining);
    updateNumber("budget_percentage", payload.budget_percentage);
    updateProgress(payload.budget_progress);
    updateBudgetAlert(payload);
    updateActivities(payload.activities, payload.wedding_timezone);

    const parsedTarget = payload.wedding_target
      ? new Date(payload.wedding_target).getTime()
      : null;
    const nextTarget = Number.isFinite(parsedTarget) ? parsedTarget : null;
    if (nextTarget !== weddingTarget) {
      weddingTarget = nextTarget;
      dashboard.dataset.weddingTarget = payload.wedding_target || "";
      if (nextTarget) {
        const dateOptions = {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: payload.wedding_timezone || "Europe/Lisbon",
        };
        let formattedDate;
        try {
          formattedDate = new Intl.DateTimeFormat("pt-PT", dateOptions)
            .format(new Date(nextTarget));
        } catch {
          delete dateOptions.timeZone;
          formattedDate = new Intl.DateTimeFormat("pt-PT", dateOptions)
            .format(new Date(nextTarget));
        }
        updateText("countdown_date", formattedDate.replace(",", " ·"));
        updateText("countdown_heading", "Estamos quase lá.");
      } else {
        updateText("countdown_date", "Definir data nas Configurações");
        updateText("countdown_heading", "Definam a data do casamento.");
        for (const key of [
          "countdown_days",
          "countdown_hours",
          "countdown_minutes",
          "countdown_seconds",
        ]) {
          updateText(key, "—");
        }
      }
      updateCountdown();
    }
  };

  const refreshSummary = async () => {
    if (document.hidden) return;
    try {
      const response = await fetch("/api/dashboard-summary", {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      if (!response.ok) return;
      applySummary(await response.json());
    } catch {
      // Network interruptions are expected on mobile; the next poll retries.
    }
  };

  const updateCountdown = () => {
    if (document.hidden) return;
    if (!weddingTarget) return;
    const difference = Math.max(0, weddingTarget - Date.now());
    const totalSeconds = Math.floor(difference / 1000);
    const countdownOptions = { duration: 180, highlight: false };
    updateNumber("countdown_days", Math.floor(totalSeconds / 86400), countdownOptions);
    updateNumber("countdown_hours", Math.floor((totalSeconds % 86400) / 3600), countdownOptions);
    updateNumber("countdown_minutes", Math.floor((totalSeconds % 3600) / 60), countdownOptions);
    updateNumber("countdown_seconds", totalSeconds % 60, countdownOptions);
    if (difference === 0) {
      updateText("countdown_heading", "O grande dia chegou.");
    }
  };

  const scheduleRefresh = () => {
    window.clearInterval(refreshTimer);
    refreshTimer = window.setInterval(refreshSummary, 12000);
  };

  let dashboardStarted = false;
  const startDashboard = () => {
    if (dashboardStarted) return;
    dashboardStarted = true;
    updateCountdown();
    window.setInterval(updateCountdown, 1000);
    scheduleRefresh();
    window.addEventListener("focus", refreshSummary);
    window.addEventListener("pageshow", refreshSummary);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refreshSummary();
    });
  };

  if (document.documentElement.classList.contains("motion-system-ready")) {
    startDashboard();
  } else {
    document.addEventListener("lv:motion:ready", startDashboard, { once: true });
    document.addEventListener("DOMContentLoaded", startDashboard, { once: true });
  }
})();
