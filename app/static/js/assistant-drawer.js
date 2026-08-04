(() => {
  "use strict";

  const dialog = document.querySelector("#assistant-drawer");
  if (!(dialog instanceof HTMLDialogElement)) return;

  const panel = dialog.querySelector(".assistant-panel");
  const closeButton = dialog.querySelector("[data-assistant-close]");
  const tabs = [...dialog.querySelectorAll("[data-assistant-tab]")];
  const messagesContainer = dialog.querySelector("[data-assistant-messages]");
  const feedback = dialog.querySelector("[data-assistant-feedback]");
  const composeForm = dialog.querySelector("[data-assistant-compose]");
  const providerField = dialog.querySelector("[data-assistant-provider-field]");
  const textarea = dialog.querySelector("#assistant-input");
  const sendButton = composeForm?.querySelector("button[type='submit']");
  const sendLabel = dialog.querySelector("[data-assistant-send-label]");
  const focusableSelector = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "summary",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");

  let returnFocus = null;
  let fetchController = null;
  let closeTimer = null;
  let activeProvider = "openai";

  const setFeedback = (message = "", isError = false) => {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.classList.toggle("is-error", isError);
  };

  const createElement = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  const timeLabel = value => {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "";
    return new Intl.DateTimeFormat("pt-PT", { hour: "2-digit", minute: "2-digit" }).format(parsed);
  };

  const renderMessages = messages => {
    if (!messagesContainer) return;
    messagesContainer.replaceChildren();
    messagesContainer.setAttribute("aria-busy", "false");

    if (!messages.length) {
      const empty = createElement("div", "assistant-empty");
      empty.append(
        createElement("span", "", "💬"),
        createElement("strong", "", "Comecem a conversa"),
        createElement("p", "", "Perguntem sobre o orçamento, os convidados ou as tarefas do casamento.")
      );
      messagesContainer.append(empty);
      return;
    }

    messages.forEach(message => {
      const bubble = createElement("article", "assistant-message");
      bubble.dataset.role = message.role;
      bubble.append(createElement("p", "assistant-message-text", message.content));
      const time = timeLabel(message.created_at);
      if (time) bubble.append(createElement("time", "assistant-message-time", time));
      messagesContainer.append(bubble);
    });
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  };

  const renderLoading = () => {
    if (!messagesContainer) return;
    messagesContainer.setAttribute("aria-busy", "true");
    const loading = createElement("div", "assistant-loading");
    loading.append(createElement("i"), createElement("span", "", "A carregar a conversa…"));
    messagesContainer.replaceChildren(loading);
  };

  const loadMessages = async provider => {
    fetchController?.abort();
    fetchController = new AbortController();
    renderLoading();
    try {
      const response = await fetch(`/api/assistant/messages?provider=${encodeURIComponent(provider)}`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: fetchController.signal
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "Não foi possível carregar a conversa.");
      renderMessages(payload.messages || []);
    } catch (error) {
      if (error.name === "AbortError") return;
      if (messagesContainer) {
        messagesContainer.setAttribute("aria-busy", "false");
        messagesContainer.replaceChildren(
          createElement(
            "div",
            "assistant-empty",
            error.message || "Não foi possível carregar a conversa."
          )
        );
      }
    }
  };

  const selectTab = provider => {
    if (!provider || provider === activeProvider) return;
    activeProvider = provider;
    if (providerField) providerField.value = provider;
    tabs.forEach(tab => {
      tab.setAttribute("aria-selected", String(tab.dataset.assistantTab === provider));
    });
    setFeedback("");
    loadMessages(provider);
  };

  const openDrawer = trigger => {
    if (dialog.open) return;
    window.clearTimeout(closeTimer);
    dialog.classList.remove("is-closing");
    returnFocus = trigger instanceof HTMLElement ? trigger : document.activeElement;
    dialog.showModal();
    loadMessages(activeProvider);
    window.requestAnimationFrame(() => textarea?.focus());
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
    const trigger = event.target.closest("[data-assistant-trigger]");
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

  tabs.forEach(tab => {
    tab.addEventListener("click", () => selectTab(tab.dataset.assistantTab));
  });

  composeForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const value = textarea?.value.trim();
    if (!value) return;
    sendButton?.setAttribute("disabled", "");
    sendButton?.classList.add("is-loading");
    if (sendLabel) sendLabel.textContent = "A enviar…";
    setFeedback("");
    try {
      const response = await fetch("/api/assistant/messages", {
        method: "POST",
        body: new FormData(composeForm),
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "Não foi possível enviar a mensagem.");
      if (textarea) textarea.value = "";
      await loadMessages(activeProvider);
    } catch (error) {
      setFeedback(error.message || "Não foi possível enviar a mensagem.", true);
    } finally {
      sendButton?.removeAttribute("disabled");
      sendButton?.classList.remove("is-loading");
      if (sendLabel) sendLabel.textContent = "Enviar";
    }
  });
})();
