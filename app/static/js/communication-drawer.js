(() => {
  "use strict";

  const dialog = document.querySelector("#communication-drawer");
  if (!(dialog instanceof HTMLDialogElement)) return;

  const panel = dialog.querySelector(".communication-panel");
  const closeButton = dialog.querySelector("[data-communication-close]");
  const searchForm = dialog.querySelector("[data-communication-search]");
  const searchInput = searchForm?.querySelector("input[name='q']");
  const createForm = dialog.querySelector("[data-communication-create]");
  const recordsContainer = dialog.querySelector("[data-communication-records]");
  const feedback = dialog.querySelector("[data-communication-feedback]");
  const count = dialog.querySelector("[data-communication-count]");
  const saveButton = createForm?.querySelector("button[type='submit']");
  const saveLabel = dialog.querySelector("[data-communication-save-label]");
  const focusableSelector = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "summary",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");
  const categoryIcons = {
    "Nota": "✎",
    "Ideia": "✦",
    "Decisão": "✓",
    "Lembrete": "◷",
    "Tarefa rápida": "→"
  };

  let returnFocus = null;
  let searchTimer = null;
  let fetchController = null;
  let closeTimer = null;

  const motion = ["full", "reduced", "none"].includes(dialog.dataset.motionPreference)
    ? dialog.dataset.motionPreference
    : "full";
  document.documentElement.dataset.motion = motion;

  const setFeedback = (message = "", isError = false) => {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.classList.toggle("is-error", isError);
  };

  const dateLabel = value => {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "";
    return new Intl.DateTimeFormat("pt-PT", {
      day: "2-digit",
      month: "short"
    }).format(parsed);
  };

  const createElement = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  const renderRecords = records => {
    if (!recordsContainer) return;
    recordsContainer.replaceChildren();
    recordsContainer.setAttribute("aria-busy", "false");
    if (count) count.textContent = `${records.length} ${records.length === 1 ? "registo" : "registos"}`;

    if (!records.length) {
      const empty = createElement("div", "communication-empty");
      empty.append(
        createElement("span", "", "♡"),
        createElement("strong", "", "Nada encontrado"),
        createElement("p", "", "Criem um registo rápido ou experimentem outra pesquisa.")
      );
      recordsContainer.append(empty);
      return;
    }

    records.forEach(record => {
      const article = createElement("article", "communication-record");
      article.dataset.category = record.category;

      const icon = createElement(
        "span",
        "communication-type",
        categoryIcons[record.category] || "✎"
      );
      icon.setAttribute("aria-hidden", "true");

      const main = createElement("div", "communication-record-main");
      const title = createElement("h3");
      const link = createElement("a", "communication-record-link", record.title);
      link.href = record.url;
      title.append(link);
      main.append(title);
      if (record.description) {
        main.append(createElement("p", "", record.description));
      }
      const meta = createElement("div", "communication-meta");
      meta.append(createElement("span", "", record.category));
      if (record.responsible) {
        meta.append(createElement("span", "", `· ${record.responsible}`));
      }
      if (record.updated_by) {
        meta.append(createElement("span", "", `· ${record.updated_by}`));
      }
      const formattedDate = dateLabel(record.event_date || record.updated_at);
      if (formattedDate) meta.append(createElement("span", "", `· ${formattedDate}`));
      main.append(meta);

      const priority = createElement("span", "communication-priority", record.priority || "Média");
      priority.dataset.priority = record.priority || "Média";
      article.append(icon, main, priority);
      recordsContainer.append(article);
    });
  };

  const renderLoading = () => {
    if (!recordsContainer) return;
    recordsContainer.setAttribute("aria-busy", "true");
    const loading = createElement("div", "communication-loading");
    loading.append(
      createElement("i"),
      createElement("span", "", "A carregar comunicação…")
    );
    recordsContainer.replaceChildren(loading);
  };

  const loadRecords = async (query = "") => {
    fetchController?.abort();
    fetchController = new AbortController();
    renderLoading();
    try {
      const response = await fetch(
        `/api/communication-panel?q=${encodeURIComponent(query.trim())}`,
        {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          signal: fetchController.signal
        }
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "Não foi possível carregar.");
      renderRecords(payload.records || []);
    } catch (error) {
      if (error.name === "AbortError") return;
      if (recordsContainer) {
        recordsContainer.setAttribute("aria-busy", "false");
        recordsContainer.replaceChildren(
          createElement(
            "div",
            "communication-empty",
            error.message || "Não foi possível carregar a comunicação."
          )
        );
      }
    }
  };

  const openDrawer = trigger => {
    if (dialog.open) return;
    window.clearTimeout(closeTimer);
    dialog.classList.remove("is-closing");
    returnFocus = trigger instanceof HTMLElement ? trigger : document.activeElement;
    dialog.showModal();
    loadRecords(searchInput?.value || "");
    window.requestAnimationFrame(() => searchInput?.focus());
  };

  const closeDrawer = () => {
    if (!dialog.open || dialog.classList.contains("is-closing")) return;
    const fullMotion = window.LVMotion?.getMode().effective === "full";
    if (!fullMotion) {
      dialog.close();
      return;
    }
    dialog.classList.add("is-closing");
    closeTimer = window.setTimeout(() => dialog.close(), 170);
  };

  document.addEventListener("click", event => {
    const trigger = event.target.closest("[data-communication-trigger]");
    if (!trigger) return;
    event.preventDefault();
    openDrawer(trigger);
  });

  closeButton?.addEventListener("click", closeDrawer);
  dialog.addEventListener("cancel", event => {
    event.preventDefault();
    closeDrawer();
  });
  dialog.addEventListener("click", event => {
    if (event.target === dialog) closeDrawer();
  });
  panel?.addEventListener("click", event => event.stopPropagation());
  dialog.addEventListener("close", () => {
    window.clearTimeout(closeTimer);
    dialog.classList.remove("is-closing");
    fetchController?.abort();
    if (returnFocus instanceof HTMLElement && returnFocus.isConnected) returnFocus.focus();
    returnFocus = null;
  });

  dialog.addEventListener("keydown", event => {
    if (event.key !== "Tab") return;
    const focusable = [...dialog.querySelectorAll(focusableSelector)].filter(
      element => element.getClientRects().length > 0
    );
    if (!focusable.length) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  searchForm?.addEventListener("submit", event => {
    event.preventDefault();
    loadRecords(searchInput?.value || "");
  });
  searchInput?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => loadRecords(searchInput.value), 260);
  });

  createForm?.addEventListener("submit", async event => {
    event.preventDefault();
    if (!createForm.reportValidity()) return;
    saveButton?.setAttribute("disabled", "");
    saveButton?.classList.add("is-loading");
    if (saveLabel) saveLabel.textContent = "A guardar…";
    setFeedback("");
    try {
      const response = await fetch("/api/communication-panel", {
        method: "POST",
        body: new FormData(createForm),
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "Não foi possível guardar.");
      createForm.reset();
      const priority = createForm.querySelector("select[name='priority']");
      if (priority) priority.value = "Média";
      setFeedback(payload.message || "Guardado na base de dados.");
      await loadRecords(searchInput?.value || "");
      createForm.querySelector("input[name='title']")?.focus();
    } catch (error) {
      setFeedback(error.message || "Não foi possível guardar.", true);
    } finally {
      saveButton?.removeAttribute("disabled");
      saveButton?.classList.remove("is-loading");
      if (saveLabel) saveLabel.textContent = "Guardar";
    }
  });
})();
