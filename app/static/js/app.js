(() => {
  "use strict";

  if ("serviceWorker" in navigator) {
    void navigator.serviceWorker.register("/static/sw.js").catch(() => {
      // Offline support is progressive; the website remains fully usable.
    });
  }

  const menuButton = document.querySelector(".menu-button");
  const sidebar = document.querySelector(".sidebar");
  const sidebarOverlay = document.querySelector(".sidebar-overlay");
  const sidebarClose = document.querySelector(".sidebar-close");
  const mobileNavigation = window.matchMedia("(max-width: 850px)");
  const focusableSelector = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "summary",
    "[tabindex]:not([tabindex='-1'])",
  ].join(",");
  let navigationReturnFocus = null;

  const navigationIsOpen = () => (
    document.body.classList.contains("navigation-open")
  );

  const setSidebarAvailability = available => {
    if (!sidebar) return;
    sidebar.toggleAttribute("inert", !available);
    sidebar.setAttribute("aria-hidden", available ? "false" : "true");
    sidebarOverlay?.setAttribute(
      "aria-hidden",
      available && mobileNavigation.matches ? "false" : "true",
    );
  };

  const sidebarFocusableElements = () => (
    sidebar
      ? [...sidebar.querySelectorAll(focusableSelector)].filter(element => (
          !element.hasAttribute("disabled")
          && element.getAttribute("aria-hidden") !== "true"
          && element.getClientRects().length > 0
        ))
      : []
  );

  const closeNavigation = (restoreFocus = true) => {
    if (!mobileNavigation.matches) return;
    const wasOpen = navigationIsOpen();
    document.body.classList.remove("navigation-open");
    menuButton?.setAttribute("aria-expanded", "false");
    setSidebarAvailability(false);
    if (wasOpen && restoreFocus) {
      const target = (
        navigationReturnFocus instanceof HTMLElement
          ? navigationReturnFocus
          : menuButton
      );
      target?.focus();
    }
    navigationReturnFocus = null;
  };

  const openNavigation = () => {
    if (!mobileNavigation.matches || !sidebar) return;
    navigationReturnFocus = document.activeElement;
    setSidebarAvailability(true);
    document.body.classList.add("navigation-open");
    menuButton?.setAttribute("aria-expanded", "true");
    window.requestAnimationFrame(() => {
      (sidebarClose || sidebarFocusableElements()[0])?.focus();
    });
  };

  const syncNavigationLayout = () => {
    const focusedInsideSidebar = sidebar?.contains(document.activeElement);
    document.body.classList.remove("navigation-open");
    menuButton?.setAttribute("aria-expanded", "false");
    setSidebarAvailability(!mobileNavigation.matches);
    if (focusedInsideSidebar) {
      if (mobileNavigation.matches) menuButton?.focus();
      else sidebar?.querySelector(".nav-item.is-active")?.focus();
    }
    navigationReturnFocus = null;
  };

  menuButton?.addEventListener("click", () => {
    if (navigationIsOpen()) closeNavigation();
    else openNavigation();
  });
  sidebarClose?.addEventListener("click", () => closeNavigation());
  sidebarOverlay?.addEventListener("click", () => closeNavigation());
  sidebar?.querySelectorAll("a").forEach(link => {
    link.addEventListener("click", () => closeNavigation(false));
  });

  document.addEventListener("keydown", event => {
    if (!mobileNavigation.matches || !navigationIsOpen()) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeNavigation();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = sidebarFocusableElements();
    if (!focusable.length) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (
      event.shiftKey
      && (
        document.activeElement === first
        || !sidebar?.contains(document.activeElement)
      )
    ) {
      event.preventDefault();
      last.focus();
    } else if (
      !event.shiftKey
      && (
        document.activeElement === last
        || !sidebar?.contains(document.activeElement)
      )
    ) {
      event.preventDefault();
      first.focus();
    }
  });

  if (typeof mobileNavigation.addEventListener === "function") {
    mobileNavigation.addEventListener("change", syncNavigationLayout);
  } else {
    mobileNavigation.addListener(syncNavigationLayout);
  }
  syncNavigationLayout();

  window.requestAnimationFrame(() => {
    sidebar?.querySelector(".nav-item.is-active")?.scrollIntoView({
      block: "nearest",
    });
  });

  const shellHeader = document.querySelector(".header");
  let headerFrame = 0;
  const syncHeaderDepth = () => {
    headerFrame = 0;
    shellHeader?.classList.toggle("is-scrolled", window.scrollY > 6);
  };
  window.addEventListener("scroll", () => {
    if (headerFrame) return;
    headerFrame = window.requestAnimationFrame(syncHeaderDepth);
  }, { passive: true });
  syncHeaderDepth();

  const accountMenus = [...document.querySelectorAll("details.account-menu")];

  const closeAccountMenus = (except = null, restoreFocus = false) => {
    accountMenus.forEach(menu => {
      if (menu === except || !menu.open) return;
      menu.open = false;
      if (restoreFocus) menu.querySelector("summary")?.focus();
    });
  };

  accountMenus.forEach(menu => {
    menu.addEventListener("toggle", () => {
      menu.querySelector("summary")?.setAttribute(
        "aria-expanded",
        menu.open ? "true" : "false",
      );
      if (menu.open) closeAccountMenus(menu);
    });
  });

  document.addEventListener("pointerdown", event => {
    const openMenu = accountMenus.find(menu => menu.open);
    if (openMenu && !openMenu.contains(event.target)) closeAccountMenus();
  });

  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    const openMenu = accountMenus.find(menu => menu.open);
    if (!openMenu) return;
    event.preventDefault();
    closeAccountMenus(null, true);
  });

  const inferMotionAction = button => {
    const label = button.textContent.trim().toLocaleLowerCase("pt-PT");
    if (/guardar|gravar|salvar/.test(label)) return "save";
    if (/adicionar|novo|nova|criar/.test(label)) return "add";
    if (/eliminar|retirar|arquivar/.test(label)) return "delete";
    if (/concluir|confirmar/.test(label)) return "complete";
    return "";
  };

  document.querySelectorAll("button, .primary-button, .secondary-button").forEach(button => {
    if (!button.hasAttribute("data-motion-action")) {
      const action = inferMotionAction(button);
      if (action) button.dataset.motionAction = action;
    }
  });

  const SUBMIT_LOCK_TIMEOUT_MS = 20000;

  const releaseSubmitLock = form => {
    if (form.dataset.submitLockTimer) {
      window.clearTimeout(Number(form.dataset.submitLockTimer));
      delete form.dataset.submitLockTimer;
    }
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    form.querySelectorAll(".is-submitting").forEach(control => {
      control.classList.remove("is-submitting");
      control.removeAttribute("aria-disabled");
    });
  };

  document.addEventListener("submit", event => {
    if (event.defaultPrevented || !(event.target instanceof HTMLFormElement)) return;
    const form = event.target;
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(control => {
      control.classList.add("is-submitting");
      control.setAttribute("aria-disabled", "true");
      if (window.LVMotion && ["save", "complete"].includes(control.dataset.motionAction)) {
        window.LVMotion.buttonSuccess(control);
      }
    });
    // Safety net: if a slow/dropped connection prevents the expected page
    // navigation, this releases the button instead of leaving the form stuck
    // on "A processar…" forever with no way to retry.
    const timerId = window.setTimeout(() => releaseSubmitLock(form), SUBMIT_LOCK_TIMEOUT_MS);
    form.dataset.submitLockTimer = String(timerId);
  });

  window.addEventListener("pageshow", () => {
    document.querySelectorAll('form[data-submitting="true"]').forEach(releaseSubmitLock);
  });

  const announceServerFeedback = () => {
    if (!window.LVMotion) return;
    const success = document.querySelector(".success-banner");
    const error = document.querySelector(".form-error");
    if (success?.textContent.trim()) {
      window.LVMotion.toast(success.textContent.trim(), { kind: "success" });
    } else if (error?.textContent.trim()) {
      window.LVMotion.toast(error.textContent.trim(), {
        kind: "error",
        duration: 5200,
      });
    }
  };

  if (document.documentElement.classList.contains("motion-system-ready")) {
    announceServerFeedback();
    window.LVMotion.refresh(document);
  } else {
    document.addEventListener("lv:motion:ready", () => {
      announceServerFeedback();
      window.LVMotion?.refresh(document);
    }, { once: true });
  }
})();
