(() => {
  "use strict";

  const collator = new Intl.Collator("pt-PT", {
    numeric: true,
    sensitivity: "base",
  });

  const normalise = (value) => String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-PT")
    .trim();

  const pluralise = (count) => count + " " + (count === 1 ? "registo" : "registos");

  const initialiseWorkspace = (root) => {
    const items = Array.from(root.querySelectorAll("[data-utility-item]"));
    const list = root.querySelector("[data-utility-list]");
    const search = root.querySelector("[data-utility-search]");
    const sortSelect = root.querySelector("[data-utility-sort-select]");
    const summary = root.querySelector("[data-utility-summary]");
    const results = root.querySelector("[data-utility-results]");
    const empty = root.querySelector("[data-utility-empty]");
    const clearButtons = root.querySelectorAll("[data-utility-clear], [data-utility-empty-clear]");
    const originalPosition = new Map(items.map((item, index) => [item, index]));
    let activeSort = { key: "original", direction: "asc" };

    if (!items.length || !list || !search) {
      return;
    }

    root.querySelectorAll("[data-enhanced-only]").forEach((element) => {
      element.hidden = false;
    });
    root.querySelectorAll("[data-utility-sort-key]").forEach((button) => {
      button.disabled = false;
    });
    root.classList.add("is-enhanced");

    const searchValue = (item) => {
      const values = Object.values(item.dataset).join(" ");
      return normalise(values + " " + (item.textContent || ""));
    };

    const visibleItems = () => items.filter((item) => !item.hidden);

    const updateSummary = () => {
      const visible = visibleItems().length;
      const total = items.length;
      if (summary) {
        summary.textContent = visible === total
          ? pluralise(visible) + " apresentados"
          : pluralise(visible) + " de " + total;
      }
      const hasQuery = Boolean(normalise(search.value));
      root.querySelectorAll("[data-utility-clear]").forEach((button) => {
        button.hidden = !hasQuery;
      });
      if (results) {
        results.hidden = visible === 0;
      }
      if (empty) {
        empty.hidden = visible !== 0;
      }
      root.dataset.resultsState = visible === 0
        ? "empty"
        : hasQuery
          ? "filtered"
          : "complete";
    };

    const filterItems = () => {
      const terms = normalise(search.value).split(/\s+/).filter(Boolean);
      items.forEach((item) => {
        const haystack = searchValue(item);
        item.hidden = !terms.every((term) => haystack.includes(term));
      });
      updateSummary();
    };

    const comparableValue = (item, key) => {
      if (key === "original") {
        return originalPosition.get(item) || 0;
      }
      if (key === "timestamp") {
        const value = Date.parse(item.dataset.timestamp || "");
        return Number.isNaN(value) ? 0 : value;
      }
      return normalise(item.dataset[key]);
    };

    const updateSortIndicators = () => {
      root.querySelectorAll("[data-utility-sort-heading]").forEach((heading) => {
        const isActive = heading.dataset.utilitySortHeading === activeSort.key;
        heading.setAttribute(
          "aria-sort",
          isActive ? (activeSort.direction === "asc" ? "ascending" : "descending") : "none",
        );
        const indicator = heading.querySelector("[data-utility-sort-key] span");
        if (indicator) {
          indicator.textContent = isActive
            ? (activeSort.direction === "asc" ? "↑" : "↓")
            : "↕";
        }
      });
      if (sortSelect) {
        const value = activeSort.key + ":" + activeSort.direction;
        const matchingOption = Array.from(sortSelect.options)
          .find((option) => option.value === value);
        if (matchingOption) {
          sortSelect.value = matchingOption.value;
        }
      }
    };

    const sortItems = (key, direction) => {
      activeSort = { key, direction };
      const sorted = [...items].sort((left, right) => {
        const leftValue = comparableValue(left, key);
        const rightValue = comparableValue(right, key);
        const comparison = typeof leftValue === "number"
          ? leftValue - rightValue
          : collator.compare(leftValue, rightValue);
        if (comparison === 0) {
          return (originalPosition.get(left) || 0) - (originalPosition.get(right) || 0);
        }
        return direction === "desc" ? comparison * -1 : comparison;
      });
      sorted.forEach((item) => list.append(item));
      updateSortIndicators();
    };

    search.addEventListener("input", filterItems);

    clearButtons.forEach((button) => {
      button.addEventListener("click", () => {
        search.value = "";
        filterItems();
        search.focus({ preventScroll: true });
      });
    });

    if (sortSelect) {
      sortSelect.addEventListener("change", () => {
        const [key, direction] = sortSelect.value.split(":");
        sortItems(key, direction);
      });
    }

    root.querySelectorAll("[data-utility-sort-key]").forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.utilitySortKey;
        const direction = activeSort.key === key && activeSort.direction === "asc"
          ? "desc"
          : "asc";
        sortItems(key, direction);
      });
    });

    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const isTyping = target instanceof HTMLElement
        && (target.matches("input, textarea, select") || target.isContentEditable);
      if (event.key === "/" && !isTyping && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        search.focus({ preventScroll: true });
      }
      if (event.key === "Escape" && document.activeElement === search && search.value) {
        search.value = "";
        filterItems();
      }
    });

    filterItems();
    updateSortIndicators();
  };

  document.querySelectorAll("[data-utility-workspace]").forEach(initialiseWorkspace);
})();
