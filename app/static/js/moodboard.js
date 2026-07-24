(() => {
  "use strict";

  const root = document.querySelector("[data-moodboard-root]");
  const editor = document.querySelector("[data-moodboard-form]");
  const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum);
  const number = (value, fallback = 0) => {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const activateLoadedImages = scope => {
    scope.querySelectorAll("img").forEach(image => {
      const markLoaded = () => image.classList.add("is-loaded");
      if (image.complete && image.naturalWidth > 0) markLoaded();
      else image.addEventListener("load", markLoaded, { once: true });
      image.addEventListener("error", () => {
        image.classList.add("is-loaded", "has-error");
      }, { once: true });
    });
  };

  const setupEditorPreview = () => {
    if (!editor) return;
    const imageInput = editor.querySelector("[data-image-url]");
    const titleInput = editor.querySelector('input[name="title"]');
    const previewImage = editor.querySelector("[data-form-preview-image]");
    const placeholder = editor.querySelector("[data-form-preview-placeholder]");
    const caption = editor.querySelector("[data-form-preview-caption]");
    if (!imageInput || !previewImage || !placeholder || !caption) return;

    let updateTimer = 0;
    const showPlaceholder = () => {
      previewImage.hidden = true;
      placeholder.hidden = false;
    };
    const updateImage = () => {
      window.clearTimeout(updateTimer);
      updateTimer = window.setTimeout(() => {
        try {
          const value = new URL(imageInput.value);
          if (!["http:", "https:"].includes(value.protocol)) {
            showPlaceholder();
            return;
          }
          previewImage.onload = () => {
            previewImage.hidden = false;
            placeholder.hidden = true;
          };
          previewImage.onerror = showPlaceholder;
          previewImage.src = value.href;
        } catch {
          showPlaceholder();
        }
      }, 220);
    };
    imageInput.addEventListener("input", updateImage);
    titleInput?.addEventListener("input", () => {
      caption.textContent = titleInput.value.trim() || "A vossa inspiração";
    });
  };

  if (editor) {
    activateLoadedImages(editor);
    setupEditorPreview();
  }
  if (!root) return;

  activateLoadedImages(root);

  const toast = root.querySelector("[data-moodboard-toast]");
  let toastTimer = 0;
  const announce = message => {
    if (!toast) return;
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2400);
  };

  root.querySelectorAll("[data-favorite-form]").forEach(form => {
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const button = form.querySelector(".moodboard-favorite");
      if (!button || button.disabled) return;
      button.disabled = true;
      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "lv-moodboard",
            "Accept": "application/json",
          },
        });
        if (!response.ok) throw new Error("favorite");
        const result = await response.json();
        const favorite = Boolean(result.favorite);
        button.classList.toggle("is-favorite", favorite);
        button.classList.add("is-animating");
        button.setAttribute("aria-pressed", String(favorite));
        button.setAttribute(
          "aria-label",
          favorite ? "Retirar dos favoritos" : "Marcar como favorito",
        );
        const icon = button.querySelector("span");
        if (icon) icon.textContent = favorite ? "♥" : "♡";
        window.setTimeout(() => button.classList.remove("is-animating"), 320);
        announce(favorite ? "Guardado nos favoritos." : "Retirado dos favoritos.");
      } catch {
        announce("Não foi possível atualizar. Tentem novamente.");
      } finally {
        button.disabled = false;
      }
    });
  });

  const table = root.querySelector("[data-inspiration-table]");
  const layoutStatus = root.querySelector("[data-layout-status]");
  const csrfToken = table?.dataset.csrfToken || "";
  const notes = table ? [...table.querySelectorAll("[data-placement-url]")] : [];
  const saveTimers = new WeakMap();

  const noteState = note => ({
    x: number(note.dataset.x, 5),
    y: number(note.dataset.y, 5),
    rotation: number(note.dataset.rotation, 0),
    layer: Math.round(number(note.dataset.layer, 1)),
  });

  const applyNoteState = (note, state) => {
    const safe = {
      x: clamp(state.x, 0, 82),
      y: clamp(state.y, 0, 76),
      rotation: clamp(state.rotation, -6, 6),
      layer: clamp(Math.round(state.layer), 1, 10000),
    };
    note.dataset.x = safe.x.toFixed(2);
    note.dataset.y = safe.y.toFixed(2);
    note.dataset.rotation = safe.rotation.toFixed(2);
    note.dataset.layer = String(safe.layer);
    note.style.setProperty("--note-x", safe.x.toFixed(2));
    note.style.setProperty("--note-y", safe.y.toFixed(2));
    note.style.setProperty("--note-rotation", `${safe.rotation.toFixed(2)}deg`);
    note.style.setProperty("--note-layer", String(safe.layer));
    return safe;
  };

  const saveNote = async (note, quiet = false) => {
    const state = noteState(note);
    const body = new FormData();
    body.set("csrf_token", csrfToken);
    body.set("x_percent", state.x.toFixed(2));
    body.set("y_percent", state.y.toFixed(2));
    body.set("rotation_degrees", state.rotation.toFixed(2));
    body.set("layer", String(state.layer));
    note.classList.add("is-saving");
    if (layoutStatus) layoutStatus.textContent = "A guardar a organização…";
    try {
      const response = await fetch(note.dataset.placementUrl, {
        method: "POST",
        body,
        credentials: "same-origin",
        keepalive: true,
        headers: {
          "X-Requested-With": "lv-moodboard",
          "Accept": "application/json",
        },
      });
      if (!response.ok) throw new Error("placement");
      const result = await response.json();
      applyNoteState(note, {
        x: result.x,
        y: result.y,
        rotation: result.rotation,
        layer: result.layer,
      });
      note.classList.add("is-saved");
      window.setTimeout(() => note.classList.remove("is-saved"), 350);
      if (layoutStatus) layoutStatus.textContent = "Organização guardada.";
      if (!quiet) announce("Posição guardada.");
    } catch {
      if (layoutStatus) {
        layoutStatus.textContent = "Não foi possível guardar. Tentem novamente.";
      }
      announce("Não foi possível guardar a posição.");
    } finally {
      note.classList.remove("is-saving");
    }
  };

  const scheduleNoteSave = note => {
    window.clearTimeout(saveTimers.get(note));
    const timer = window.setTimeout(() => saveNote(note, true), 380);
    saveTimers.set(note, timer);
  };

  notes.forEach(note => {
    applyNoteState(note, noteState(note));
    const handle = note.querySelector("[data-drag-handle]");
    const rotateButton = note.querySelector("[data-rotate-note]");
    const frontButton = note.querySelector("[data-bring-front]");
    if (!handle || !table) return;

    let drag = null;
    const finishDrag = event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      drag = null;
      note.classList.remove("is-dragging");
      saveNote(note);
    };

    handle.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      event.preventDefault();
      const state = noteState(note);
      drag = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        x: state.x,
        y: state.y,
      };
      note.classList.add("is-dragging");
      handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener("pointermove", event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      event.preventDefault();
      const rect = table.getBoundingClientRect();
      applyNoteState(note, {
        ...noteState(note),
        x: drag.x + (((event.clientX - drag.startX) / rect.width) * 100),
        y: drag.y + (((event.clientY - drag.startY) / rect.height) * 100),
      });
    });
    handle.addEventListener("pointerup", finishDrag);
    handle.addEventListener("pointercancel", event => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      drag = null;
      note.classList.remove("is-dragging");
      saveNote(note, true);
    });
    handle.addEventListener("keydown", event => {
      const directions = {
        ArrowLeft: [-1, 0],
        ArrowRight: [1, 0],
        ArrowUp: [0, -1],
        ArrowDown: [0, 1],
      };
      if (!directions[event.key]) return;
      event.preventDefault();
      const step = event.shiftKey ? 5 : 1;
      const [horizontal, vertical] = directions[event.key];
      const state = noteState(note);
      applyNoteState(note, {
        ...state,
        x: state.x + (horizontal * step),
        y: state.y + (vertical * step),
      });
      scheduleNoteSave(note);
      if (layoutStatus) layoutStatus.textContent = "Posição ajustada. A guardar…";
    });

    rotateButton?.addEventListener("click", () => {
      const state = noteState(note);
      const nextRotation = state.rotation >= 5.8 ? -4.5 : state.rotation + 1.5;
      applyNoteState(note, {...state, rotation: nextRotation});
      saveNote(note);
    });
    frontButton?.addEventListener("click", () => {
      const highestLayer = Math.max(...notes.map(other => noteState(other).layer), 0);
      applyNoteState(note, {...noteState(note), layer: highestLayer + 1});
      saveNote(note);
    });
  });

  const dialog = root.querySelector("[data-moodboard-dialog]");
  const previewCards = [...root.querySelectorAll("[data-preview]")];
  const previewImage = dialog?.querySelector("[data-preview-image]");
  const previewTitle = dialog?.querySelector("[data-preview-title]");
  const previewCollection = dialog?.querySelector("[data-preview-collection]");
  const previewTags = dialog?.querySelector("[data-preview-tags]");
  const previewNotes = dialog?.querySelector("[data-preview-notes]");
  const previewSource = dialog?.querySelector("[data-preview-source]");
  const previewPosition = dialog?.querySelector("[data-preview-position]");
  const previousButton = dialog?.querySelector("[data-preview-previous]");
  const nextButton = dialog?.querySelector("[data-preview-next]");
  const closeButton = dialog?.querySelector("[data-preview-close]");
  let previewIndex = 0;
  let previewReturnFocus = null;
  let closeTimer = 0;

  const previewData = card => {
    try {
      return JSON.parse(card.dataset.preview);
    } catch {
      return {};
    }
  };

  const showPreview = index => {
    if (!dialog || !previewCards.length) return;
    previewIndex = (index + previewCards.length) % previewCards.length;
    const data = previewData(previewCards[previewIndex]);
    if (previewImage) {
      previewImage.src = data.image || "";
      previewImage.alt = data.title || "Inspiração";
      previewImage.classList.remove("is-preview-changing");
      void previewImage.offsetWidth;
      previewImage.classList.add("is-preview-changing");
    }
    if (previewTitle) previewTitle.textContent = data.title || "Inspiração";
    if (previewCollection) previewCollection.textContent = data.collection || "";
    if (previewTags) {
      previewTags.textContent = data.tags || "";
      previewTags.hidden = !data.tags;
    }
    if (previewNotes) {
      previewNotes.textContent = data.notes || "";
      previewNotes.hidden = !data.notes;
    }
    if (previewSource) {
      previewSource.href = data.source || "#";
      previewSource.hidden = !data.source;
    }
    if (previewPosition) {
      previewPosition.textContent = `${previewIndex + 1} de ${previewCards.length}`;
    }
    if (previousButton) previousButton.hidden = previewCards.length < 2;
    if (nextButton) nextButton.hidden = previewCards.length < 2;
  };

  root.querySelectorAll("[data-preview-open]").forEach(trigger => {
    trigger.addEventListener("click", () => {
      const card = trigger.closest("[data-preview]");
      const index = previewCards.indexOf(card);
      if (!dialog || index < 0) return;
      previewReturnFocus = trigger;
      showPreview(index);
      if (typeof dialog.showModal === "function") {
        dialog.classList.add("is-opening");
        dialog.showModal();
        window.requestAnimationFrame(() => {
          window.requestAnimationFrame(() => dialog.classList.remove("is-opening"));
        });
      }
      else window.open(previewData(card).image, "_blank", "noopener");
    });
  });
  const closePreview = () => {
    if (!dialog?.open || dialog.classList.contains("is-closing")) return;
    dialog.classList.add("is-closing");
    const fullMotion = window.LVMotion?.getMode().effective === "full";
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(() => dialog.close(), fullMotion ? 180 : 1);
  };
  previousButton?.addEventListener("click", () => showPreview(previewIndex - 1));
  nextButton?.addEventListener("click", () => showPreview(previewIndex + 1));
  closeButton?.addEventListener("click", closePreview);
  dialog?.addEventListener("click", event => {
    if (event.target === dialog) closePreview();
  });
  dialog?.addEventListener("cancel", event => {
    event.preventDefault();
    closePreview();
  });
  dialog?.addEventListener("close", () => {
    window.clearTimeout(closeTimer);
    dialog.classList.remove("is-opening", "is-closing");
    if (previewReturnFocus instanceof HTMLElement) previewReturnFocus.focus();
    previewReturnFocus = null;
  });
  document.addEventListener("keydown", event => {
    if (!dialog?.open) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPreview(previewIndex - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      showPreview(previewIndex + 1);
    }
  });
})();
