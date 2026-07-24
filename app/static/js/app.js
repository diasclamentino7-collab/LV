(() => {
  "use strict";

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
  });

  window.addEventListener("pageshow", () => {
    document.querySelectorAll('form[data-submitting="true"]').forEach(form => {
      delete form.dataset.submitting;
      form.removeAttribute("aria-busy");
      form.querySelectorAll(".is-submitting").forEach(control => {
        control.classList.remove("is-submitting");
        control.removeAttribute("aria-disabled");
      });
    });
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
