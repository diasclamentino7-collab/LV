(() => {
  "use strict";

  const palette = document.querySelector("#command-palette");
  if (!(palette instanceof HTMLDialogElement)) return;

  const input = palette.querySelector("[data-command-input]");
  const results = palette.querySelector("[data-command-results]");
  const status = palette.querySelector("[data-command-status]");
  const empty = palette.querySelector("[data-command-empty]");
  const recentGroup = palette.querySelector("[data-command-recent-group]");
  const recentList = palette.querySelector("[data-command-recent-list]");
  const standardGroups = [...palette.querySelectorAll("[data-command-group]")];
  const sourceItems = [...palette.querySelectorAll("[data-command-item]")];
  const sourceById = new Map(sourceItems.map(item => [item.dataset.commandId, item]));
  const storageKey = "lv-command-recent";
  const maximumRecents = 4;
  let activeIndex = -1;

  const normalize = value => String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-PT")
    .trim();

  const normalizedPath = value => {
    const clean = String(value || "/").replace(/\/+$/, "");
    return clean || "/";
  };

  const readRecents = () => {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
      if (!Array.isArray(parsed)) return [];
      return [...new Set(parsed)]
        .filter(id => typeof id === "string" && sourceById.has(id))
        .slice(0, maximumRecents);
    } catch (_error) {
      return [];
    }
  };

  const writeRecent = item => {
    const id = item?.dataset.commandId;
    if (!id || !sourceById.has(id)) return;
    const recents = [id, ...readRecents().filter(entry => entry !== id)]
      .slice(0, maximumRecents);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(recents));
    } catch (_error) {
      // Recent navigation is optional when private storage is unavailable.
    }
  };

  const markCurrentRoutes = root => {
    root.querySelectorAll("[data-command-item]").forEach(item => {
      let isCurrent = false;
      try {
        const url = new URL(item.href, window.location.href);
        isCurrent = normalizedPath(url.pathname) === normalizedPath(window.location.pathname);
      } catch (_error) {
        isCurrent = false;
      }
      item.classList.toggle("is-current", isCurrent);
      if (isCurrent) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
  };

  const renderRecents = () => {
    recentList?.replaceChildren();
    readRecents().forEach(id => {
      const source = sourceById.get(id);
      if (!source || !recentList) return;
      const clone = source.cloneNode(true);
      clone.classList.add("is-recent");
      clone.removeAttribute("id");
      recentList.append(clone);
    });
    if (recentGroup) recentGroup.hidden = !recentList?.children.length;
    markCurrentRoutes(palette);
  };

  const visibleItems = () => [...palette.querySelectorAll("[data-command-item]")]
    .filter(item => !item.hidden && !item.closest("[hidden]"));

  const setActiveItem = (index, { focus = false, scroll = false } = {}) => {
    palette.querySelectorAll("[data-command-item]").forEach(item => {
      item.classList.remove("is-active");
      item.setAttribute("aria-selected", "false");
      item.removeAttribute("id");
    });
    const items = visibleItems();
    if (!items.length) {
      activeIndex = -1;
      input?.setAttribute("aria-activedescendant", "");
      return;
    }
    activeIndex = ((index % items.length) + items.length) % items.length;
    items.forEach((item, itemIndex) => {
      const isActive = itemIndex === activeIndex;
      item.classList.toggle("is-active", isActive);
      item.setAttribute("aria-selected", isActive ? "true" : "false");
      item.id = `command-option-${itemIndex}`;
    });
    const active = items[activeIndex];
    input?.setAttribute("aria-activedescendant", active.id);
    if (scroll) active.scrollIntoView({ block: "nearest" });
    if (focus) active.focus({ preventScroll: true });
  };

  const applyFilter = () => {
    const query = normalize(input?.value);
    const terms = query.split(/\s+/).filter(Boolean);

    sourceItems.forEach(item => {
      const haystack = normalize(`${item.dataset.commandSearch || ""} ${item.textContent}`);
      item.hidden = terms.length > 0 && !terms.every(term => haystack.includes(term));
    });

    standardGroups.forEach(group => {
      group.hidden = ![...group.querySelectorAll("[data-command-item]")]
        .some(item => !item.hidden);
    });

    if (recentGroup) {
      recentGroup.hidden = Boolean(query) || !recentList?.children.length;
    }

    const count = sourceItems.filter(item => !item.hidden).length;
    if (empty) empty.hidden = count > 0;
    if (status) {
      status.textContent = query
        ? `${count} ${count === 1 ? "resultado encontrado" : "resultados encontrados"} para ${input.value.trim()}.`
        : "Escolham uma ação ou pesquisem pelo nome.";
    }
    setActiveItem(0);
  };

  const prepareOpen = () => {
    renderRecents();
    if (input) input.value = "";
    input?.setAttribute("aria-expanded", "true");
    applyFilter();
    window.requestAnimationFrame(() => input?.focus({ preventScroll: true }));
  };

  const openPalette = trigger => {
    if (palette.open) {
      input?.focus({ preventScroll: true });
      return;
    }
    if (window.LVMotion?.openModal) {
      window.LVMotion.openModal(palette, trigger || document.activeElement);
    } else {
      palette.showModal();
      prepareOpen();
    }
  };

  const closePalette = () => {
    if (window.LVMotion?.closeModal) {
      window.LVMotion.closeModal(palette);
    } else if (palette.open) {
      palette.close();
    }
  };

  const activateItem = item => {
    if (!(item instanceof HTMLAnchorElement)) return;
    let destination;
    try {
      destination = new URL(item.href, window.location.href);
    } catch (_error) {
      return;
    }
    writeRecent(item);

    const samePage = normalizedPath(destination.pathname) === normalizedPath(window.location.pathname)
      && destination.search === window.location.search;
    if (samePage) {
      closePalette();
      window.LVMotion?.toast?.("Já estão nesta área.", { kind: "success", duration: 1800 });
      return;
    }

    if (window.LVMotion?.navigate) {
      window.LVMotion.navigate(destination.href, { kind: "subtle" });
    } else {
      window.location.assign(destination.href);
    }
  };

  input?.addEventListener("input", applyFilter);
  input?.addEventListener("keydown", event => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveItem(activeIndex + 1, { scroll: true });
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveItem(activeIndex - 1, { scroll: true });
    } else if (event.key === "Enter") {
      const item = visibleItems()[activeIndex];
      if (!item) return;
      event.preventDefault();
      activateItem(item);
    }
  });

  results?.addEventListener("pointerover", event => {
    const item = event.target.closest("[data-command-item]");
    if (!item) return;
    const index = visibleItems().indexOf(item);
    if (index >= 0) setActiveItem(index);
  });

  results?.addEventListener("click", event => {
    const item = event.target.closest("[data-command-item]");
    if (!item || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    activateItem(item);
  });

  palette.addEventListener("lv:motion:modal-opened", prepareOpen);
  palette.addEventListener("lv:motion:modal-closed", () => {
    input?.setAttribute("aria-expanded", "false");
  });
  palette.addEventListener("close", () => {
    input?.setAttribute("aria-expanded", "false");
  });
  palette.addEventListener("cancel", event => {
    if (window.LVMotion?.closeModal) return;
    event.preventDefault();
    closePalette();
  });

  document.addEventListener("keydown", event => {
    const isShortcut = (event.ctrlKey || event.metaKey)
      && !event.altKey
      && event.key.toLocaleLowerCase("pt-PT") === "k";
    if (!isShortcut) return;
    event.preventDefault();
    const otherDialog = document.querySelector("dialog[open]:not(#command-palette)");
    if (otherDialog) return;
    openPalette(document.querySelector("[data-motion-modal-open='command-palette']"));
  });

  markCurrentRoutes(palette);
})();
