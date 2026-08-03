import re

from app.core.config import PROJECT_ROOT
from app.core.templating import templates


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_table_plan_compiles_and_exposes_a_visual_map() -> None:
    template = read_project_file("app/templates/table_plan.html")

    templates.env.get_template("table_plan.html")
    for marker in (
        "data-table-plan",
        "data-table-card",
        "data-table-diagram",
        "data-seat-ring",
        "data-table-roster",
        "data-unassigned-list",
        "data-table-assignment",
        "data-table-capacity-label",
        "is-over-capacity",
    ):
        assert marker in template
    assert "range(seat_total)" in template
    assert "[[capacity, occupancy, 1]|max, 16]|min" in template
    assert "table.duplicate_definitions" in template
    assert "Existem {{ table.definition_count" in template
    assert 'href="{{ duplicate.edit_url }}"' in template
    assert 'action="/table-plan/{{ duplicate.id }}/archive"' in template
    assert "Eliminar repetida" in template


def test_table_plan_preserves_crud_and_fallback_actions() -> None:
    template = read_project_file("app/templates/table_plan.html")

    for action in (
        'href="/exports/table-plan.pdf"',
        'href="/table-plan?archived=true"',
        'href="/table-plan/new"',
        'href="/guests"',
        'href="/table-plan/{{ table.id }}/edit"',
        'action="/table-plan/{{ table.id }}/archive"',
        'name="csrf_token" value="{{ csrf_token }}"',
    ):
        assert action in template
    assert "os convidados não serão apagados" in template
    assert 'value="{{ search|default' in template
    assert 'data-table-notes="{{ table.notes|default' in template


def test_table_assignment_is_secure_concurrent_and_database_backed() -> None:
    javascript = read_project_file("app/static/js/table-plan.js")

    assert 'method: "PATCH"' in javascript
    assert 'headers.set("X-CSRF-Token", csrfToken)' in javascript
    assert 'cache: "no-store"' in javascript
    assert "expected_updated_at: item.dataset.updatedAt" in javascript
    assert "table_name: nextTable" in javascript
    assert "table_name: null" not in javascript
    assert "error.status === 409" in javascript
    assert "var conflictReconciled = false" in javascript
    assert 'setGuestState(item, "saved", "Atualizado")' in javascript
    assert 'new BroadcastChannel("lv-wedding-guests")' in javascript
    for unsafe_api in (
        "innerHTML",
        "insertAdjacentHTML",
        "localStorage",
        "sessionStorage",
    ):
        assert unsafe_api not in javascript


def test_identity_search_and_partial_polling_are_loss_safe() -> None:
    javascript = read_project_file("app/static/js/table-plan.js")

    assert "function tableIdentityKey(value)" in javascript
    assert "function canonicalTableName(value)" in javascript
    assert "tableIdentityKey(card.dataset.tableName)" in javascript
    assert "card.dataset.tableNotes" in javascript
    assert "normalize(cardSearch).includes(query)" in javascript
    assert "normalize(card.textContent)" not in javascript
    assert "var completeSnapshot" in javascript
    assert "expectedCount <= payload.items.length" in javascript
    assert "if (completeSnapshot)" in javascript
    assert "unknownTables.size" in javascript
    assert "mesas novas ou renomeadas" in javascript
    assert "tags.replaceChildren()" in javascript


def test_map_supports_drag_touch_filters_and_accessible_overflow() -> None:
    template = read_project_file("app/templates/table_plan.html")
    javascript = read_project_file("app/static/js/table-plan.js")
    stylesheet = read_project_file("app/static/css/table-plan.css")

    for marker in (
        "data-table-zone-filter",
        "data-table-shape-filter",
        "data-table-capacity-filter",
    ):
        assert marker in template
    assert 'event.key === "/"' in javascript
    assert "item.draggable = true" in javascript
    assert 'target.addEventListener("drop"' in javascript
    assert "Math.min(Math.max(capacity, guests.length, 1), 16)" in javascript
    assert "String(Math.max(capacity, occupancy, 1))" in javascript
    assert 'aria-valuemax="{{ [capacity, occupancy, 1]|max }}"' in template
    assert '.table-diagram[data-shape*="oval" i]' in stylesheet
    assert '.table-diagram[data-shape*="retang" i]' in stylesheet
    assert ".table-map-card.is-over-capacity" in stylesheet
    assert "@media (max-width: 560px)" in stylesheet
    assert "@media (hover: none)" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ":focus-visible" in stylesheet


def test_map_text_is_legible_for_daily_use() -> None:
    stylesheet = read_project_file("app/static/css/table-plan.css")
    pixel_sizes = [
        float(value) for value in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", stylesheet)
    ]

    assert pixel_sizes
    assert min(pixel_sizes) >= 10
    assert ".table-guest-copy strong" in stylesheet
    assert ".table-assignment-field select" in stylesheet
    assert "font-size: 13px" in stylesheet
    assert "min-height: 44px" in stylesheet


def test_table_map_assets_are_available_in_the_pwa() -> None:
    service_worker = read_project_file("app/static/sw.js")

    assert '"/static/css/table-plan.css"' in service_worker
    assert '"/static/js/table-plan.js"' in service_worker
    assert 'const CACHE = "lv-wedding-v10"' in service_worker
