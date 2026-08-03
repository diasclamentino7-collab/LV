"use strict";

const authPage = document.querySelector("[data-auth-page]");

if (authPage) {
  const strengthLabel = (value) => {
    if (value.length < 8) return { level: "weak", text: "Usem pelo menos 8 caracteres." };

    let score = 0;
    if (value.length >= 12) score += 1;
    if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
    if (/\d/.test(value)) score += 1;
    if (/[^A-Za-z0-9]/.test(value)) score += 1;

    if (score <= 1) return { level: "weak", text: "Válida, mas pode ser mais forte." };
    if (score <= 2) return { level: "medium", text: "Boa password." };
    return { level: "good", text: "Password forte." };
  };

  for (const button of authPage.querySelectorAll("[data-password-toggle]")) {
    button.addEventListener("click", () => {
      const control = button.closest(".password-control");
      const input = control?.querySelector("[data-password-input]");
      if (!input) return;

      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      button.textContent = reveal ? "Ocultar" : "Mostrar";
      button.setAttribute("aria-pressed", String(reveal));
      const subject = button.getAttribute("aria-label")?.replace(/^(Mostrar|Ocultar)\s+/u, "") || "password";
      button.setAttribute("aria-label", `${reveal ? "Ocultar" : "Mostrar"} ${subject}`);
      input.focus({ preventScroll: true });
    });
  }

  for (const status of authPage.querySelectorAll("[data-password-strength]")) {
    const input = status.closest("label")?.querySelector('[autocomplete="new-password"]');
    if (!input) continue;

    const updateStrength = () => {
      const result = strengthLabel(input.value);
      status.dataset.strength = result.level;
      status.textContent = result.text;
    };
    input.addEventListener("input", updateStrength);
  }

  for (const form of authPage.querySelectorAll("[data-auth-form]")) {
    form.addEventListener("submit", (event) => {
      if (form.dataset.submitting === "true") {
        event.preventDefault();
        return;
      }
      if (!form.checkValidity()) return;

      form.dataset.submitting = "true";
      const submitter = event.submitter;
      if (!submitter) return;
      submitter.setAttribute("aria-busy", "true");
      submitter.setAttribute("aria-disabled", "true");
      const label = submitter.querySelector("[data-submit-label]");
      if (label) label.textContent = "A processar…";
    });
  }
}
