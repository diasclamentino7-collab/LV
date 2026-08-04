(() => {
  "use strict";

  const SUBMIT_LOCK_TIMEOUT_MS = 20000;

  const controlsFor = form => [...form.querySelectorAll("[data-form-control]")]
    .filter(control => !control.disabled && Boolean(control.name));

  const isFilled = control => {
    if (control instanceof HTMLInputElement && ["checkbox", "radio"].includes(control.type)) {
      return control.checked;
    }
    return String(control.value || "").trim().length > 0;
  };

  const formSnapshot = form => JSON.stringify(controlsFor(form).map(control => [
    control.name,
    control instanceof HTMLInputElement && ["checkbox", "radio"].includes(control.type)
      ? control.checked
      : control.value,
  ]));

  const friendlyValidationMessage = control => {
    const validity = control.validity;
    if (validity.valueMissing) return "Preencham este campo para continuar.";
    if (validity.typeMismatch && control.type === "email") return "Confirmem o email, por exemplo nome@exemplo.pt.";
    if (validity.typeMismatch && control.type === "url") return "Introduzam um endereço completo, começando por https://.";
    if (validity.rangeUnderflow) return `O valor mínimo é ${control.min}.`;
    if (validity.rangeOverflow) return `O valor máximo é ${control.max}.`;
    if (validity.stepMismatch) return "Introduzam um valor válido para este campo.";
    if (validity.badInput) return "Confirmem o formato do valor introduzido.";
    if (validity.tooLong) return `Utilizem no máximo ${control.maxLength} caracteres.`;
    if (validity.tooShort) return `Utilizem pelo menos ${control.minLength} caracteres.`;
    if (validity.patternMismatch) return "Confirmem o formato deste campo.";
    return "Revejam este campo antes de guardar.";
  };

  const resizeTextarea = textarea => {
    if (!(textarea instanceof HTMLTextAreaElement)) return;
    textarea.style.height = "auto";
    const targetHeight = Math.min(Math.max(textarea.scrollHeight, 104), 360);
    textarea.style.height = `${targetHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > 360 ? "auto" : "hidden";
  };

  const validateControl = (control, reveal = false) => {
    const field = control.closest("[data-form-field]");
    const error = field?.querySelector("[data-form-field-error]");
    control.setCustomValidity("");
    const valid = control.validity.valid;
    if (!valid && reveal) {
      const message = friendlyValidationMessage(control);
      control.setCustomValidity(message);
      control.setAttribute("aria-invalid", "true");
      field?.classList.add("is-invalid");
      field?.classList.remove("is-valid");
      if (error) error.textContent = message;
      return false;
    }
    control.removeAttribute("aria-invalid");
    field?.classList.remove("is-invalid");
    field?.classList.toggle("is-valid", valid && isFilled(control));
    if (error) error.textContent = "";
    return valid;
  };

  const focusFirstInvalid = form => {
    const invalid = form.querySelector('[aria-invalid="true"]') || controlsFor(form)
      .find(control => !control.validity.valid);
    if (!(invalid instanceof HTMLElement)) return;
    invalid.focus({ preventScroll: true });
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    invalid.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
  };

  document.querySelectorAll("[data-form-workspace]").forEach(form => {
    const controls = controlsFor(form);
    const status = form.querySelector("[data-form-status]");
    const stateLabel = form.querySelector("[data-form-state]");
    const stateDetail = form.querySelector("[data-form-state-detail]");
    const progress = form.querySelector("[data-form-progress]");
    const progressValue = form.querySelector("[data-form-progress-value]");
    const filledCount = form.querySelector("[data-form-filled-count]");
    const ring = form.querySelector("[data-form-ring]");
    const ringValue = form.querySelector("[data-form-ring-value]");
    const progressCopy = form.querySelector("[data-form-progress-copy]");
    const characterCounters = [...form.querySelectorAll("[data-form-character-count]")];
    const submitLabels = [...form.querySelectorAll("[data-form-submit-label]")];
    const initialSubmitLabels = new Map(submitLabels.map(label => [label, label.textContent]));
    const cancelUrl = form.dataset.cancelUrl || "/dashboard";
    const isEdit = form.dataset.formMode === "edit";
    let initialSnapshot = formSnapshot(form);
    let dirty = false;
    let submitting = false;
    let leaving = false;
    let submitLockTimer = 0;

    const setStatus = (state, label, detail) => {
      if (status) status.dataset.state = state;
      if (stateLabel) stateLabel.textContent = label;
      if (stateDetail) stateDetail.textContent = detail;
    };

    const updateProgress = () => {
      const filled = controls.filter(isFilled).length;
      const essential = controls.filter(control => control.required);
      const essentialFilled = essential.filter(isFilled).length;
      const percentage = essential.length
        ? Math.round((essentialFilled / essential.length) * 100)
        : 100;
      if (progress) progress.value = percentage;
      if (progressValue) progressValue.textContent = percentage + "%";
      if (filledCount) filledCount.textContent = filled + " de " + controls.length;
      if (ring) ring.style.setProperty("--form-progress", percentage + "%");
      if (ringValue) ringValue.textContent = percentage + "%";
      if (progressCopy) {
        progressCopy.textContent = percentage === 100
          ? "Campos essenciais completos. Confirmem os detalhes antes de guardar."
          : percentage >= 50
            ? "O essencial está bem encaminhado. Completem os campos assinalados."
            : "Comecem pelos dados indispensáveis. Os restantes podem ficar para depois.";
      }
    };

    const updateCharacterCount = control => {
      if (!(control instanceof HTMLTextAreaElement)) return;
      const counter = control.closest("[data-form-field]")?.querySelector("[data-form-character-count]");
      if (!counter) return;
      const count = control.value.length;
      counter.textContent = count + (count === 1 ? " carácter" : " caracteres");
    };

    const updateDirtyState = () => {
      dirty = formSnapshot(form) !== initialSnapshot;
      if (submitting) return;
      if (dirty) {
        setStatus("dirty", "Alterações por guardar", "Guardem para disponibilizar aos dois");
      } else {
        setStatus(
          "clean",
          isEdit ? "Tudo guardado" : "Pronto para preencher",
          isEdit ? "Sem alterações pendentes" : "Os dados só serão enviados ao guardar",
        );
      }
    };

    const validateForm = () => {
      const valid = form.checkValidity();
      if (valid) return true;
      controls.forEach(control => {
        if (!control.validity.valid) validateControl(control, true);
      });
      setStatus("invalid", "Faltam alguns detalhes", "Revejam os campos assinalados");
      focusFirstInvalid(form);
      return false;
    };

    const confirmCancel = () => {
      if (dirty && !window.confirm("Existem alterações por guardar. Querem sair sem as guardar?")) {
        return false;
      }
      leaving = true;
      form.removeAttribute("data-motion-dirty");
      return true;
    };

    controls.forEach(control => {
      if (control.matches("[data-auto-resize]")) resizeTextarea(control);
      updateCharacterCount(control);
      control.addEventListener("input", () => {
        if (control.matches("[data-auto-resize]")) resizeTextarea(control);
        updateCharacterCount(control);
        if (control.getAttribute("aria-invalid") === "true") validateControl(control, true);
        else control.setCustomValidity("");
        updateProgress();
        updateDirtyState();
      });
      control.addEventListener("change", () => {
        validateControl(control, control.getAttribute("aria-invalid") === "true");
        updateProgress();
        updateDirtyState();
      });
      control.addEventListener("blur", () => validateControl(control, true));
      control.addEventListener("invalid", () => validateControl(control, true));
    });

    const formPage = form.closest("[data-form-page]") || form;
    formPage.querySelectorAll("[data-form-cancel]").forEach(link => {
      link.addEventListener("click", event => {
        if (!confirmCancel()) event.preventDefault();
      });
    });

    document.addEventListener("keydown", event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (validateForm()) form.requestSubmit(form.querySelector("[data-form-submit]"));
        return;
      }
      if (event.key !== "Escape" || event.defaultPrevented || document.querySelector("dialog[open]")) return;
      event.preventDefault();
      if (confirmCancel()) window.location.assign(cancelUrl);
    });

    const releaseSubmitLock = () => {
      if (submitLockTimer) {
        window.clearTimeout(submitLockTimer);
        submitLockTimer = 0;
      }
      if (!submitting) return;
      submitting = false;
      form.setAttribute("aria-busy", "false");
      initialSubmitLabels.forEach((label, element) => {
        element.textContent = label;
      });
      updateDirtyState();
    };

    form.addEventListener("submit", event => {
      if (!validateForm()) {
        event.preventDefault();
        return;
      }
      submitting = true;
      dirty = false;
      form.setAttribute("aria-busy", "true");
      submitLabels.forEach(label => {
        label.textContent = "A guardar…";
      });
      setStatus("saving", "A guardar…", "A enviar diretamente para a base de dados");
      // Safety net: if a slow/dropped connection prevents the expected page
      // navigation, this releases the form instead of leaving it stuck on
      // "A guardar…" forever with the unsaved-changes warning silently
      // disabled.
      submitLockTimer = window.setTimeout(releaseSubmitLock, SUBMIT_LOCK_TIMEOUT_MS);
    });

    window.addEventListener("beforeunload", event => {
      if (!dirty || submitting || leaving) return;
      event.preventDefault();
      event.returnValue = "";
    });

    window.addEventListener("pageshow", () => {
      if (submitLockTimer) {
        window.clearTimeout(submitLockTimer);
        submitLockTimer = 0;
      }
      if (submitting) initialSnapshot = formSnapshot(form);
      submitting = false;
      leaving = false;
      form.setAttribute("aria-busy", "false");
      initialSubmitLabels.forEach((label, element) => {
        element.textContent = label;
      });
      characterCounters.forEach(counter => {
        const textarea = counter.closest("[data-form-field]")?.querySelector("textarea");
        if (textarea) updateCharacterCount(textarea);
      });
      updateProgress();
      updateDirtyState();
    });

    updateProgress();
    updateDirtyState();
  });
})();
