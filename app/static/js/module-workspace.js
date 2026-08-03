(() => {
  "use strict";

  const densityKey = "lv-module-density";
  const validDensities = new Set(["comfortable", "compact"]);
  const collator = new Intl.Collator("pt-PT", { numeric: true, sensitivity: "base" });

  const normalize = value => String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-PT")
    .trim();

  const storedDensity = () => {
    try {
      const value = window.localStorage.getItem(densityKey);
      return validDensities.has(value) ? value : "comfortable";
    } catch (_error) {
      return "comfortable";
    }
  };

  const saveDensity = value => {
    try {
      window.localStorage.setItem(densityKey, value);
    } catch (_error) {
      // Visual preference is optional in private browsing.
    }
  };

  const initialize = workspace => {
    const isComplete = workspace.dataset.listComplete === "true";
    const form = workspace.querySelector("[data-module-search-form]");
    const input = workspace.querySelector("[data-module-search-input]");
    const clearButton = workspace.querySelector("[data-module-search-clear]");
    const rowsContainer = workspace.querySelector("[data-module-rows]");
    const rows = [...workspace.querySelectorAll("[data-module-row]")];
    const count = workspace.querySelector("[data-visible-count]");
    const countLabel = workspace.querySelector("[data-count-label]");
    const filterEmpty = workspace.querySelector("[data-filter-empty]");
    const emptyClear = workspace.querySelector("[data-filter-empty-clear]");
    const selectVisible = workspace.querySelector("[data-select-visible]");
    const selectionSummary = workspace.querySelector("[data-selection-summary]");
    const selectedCount = workspace.querySelector("[data-selected-count]");
    const clearSelection = workspace.querySelector("[data-clear-selection]");
    const openSelected = workspace.querySelector("[data-open-selected]");
    const densityControls = workspace.querySelector("[data-density-controls]");
    const statusFilter = workspace.querySelector("[data-module-status-filter]");
    const statusFilterControl = workspace.querySelector("[data-status-filter-control]");
    const sortSelect = workspace.querySelector("[data-module-sort-select]");
    const sortSelectControl = workspace.querySelector("[data-sort-select-control]");
    const sortButtons = [...workspace.querySelectorAll("[data-sort]")];
    let sortKey = "updated";
    let sortDirection = "desc";

    document.documentElement.classList.add("module-workspace-ready");
    workspace.querySelectorAll("[data-selection-cell]").forEach(cell => {
      cell.hidden = false;
    });
    sortButtons.forEach(button => {
      button.disabled = false;
    });
    if (densityControls) densityControls.hidden = false;
    if (sortSelect && sortSelectControl) {
      sortSelect.disabled = false;
      sortSelectControl.hidden = false;
    }

    const statuses = [...new Set(rows
      .map(row => String(row.dataset.sortStatus || "").trim())
      .filter(Boolean))]
      .sort((left, right) => collator.compare(left, right));
    if (statusFilter && statusFilterControl && statuses.length) {
      statuses.forEach(value => {
        const option = document.createElement("option");
        option.value = normalize(value);
        option.textContent = value;
        statusFilter.append(option);
      });
      statusFilter.disabled = false;
      statusFilterControl.hidden = false;
    }

    const setDensity = (density, persist = false) => {
      const value = validDensities.has(density) ? density : "comfortable";
      workspace.dataset.density = value;
      workspace.querySelectorAll("[data-density]").forEach(button => {
        button.setAttribute("aria-pressed", button.dataset.density === value ? "true" : "false");
      });
      if (persist) saveDensity(value);
    };

    const visibleRows = () => rows.filter(row => !row.hidden);
    const selectedRows = () => rows.filter(row => row.querySelector("[data-row-select]")?.checked);

    const updateSelection = () => {
      rows.forEach(row => {
        row.classList.toggle("is-selected", Boolean(row.querySelector("[data-row-select]")?.checked));
      });
      const selected = selectedRows().length;
      if (selectedCount) selectedCount.textContent = String(selected);
      if (selectionSummary) selectionSummary.hidden = selected === 0;
      if (selectVisible) {
        const visible = visibleRows();
        const checked = visible.filter(row => row.querySelector("[data-row-select]")?.checked).length;
        selectVisible.checked = visible.length > 0 && checked === visible.length;
        selectVisible.indeterminate = checked > 0 && checked < visible.length;
      }
    };

    const updateCount = () => {
      const visible = visibleRows().length;
      if (count) count.textContent = String(visible);
      if (countLabel) countLabel.textContent = visible === 1 ? "registo visível" : "registos visíveis";
      if (filterEmpty) filterEmpty.hidden = visible > 0;
      const table = workspace.querySelector(".module-table-scroll") || workspace.querySelector(".module-table");
      if (table) table.hidden = visible === 0;
      if (clearButton) clearButton.hidden = !input?.value;
      updateSelection();
    };

    const filterRows = () => {
      const terms = isComplete
        ? normalize(input?.value).split(/\s+/).filter(Boolean)
        : [];
      const selectedStatus = normalize(statusFilter?.value);
      rows.forEach(row => {
        const matchesSearch = terms.every(term => normalize(row.dataset.search).includes(term));
        const matchesStatus = !selectedStatus
          || normalize(row.dataset.sortStatus) === selectedStatus;
        const matches = matchesSearch && matchesStatus;
        row.hidden = !matches;
        if (!matches) {
          const checkbox = row.querySelector("[data-row-select]");
          if (checkbox) checkbox.checked = false;
        }
      });
      updateCount();
    };

    const sortValue = (row, key, kind) => {
      const raw = row.dataset[`sort${key.charAt(0).toUpperCase()}${key.slice(1)}`] || "";
      if (kind === "number") return Number.parseFloat(raw) || 0;
      if (kind === "date") return Date.parse(raw) || 0;
      return normalize(raw);
    };

    const sortRows = (key, kind, requestedDirection = null) => {
      if (!rowsContainer) return;
      sortDirection = requestedDirection
        || (sortKey === key && sortDirection === "asc" ? "desc" : "asc");
      sortKey = key;
      const factor = sortDirection === "asc" ? 1 : -1;
      [...rows].sort((left, right) => {
        const first = sortValue(left, key, kind);
        const second = sortValue(right, key, kind);
        const compared = typeof first === "number" ? first - second : collator.compare(first, second);
        return compared * factor;
      }).forEach(row => rowsContainer.append(row));

      sortButtons.forEach(button => {
        const active = button.dataset.sort === key;
        const header = button.closest("[data-sort-header]");
        header?.setAttribute("aria-sort", active ? (sortDirection === "asc" ? "ascending" : "descending") : "none");
        const indicator = button.querySelector("[data-sort-indicator]");
        if (indicator) indicator.textContent = active ? (sortDirection === "asc" ? "↑" : "↓") : "↕";
      });
      if (sortSelect) {
        const option = [...sortSelect.options].find(item => {
          const [optionKey, optionKind, optionDirection] = item.value.split(":");
          return optionKey === key && optionKind === kind && optionDirection === sortDirection;
        });
        if (option) sortSelect.value = option.value;
      }
    };

    const clearSearch = () => {
      if (!input) return;
      if (!isComplete && input.value) {
        const destination = workspace.dataset.resetUrl || window.location.pathname;
        if (window.LVMotion?.navigate) window.LVMotion.navigate(destination, { kind: "subtle" });
        else window.location.assign(destination);
        return;
      }
      input.value = "";
      if (statusFilter) statusFilter.value = "";
      filterRows();
      input.focus();
    };

    if (isComplete) {
      input?.addEventListener("input", filterRows);
      form?.addEventListener("submit", event => {
        event.preventDefault();
        filterRows();
      });
    } else if (clearButton && input?.value) {
      clearButton.hidden = false;
    }
    clearButton?.addEventListener("click", clearSearch);
    emptyClear?.addEventListener("click", clearSearch);
    statusFilter?.addEventListener("change", filterRows);
    sortSelect?.addEventListener("change", () => {
      const [key, kind, direction] = sortSelect.value.split(":");
      sortRows(key, kind, direction);
    });

    sortButtons.forEach(button => {
      button.addEventListener("click", () => sortRows(button.dataset.sort, button.dataset.sortKind));
    });
    workspace.querySelectorAll("[data-density]").forEach(button => {
      button.addEventListener("click", () => setDensity(button.dataset.density, true));
    });

    selectVisible?.addEventListener("change", () => {
      visibleRows().forEach(row => {
        const checkbox = row.querySelector("[data-row-select]");
        if (checkbox) checkbox.checked = selectVisible.checked;
      });
      updateSelection();
    });
    workspace.querySelectorAll("[data-row-select]").forEach(checkbox => {
      checkbox.addEventListener("change", updateSelection);
    });
    clearSelection?.addEventListener("click", () => {
      rows.forEach(row => {
        const checkbox = row.querySelector("[data-row-select]");
        if (checkbox) checkbox.checked = false;
      });
      updateSelection();
    });
    openSelected?.addEventListener("click", () => {
      const destination = selectedRows()
        .map(row => row.dataset.recordHref)
        .find(Boolean);
      if (!destination) return;
      if (window.LVMotion?.navigate) window.LVMotion.navigate(destination, { kind: "subtle" });
      else window.location.assign(destination);
    });

    rows.forEach(row => {
      row.addEventListener("keydown", event => {
        if (event.target !== row) return;
        if (event.key === " ") {
          event.preventDefault();
          const checkbox = row.querySelector("[data-row-select]");
          if (checkbox) checkbox.checked = !checkbox.checked;
          updateSelection();
        } else if (event.key === "Enter") {
          const edit = row.querySelector(".module-edit-button");
          if (edit) {
            event.preventDefault();
            edit.click();
          }
        }
      });
    });

    document.addEventListener("keydown", event => {
      const target = event.target;
      const isTyping = target instanceof HTMLInputElement
        || target instanceof HTMLTextAreaElement
        || target instanceof HTMLSelectElement
        || target?.isContentEditable;
      if (event.key === "/" && !isTyping && !event.ctrlKey && !event.metaKey && input) {
        event.preventDefault();
        input.focus();
      } else if (event.key === "Escape" && target === input && input.value && isComplete) {
        event.preventDefault();
        clearSearch();
      }
    });

    setDensity(storedDensity());
    updateCount();
  };

  document.querySelectorAll("[data-module-workspace]").forEach(initialize);
})();
