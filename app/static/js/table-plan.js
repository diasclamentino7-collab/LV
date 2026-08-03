(function () {
  "use strict";

  var workspace = document.querySelector("[data-table-plan]");
  if (!workspace) {
    return;
  }

  document.documentElement.classList.add("table-plan-enhanced");

  var apiUrl = workspace.getAttribute("data-guest-api") || "/api/guests";
  var csrfToken = workspace.getAttribute("data-csrf-token") || "";
  var searchInput = workspace.querySelector("[data-table-search]");
  var zoneFilter = workspace.querySelector("[data-table-zone-filter]");
  var shapeFilter = workspace.querySelector("[data-table-shape-filter]");
  var capacityFilter = workspace.querySelector("[data-table-capacity-filter]");
  var clearButton = workspace.querySelector("[data-table-clear]");
  var emptyClearButton = workspace.querySelector("[data-table-empty-clear]");
  var filterEmpty = workspace.querySelector("[data-table-filter-empty]");
  var visibleCount = workspace.querySelector("[data-table-visible-count]");
  var unassignedList = workspace.querySelector("[data-unassigned-list]");
  var unassignedPanel = workspace.querySelector("[data-unassigned-panel]");
  var liveState = workspace.querySelector("[data-table-live-state]");
  var celebration = workspace.querySelector("[data-table-celebration]");
  var draggedItem = null;
  var savePromises = new Map();
  var channel = null;
  var refreshInProgress = false;
  var lastUnknownNotice = "";

  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-PT")
      .trim();
  }

  function tableIdentityKey(value) {
    return String(value || "")
      .trim()
      .replace(/\s+/g, " ")
      .toLocaleLowerCase("pt-PT");
  }

  function canonicalTableName(value) {
    var rawValue = String(value || "");
    if (!tableIdentityKey(rawValue)) {
      return "";
    }
    var key = tableIdentityKey(rawValue);
    var card = allTableCards().find(function (candidate) {
      return tableIdentityKey(candidate.dataset.tableName) === key;
    });
    return card ? String(card.dataset.tableName || "") : null;
  }

  function allTableCards() {
    return Array.prototype.slice.call(
      workspace.querySelectorAll("[data-table-card]")
    );
  }

  function allGuestItems() {
    return Array.prototype.slice.call(
      workspace.querySelectorAll("[data-table-guest]")
    );
  }

  function tableCardByName(name) {
    var target = tableIdentityKey(name);
    if (!target) {
      return null;
    }
    return allTableCards().find(function (card) {
      return tableIdentityKey(card.dataset.tableName) === target;
    }) || null;
  }

  function assignmentControl(item) {
    return item && item.querySelector("[data-table-assignment]");
  }

  function tableNames() {
    return allTableCards().map(function (card) {
      return card.dataset.tableName || "";
    }).filter(Boolean);
  }

  function motionMode() {
    if (window.LVMotion) {
      return window.LVMotion.getMode().effective;
    }
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "reduced"
      : "full";
  }

  function toast(message, kind) {
    if (window.LVMotion && message) {
      window.LVMotion.toast(message, {
        kind: kind || "success",
        duration: kind === "error" ? 5200 : 3000,
      });
    }
  }

  function setLive(message, state) {
    if (!liveState) {
      return;
    }
    var textNode = Array.prototype.slice.call(liveState.childNodes).find(
      function (node) {
        return node.nodeType === Node.TEXT_NODE;
      }
    );
    if (textNode) {
      textNode.textContent = " " + message;
    } else {
      liveState.appendChild(document.createTextNode(" " + message));
    }
    liveState.classList.toggle("is-saving", state === "saving");
    liveState.classList.toggle("is-error", state === "error");
  }

  function errorMessage(payload, fallback) {
    if (payload && typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload && Array.isArray(payload.detail) && payload.detail.length) {
      var first = payload.detail[0];
      if (first && typeof first.msg === "string") {
        return first.msg.replace(/^Value error,\s*/i, "");
      }
    }
    return fallback || "Não foi possível guardar esta alteração.";
  }

  async function jsonRequest(url, options) {
    var settings = options || {};
    var headers = new Headers(settings.headers || {});
    headers.set("Accept", "application/json");
    headers.set("X-CSRF-Token", csrfToken);
    if (settings.body) {
      headers.set("Content-Type", "application/json");
    }
    var response = await window.fetch(url, {
      method: settings.method || "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: headers,
      body: settings.body,
    });
    var payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (response.status === 401) {
      window.location.assign("/login");
      throw new Error("Session expired");
    }
    if (!response.ok) {
      var failure = new Error(errorMessage(payload));
      failure.status = response.status;
      failure.payload = payload;
      throw failure;
    }
    return payload;
  }

  function initials(name) {
    var parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) {
      return "?";
    }
    return (parts[0].charAt(0) + (parts.length > 1 ? parts[parts.length - 1].charAt(0) : "")).toLocaleUpperCase("pt-PT");
  }

  function element(tagName, className, textValue) {
    var node = document.createElement(tagName);
    if (className) {
      node.className = className;
    }
    if (textValue !== undefined) {
      node.textContent = String(textValue);
    }
    return node;
  }

  function buildAssignmentSelect(guest, currentTable) {
    var label = element("label", "table-assignment-field");
    var hiddenLabel = element(
      "span",
      "visually-hidden",
      "Mesa atribuída a " + String(guest.name || "convidado")
    );
    var select = document.createElement("select");
    select.setAttribute("data-table-assignment", "");
    select.setAttribute(
      "aria-label",
      "Alterar mesa de " + String(guest.name || "convidado")
    );
    var emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "Sem mesa";
    select.appendChild(emptyOption);
    tableNames().forEach(function (name) {
      var option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      select.appendChild(option);
    });
    select.value = currentTable || "";
    label.append(hiddenLabel, select);
    return label;
  }

  function appendGuestTag(container, value, kind) {
    if (!value) {
      return;
    }
    var tag = element("span", "", value);
    if (kind === "rsvp") {
      tag.dataset.rsvp = normalize(value);
    }
    container.appendChild(tag);
  }

  function createGuestItem(guest) {
    var currentTable = String(guest.table_name || "");
    var item = element("li", "table-guest-item");
    item.setAttribute("data-table-guest", "");
    item.dataset.guestId = String(guest.id);
    item.dataset.guestName = String(guest.name || "Convidado");
    item.dataset.guestSide = String(guest.side || "");
    item.dataset.guestGroup = String(guest.age_group || "");
    item.dataset.guestRsvp = String(guest.rsvp_status || "");
    item.dataset.currentTable = currentTable;
    item.dataset.updatedAt = String(guest.updated_at || "");

    var grip = element("span", "table-guest-grip", "⋮⋮");
    grip.setAttribute("aria-hidden", "true");
    grip.title = "Arrastar para outra mesa";

    var avatar = element("a", "table-guest-avatar", initials(guest.name));
    avatar.href = "/guests/" + encodeURIComponent(guest.id) + "/edit";
    avatar.setAttribute(
      "aria-label",
      "Abrir detalhes de " + String(guest.name || "convidado")
    );

    var copy = element("div", "table-guest-copy");
    var nameLink = document.createElement("a");
    nameLink.href = avatar.href;
    nameLink.appendChild(element("strong", "", guest.name || "Convidado"));
    var tags = document.createElement("p");
    appendGuestTag(tags, guest.side, "side");
    appendGuestTag(tags, guest.age_group, "group");
    appendGuestTag(tags, guest.rsvp_status, "rsvp");
    copy.append(nameLink, tags);

    var state = element("small", "table-guest-save-state", "Guardado");
    state.setAttribute("data-table-save-state", "");
    state.setAttribute("aria-live", "polite");
    item.append(grip, avatar, copy, buildAssignmentSelect(guest, currentTable), state);
    setupGuestItem(item);
    return item;
  }

  function setGuestState(item, state, message) {
    var indicator = item.querySelector("[data-table-save-state]");
    item.classList.toggle("is-saving", state === "saving");
    item.classList.toggle("is-save-error", state === "error");
    item.setAttribute("aria-busy", state === "saving" ? "true" : "false");
    if (indicator) {
      indicator.textContent = message || "";
    }
  }

  function sortGuestList(list) {
    if (!list) {
      return;
    }
    var items = Array.prototype.slice.call(
      list.querySelectorAll(":scope > [data-table-guest]")
    );
    items.sort(function (first, second) {
      return String(first.dataset.guestName || "").localeCompare(
        String(second.dataset.guestName || ""),
        "pt-PT",
        { sensitivity: "base" }
      );
    });
    items.forEach(function (item) {
      list.appendChild(item);
    });
  }

  function guestItemsInCard(card) {
    return card
      ? Array.prototype.slice.call(
          card.querySelectorAll("[data-table-roster] > [data-table-guest]")
        )
      : [];
  }

  function createSeat(guestItem, index, total) {
    var seat = element(
      "li",
      "table-seat" + (guestItem ? " is-occupied" : "")
    );
    seat.style.setProperty("--seat-index", String(index));
    seat.style.setProperty("--seat-total", String(total));
    var seatNumber = index + 1;
    var content;
    if (guestItem) {
      seat.dataset.seatOccupantId = guestItem.dataset.guestId;
      content = document.createElement("a");
      content.href =
        "/guests/" + encodeURIComponent(guestItem.dataset.guestId) + "/edit";
      content.title =
        "Lugar " + seatNumber + " · " + guestItem.dataset.guestName;
      content.setAttribute(
        "aria-label",
        "Lugar " + seatNumber + ", " + guestItem.dataset.guestName
      );
    } else {
      content = document.createElement("span");
      content.title = "Lugar " + seatNumber + " livre";
      content.setAttribute("aria-label", "Lugar " + seatNumber + " livre");
    }
    content.appendChild(element("small", "", seatNumber));
    var seatCopy = element(
      "strong",
      "",
      guestItem ? initials(guestItem.dataset.guestName) : "+"
    );
    if (!guestItem) {
      seatCopy.setAttribute("aria-hidden", "true");
    }
    content.appendChild(seatCopy);
    seat.appendChild(content);
    return seat;
  }

  function renderTableSeats(card) {
    if (!card) {
      return;
    }
    var ring = card.querySelector("[data-seat-ring]");
    if (!ring) {
      return;
    }
    var guests = guestItemsInCard(card);
    var capacity = Math.max(0, Number(card.dataset.tableCapacity) || 0);
    var totalToRender = Math.min(Math.max(capacity, guests.length, 1), 16);
    var fragment = document.createDocumentFragment();
    for (var index = 0; index < totalToRender; index += 1) {
      fragment.appendChild(createSeat(guests[index] || null, index, totalToRender));
    }
    ring.replaceChildren(fragment);
    var overflow = card.querySelector("[data-seat-overflow]");
    if (overflow) {
      var overflowCount = guests.length > 16
        ? guests.length - 16
        : Math.max(0, capacity - 16);
      overflow.hidden = overflowCount < 1;
      overflow.textContent = guests.length > 16
        ? "+" + overflowCount + " pessoas no rol"
        : "+" + overflowCount + " lugares adicionais";
    }
  }

  function updateTableCard(card) {
    if (!card) {
      return;
    }
    var occupancy = guestItemsInCard(card).length;
    var capacity = Math.max(0, Number(card.dataset.tableCapacity) || 0);
    var available = Math.max(0, capacity - occupancy);
    var isOver = occupancy > capacity;
    var isFull = capacity > 0 && occupancy === capacity;
    card.classList.toggle("is-over-capacity", isOver);
    card.classList.toggle("is-full", !isOver && isFull);

    card.querySelectorAll("[data-table-occupancy], [data-roster-count]").forEach(
      function (elementNode) {
        elementNode.textContent = String(occupancy);
      }
    );
    var label = card.querySelector("[data-table-capacity-label]");
    var state = card.querySelector("[data-table-capacity-state]");
    if (label) {
      label.textContent = isOver
        ? String(occupancy - capacity) + " acima da capacidade"
        : isFull
          ? "Mesa completa"
          : String(available) + (available === 1 ? " lugar livre" : " lugares livres");
    }
    if (state) {
      state.textContent = isOver
        ? "Revejam esta distribuição"
        : isFull
          ? "Distribuição concluída"
          : "Disponível";
    }
    var progress = card.querySelector("[role='progressbar']");
    if (progress) {
      progress.setAttribute(
        "aria-valuemax",
        String(Math.max(capacity, occupancy, 1))
      );
      progress.setAttribute("aria-valuenow", String(occupancy));
      var fill = progress.querySelector("i");
      if (fill) {
        fill.style.width = String(
          Math.min(100, capacity ? (occupancy / capacity) * 100 : 100)
        ) + "%";
      }
    }
    var empty = card.querySelector("[data-table-roster-empty]");
    if (empty) {
      empty.hidden = occupancy > 0;
    }
    renderTableSeats(card);
  }

  function setNumber(selector, value) {
    workspace.querySelectorAll(selector).forEach(function (target) {
      var nextValue = String(value);
      if (target.textContent !== nextValue) {
        if (window.LVMotion && target.hasAttribute("data-motion-number")) {
          window.LVMotion.update(target, nextValue, { type: "number" });
        } else {
          target.textContent = nextValue;
        }
      }
    });
  }

  function updateStats() {
    var cards = allTableCards();
    var assigned = cards.reduce(function (total, card) {
      return total + guestItemsInCard(card).length;
    }, 0);
    var unassigned = unassignedList
      ? unassignedList.querySelectorAll(":scope > [data-table-guest]").length
      : 0;
    var capacity = cards.reduce(function (total, card) {
      return total + Math.max(0, Number(card.dataset.tableCapacity) || 0);
    }, 0);
    var available = cards.reduce(function (total, card) {
      return total + Math.max(
        0,
        (Number(card.dataset.tableCapacity) || 0) - guestItemsInCard(card).length
      );
    }, 0);
    var occupancy = capacity
      ? Math.round((assigned / capacity) * 1000) / 10
      : 0;
    setNumber('[data-plan-stat="table_count"]', cards.length);
    setNumber('[data-plan-stat="assigned_guests"]', assigned);
    setNumber('[data-plan-stat="unassigned_guests"]', unassigned);
    setNumber('[data-plan-stat="total_guests"]', assigned + unassigned);
    setNumber('[data-plan-stat="seats_available"]', available);
    setNumber('[data-plan-stat="seats_total"]', capacity);
    setNumber('[data-plan-stat="occupancy_percent"]', occupancy);
    setNumber("[data-map-assigned]", assigned);
    setNumber("[data-unassigned-count]", unassigned);
    var ring = workspace.querySelector(".table-plan-ring");
    if (ring) {
      ring.style.setProperty("--occupancy", String(Math.min(100, occupancy)));
    }
    var empty = workspace.querySelector("[data-unassigned-empty]");
    if (empty) {
      empty.hidden = unassigned > 0;
    }
  }

  function destinationList(tableName) {
    var canonicalName = canonicalTableName(tableName);
    if (canonicalName === "") {
      return unassignedList;
    }
    if (canonicalName === null) {
      return null;
    }
    var card = tableCardByName(canonicalName);
    return card ? card.querySelector("[data-table-roster]") : null;
  }

  function moveGuestElement(item, tableName) {
    var oldTableName = item.dataset.currentTable || "";
    var canonicalName = canonicalTableName(tableName);
    if (canonicalName === null) {
      return false;
    }
    var destination = destinationList(canonicalName);
    if (!destination) {
      return false;
    }
    var sourceCard = tableCardByName(oldTableName);
    var destinationCard = tableCardByName(canonicalName);
    destination.appendChild(item);
    item.dataset.currentTable = canonicalName;
    var select = assignmentControl(item);
    if (select) {
      select.value = canonicalName;
    }
    sortGuestList(destination);
    item.classList.remove("is-just-moved");
    window.requestAnimationFrame(function () {
      item.classList.add("is-just-moved");
    });
    window.setTimeout(function () {
      item.classList.remove("is-just-moved");
    }, 520);
    updateTableCard(sourceCard);
    if (destinationCard !== sourceCard) {
      updateTableCard(destinationCard);
    }
    updateStats();
    applyFilters();
    return true;
  }

  function sparkleFrom(item) {
    if (!celebration || motionMode() !== "full") {
      return;
    }
    var rect = item.getBoundingClientRect();
    var colors = ["#D88BA7", "#C9A46A", "#789783", "#F8DCE8"];
    for (var index = 0; index < 8; index += 1) {
      var particle = element("span", "table-plan-sparkle");
      var angle = (Math.PI * 2 * index) / 8;
      var distance = 22 + (index % 3) * 6;
      particle.style.left = rect.left + Math.min(rect.width, 80) / 2 + "px";
      particle.style.top = rect.top + rect.height / 2 + "px";
      particle.style.setProperty("--sparkle-x", Math.cos(angle) * distance + "px");
      particle.style.setProperty("--sparkle-y", Math.sin(angle) * distance + "px");
      particle.style.setProperty("--sparkle-color", colors[index % colors.length]);
      celebration.appendChild(particle);
      window.setTimeout(function (sparkle) {
        sparkle.remove();
      }, 720, particle);
    }
  }

  function announceMutation() {
    if (channel) {
      channel.postMessage({ type: "guests-changed", at: String(Date.now()) });
    }
  }

  function saveAssignment(item, requestedTable) {
    var guestId = item.dataset.guestId;
    var oldTable = canonicalTableName(item.dataset.currentTable || "");
    oldTable = oldTable === null ? String(item.dataset.currentTable || "") : oldTable;
    var nextTable = canonicalTableName(requestedTable);
    var select = assignmentControl(item);
    if (nextTable === null) {
      if (select) {
        select.value = oldTable;
      }
      toast("Esta mesa já não está no mapa. Atualizem a página antes de mover o convidado.", "error");
      return Promise.resolve();
    }
    if (
      !guestId ||
      tableIdentityKey(oldTable) === tableIdentityKey(nextTable) ||
      savePromises.has(guestId)
    ) {
      if (select) {
        select.value = nextTable;
      }
      item.dataset.currentTable = nextTable;
      return Promise.resolve();
    }
    if (!destinationList(nextTable)) {
      if (select) {
        select.value = oldTable;
      }
      toast("Esta mesa já não está disponível. Atualizem a página.", "error");
      return Promise.resolve();
    }

    if (select) {
      select.disabled = true;
    }
    setGuestState(item, "saving", "A guardar…");
    setLive("A guardar lugar…", "saving");
    var operation = jsonRequest(
      apiUrl + "/" + encodeURIComponent(guestId),
      {
        method: "PATCH",
        body: JSON.stringify({
          table_name: nextTable,
          expected_updated_at: item.dataset.updatedAt || "",
        }),
      }
    ).then(function (payload) {
      var guest = payload.guest || {};
      var savedTable = canonicalTableName(guest.table_name || "");
      item.dataset.updatedAt = String(guest.updated_at || "");
      if (savedTable === null || !moveGuestElement(item, savedTable)) {
        if (select) {
          select.value = oldTable;
        }
        throw new Error("O mapa mudou noutra sessão. Atualizem a página para ver a nova mesa.");
      }
      setGuestState(item, "saved", "Guardado");
      setLive("Tudo guardado", "ready");
      sparkleFrom(item);
      var targetCard = tableCardByName(savedTable);
      var targetOccupancy = targetCard ? guestItemsInCard(targetCard).length : 0;
      var targetCapacity = targetCard
        ? Math.max(0, Number(targetCard.dataset.tableCapacity) || 0)
        : 0;
      var message = savedTable
        ? String(guest.name || item.dataset.guestName) + " ficou na " + savedTable + "."
        : String(guest.name || item.dataset.guestName) + " ficou sem mesa por agora.";
      if (targetCard && targetOccupancy === targetCapacity) {
        message += " A mesa ficou completa ✦";
      } else if (targetCard && targetOccupancy > targetCapacity) {
        message += " Atenção: está acima da capacidade.";
      }
      toast(message, targetCard && targetOccupancy > targetCapacity ? "error" : "success");
      announceMutation();
    }).catch(function (error) {
      var conflictReconciled = false;
      if (error.status === 409 && error.payload && error.payload.guest) {
        var currentGuest = error.payload.guest;
        var serverTable = canonicalTableName(currentGuest.table_name || "");
        item.dataset.updatedAt = String(currentGuest.updated_at || "");
        if (serverTable === null || !moveGuestElement(item, serverTable)) {
          setLive("O mapa mudou noutra sessão · atualizem a página", "error");
          if (select) {
            select.value = oldTable;
          }
          toast(
            "Foi criada ou alterada uma mesa noutra sessão. Atualizem a página antes de continuar.",
            "error"
          );
        } else {
          conflictReconciled = true;
          toast(
            "Este convidado foi alterado noutra sessão. O mapa foi sincronizado.",
            "error"
          );
        }
      } else {
        if (select) {
          select.value = oldTable;
        }
        toast(error.message || "Não foi possível guardar o novo lugar.", "error");
      }
      if (conflictReconciled) {
        setGuestState(item, "saved", "Atualizado");
        setLive("Mapa sincronizado", "ready");
      } else {
        setGuestState(item, "error", "Não guardado");
        setLive("Não foi possível guardar", "error");
      }
    }).finally(function () {
      if (select) {
        select.disabled = false;
      }
      savePromises.delete(guestId);
    });
    savePromises.set(guestId, operation);
    return operation;
  }

  function setupGuestItem(item) {
    if (!item || item.dataset.dragReady === "true") {
      return;
    }
    item.dataset.dragReady = "true";
    item.draggable = true;
    item.addEventListener("dragstart", function (event) {
      if (item.classList.contains("is-saving")) {
        event.preventDefault();
        return;
      }
      draggedItem = item;
      item.classList.add("is-dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", item.dataset.guestId || "");
      }
    });
    item.addEventListener("dragend", function () {
      item.classList.remove("is-dragging");
      draggedItem = null;
      workspace.querySelectorAll(".is-drag-over").forEach(function (target) {
        target.classList.remove("is-drag-over");
      });
    });
  }

  function setupDropTarget(target, tableName) {
    if (!target || target.dataset.dropReady === "true") {
      return;
    }
    target.dataset.dropReady = "true";
    target.addEventListener("dragover", function (event) {
      if (!draggedItem) {
        return;
      }
      event.preventDefault();
      target.classList.add("is-drag-over");
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "move";
      }
    });
    target.addEventListener("dragleave", function (event) {
      if (!target.contains(event.relatedTarget)) {
        target.classList.remove("is-drag-over");
      }
    });
    target.addEventListener("drop", function (event) {
      event.preventDefault();
      target.classList.remove("is-drag-over");
      if (!draggedItem) {
        return;
      }
      var item = draggedItem;
      draggedItem = null;
      item.classList.remove("is-dragging");
      var select = assignmentControl(item);
      if (select) {
        select.value = tableName || "";
      }
      saveAssignment(item, tableName || "");
    });
  }

  function availabilityMatches(card, filterValue) {
    if (!filterValue) {
      return true;
    }
    var occupancy = guestItemsInCard(card).length;
    var capacity = Math.max(0, Number(card.dataset.tableCapacity) || 0);
    if (filterValue === "available") {
      return occupancy < capacity;
    }
    if (filterValue === "full") {
      return capacity > 0 && occupancy === capacity;
    }
    if (filterValue === "over") {
      return occupancy > capacity;
    }
    return true;
  }

  function applyFilters() {
    var query = normalize(searchInput && searchInput.value);
    var zone = normalize(zoneFilter && zoneFilter.value);
    var shape = normalize(shapeFilter && shapeFilter.value);
    var capacity = capacityFilter ? capacityFilter.value : "";
    var visible = 0;
    allTableCards().forEach(function (card) {
      var guestSearch = guestItemsInCard(card).map(function (item) {
        return [
          item.dataset.guestName,
          item.dataset.guestSide,
          item.dataset.guestGroup,
          item.dataset.guestRsvp,
        ].join(" ");
      }).join(" ");
      var cardSearch = [
        card.dataset.tableName,
        card.dataset.tableZone,
        card.dataset.tableShape,
        card.dataset.tableNotes,
        guestSearch,
      ].join(" ");
      var matches =
        (!query || normalize(cardSearch).includes(query)) &&
        (!zone || normalize(card.dataset.tableZone) === zone) &&
        (!shape || normalize(card.dataset.tableShape) === shape) &&
        availabilityMatches(card, capacity);
      card.hidden = !matches;
      if (matches) {
        visible += 1;
      }
    });
    if (unassignedList) {
      unassignedList.querySelectorAll(":scope > [data-table-guest]").forEach(
        function (item) {
          var guestSearch = [
            item.dataset.guestName,
            item.dataset.guestSide,
            item.dataset.guestGroup,
            item.dataset.guestRsvp,
          ].join(" ");
          item.hidden = Boolean(query) && !normalize(guestSearch).includes(query);
        }
      );
    }
    if (visibleCount) {
      visibleCount.textContent = String(visible);
    }
    if (filterEmpty && allTableCards().length) {
      filterEmpty.hidden = visible > 0;
    }
    var hasFilters = Boolean(query || zone || shape || capacity);
    if (clearButton) {
      clearButton.hidden = !hasFilters;
    }
  }

  function clearFilters() {
    if (searchInput) {
      searchInput.value = "";
    }
    [zoneFilter, shapeFilter, capacityFilter].forEach(function (select) {
      if (select) {
        select.value = "";
      }
    });
    applyFilters();
    searchInput && searchInput.focus();
  }

  function guestIsProtected(item) {
    return item.classList.contains("is-saving") || item.contains(document.activeElement);
  }

  function updateGuestCopy(item, guest) {
    item.dataset.guestName = String(guest.name || item.dataset.guestName || "Convidado");
    item.dataset.guestSide = String(guest.side || "");
    item.dataset.guestGroup = String(guest.age_group || "");
    item.dataset.guestRsvp = String(guest.rsvp_status || "");
    var avatar = item.querySelector(".table-guest-avatar");
    var name = item.querySelector(".table-guest-copy strong");
    if (avatar) {
      avatar.textContent = initials(guest.name);
      avatar.setAttribute("aria-label", "Abrir detalhes de " + guest.name);
    }
    if (name) {
      name.textContent = guest.name;
    }
    var tags = item.querySelector(".table-guest-copy p");
    if (tags) {
      tags.replaceChildren();
      appendGuestTag(tags, guest.side, "side");
      appendGuestTag(tags, guest.age_group, "group");
      appendGuestTag(tags, guest.rsvp_status, "rsvp");
    }
  }

  function reconcileAssignments(payload) {
    if (!payload || !Array.isArray(payload.items)) {
      return;
    }
    var existing = new Map();
    allGuestItems().forEach(function (item) {
      existing.set(String(item.dataset.guestId), item);
    });
    var incoming = new Set();
    var touchedCards = new Set();
    var unknownTables = new Set();
    payload.items.forEach(function (guest) {
      var guestId = String(guest.id);
      incoming.add(guestId);
      var item = existing.get(guestId);
      var rawServerTable = String(guest.table_name || "");
      var serverTable = canonicalTableName(rawServerTable);
      if (serverTable === null) {
        unknownTables.add(rawServerTable);
        return;
      }
      if (!item) {
        var newDestination = destinationList(serverTable);
        if (!newDestination) {
          return;
        }
        guest.table_name = serverTable;
        item = createGuestItem(guest);
        newDestination.appendChild(item);
        touchedCards.add(tableCardByName(serverTable));
      } else if (!guestIsProtected(item)) {
        updateGuestCopy(item, guest);
        if (
          tableIdentityKey(serverTable) !==
          tableIdentityKey(item.dataset.currentTable || "")
        ) {
          touchedCards.add(tableCardByName(item.dataset.currentTable || ""));
          if (moveGuestElement(item, serverTable)) {
            touchedCards.add(tableCardByName(serverTable));
          }
        } else {
          item.dataset.currentTable = serverTable;
          var select = assignmentControl(item);
          if (select) {
            select.value = serverTable;
          }
        }
        item.dataset.updatedAt = String(guest.updated_at || "");
      }
    });
    var reportedFiltered = Number(payload.filtered);
    var reportedTotal = Number(payload.stats && payload.stats.total);
    var expectedCount = Number.isFinite(reportedFiltered)
      ? reportedFiltered
      : reportedTotal;
    var completeSnapshot =
      Number.isFinite(expectedCount) && expectedCount <= payload.items.length;
    if (completeSnapshot) {
      existing.forEach(function (item, guestId) {
        if (!incoming.has(guestId) && !guestIsProtected(item)) {
          touchedCards.add(tableCardByName(item.dataset.currentTable || ""));
          item.remove();
        }
      });
    }
    touchedCards.forEach(updateTableCard);
    sortGuestList(unassignedList);
    allTableCards().forEach(function (card) {
      sortGuestList(card.querySelector("[data-table-roster]"));
    });
    updateStats();
    applyFilters();
    if (unknownTables.size) {
      var noticeKey = Array.from(unknownTables).sort().join("|");
      setLive("O mapa mudou noutra sessão · atualizem a página", "error");
      if (noticeKey !== lastUnknownNotice) {
        toast(
          "Existem mesas novas ou renomeadas. Atualizem a página para carregar o mapa completo.",
          "error"
        );
        lastUnknownNotice = noticeKey;
      }
      return false;
    }
    lastUnknownNotice = "";
    return true;
  }

  async function refreshAssignments() {
    if (refreshInProgress || document.hidden || savePromises.size) {
      return;
    }
    refreshInProgress = true;
    try {
      var payload = await jsonRequest(apiUrl + "?limit=500&sort=name&direction=asc");
      var isComplete = reconcileAssignments(payload);
      if (isComplete) {
        setLive("Tudo sincronizado", "ready");
      }
    } catch (error) {
      if (error.message !== "Session expired") {
        setLive("Sem ligação · os dados guardados continuam seguros", "error");
      }
    } finally {
      refreshInProgress = false;
    }
  }

  workspace.addEventListener("change", function (event) {
    var select = event.target.closest("[data-table-assignment]");
    if (!select) {
      return;
    }
    var item = select.closest("[data-table-guest]");
    if (item) {
      saveAssignment(item, select.value);
    }
  });

  searchInput && searchInput.addEventListener("input", applyFilters);
  [zoneFilter, shapeFilter, capacityFilter].forEach(function (select) {
    select && select.addEventListener("change", applyFilters);
  });
  clearButton && clearButton.addEventListener("click", clearFilters);
  emptyClearButton && emptyClearButton.addEventListener("click", clearFilters);

  document.addEventListener("keydown", function (event) {
    var target = event.target;
    var isWriting = target && (
      target.matches("input, textarea, select") || target.isContentEditable
    );
    if (event.key === "/" && !isWriting && searchInput) {
      event.preventDefault();
      searchInput.focus();
    }
  });

  allGuestItems().forEach(setupGuestItem);
  allTableCards().forEach(function (card) {
    setupDropTarget(card, card.dataset.tableName || "");
    updateTableCard(card);
    sortGuestList(card.querySelector("[data-table-roster]"));
  });
  setupDropTarget(unassignedPanel, "");
  sortGuestList(unassignedList);
  updateStats();
  applyFilters();

  if ("BroadcastChannel" in window) {
    channel = new BroadcastChannel("lv-wedding-guests");
    channel.addEventListener("message", function (event) {
      if (event.data && event.data.type === "guests-changed") {
        refreshAssignments();
      }
    });
  }
  window.setInterval(refreshAssignments, 20000);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      refreshAssignments();
    }
  });
})();
