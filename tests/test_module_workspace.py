from app.core.config import PROJECT_ROOT


def test_generic_module_workspace_preserves_crud_and_archived_forms() -> None:
    template = (PROJECT_ROOT / "app/templates/module_list.html").read_text(encoding="utf-8")

    assert "data-module-workspace" in template
    assert 'method="get"' in template
    assert 'name="archived" value="true"' in template
    assert 'action="/{{ module.slug }}/{{ record.id }}/archive"' in template
    assert 'action="/{{ module.slug }}/{{ record.id }}/restore"' in template
    assert 'name="csrf_token" value="{{ csrf_token }}"' in template
    assert "permanent_delete_form(module.slug, record.id, csrf_token)" in template
    assert 'href="/{{ module.slug }}/{{ record.id }}/edit"' in template


def test_generic_module_workspace_has_accessible_progressive_enhancements() -> None:
    template = (PROJECT_ROOT / "app/templates/module_list.html").read_text(encoding="utf-8")

    assert 'role="search"' in template
    assert 'role="table"' in template
    assert 'role="columnheader"' in template
    assert 'aria-sort="none"' in template
    assert "data-module-search-input" in template
    assert "data-sort-name" in template
    assert "data-density-controls hidden" in template
    assert "data-selection-cell hidden" in template
    assert "data-module-status-filter" in template
    assert "data-module-sort-select" in template
    assert "data-open-selected" in template
    assert "data-record-href" in template
    assert "module-card-header" in template
    assert "js/module-workspace.js" in template
    assert "css/module-workspace.css" in template


def test_workspace_javascript_is_local_instant_and_business_data_free() -> None:
    javascript = (PROJECT_ROOT / "app/static/js/module-workspace.js").read_text(encoding="utf-8")

    assert 'const densityKey = "lv-module-density"' in javascript
    assert 'input?.addEventListener("input", filterRows)' in javascript
    assert 'event.key === "/"' in javascript
    assert 'event.key === "Enter"' in javascript
    assert 'event.key === " "' in javascript
    assert "append(row)" in javascript
    assert 'document.createElement("option")' in javascript
    assert 'statusFilter?.addEventListener("change", filterRows)' in javascript
    assert "data-record-href" not in javascript
    assert "fetch(" not in javascript
    assert "innerHTML" not in javascript
    assert "sessionStorage" not in javascript
    assert "setTimeout" not in javascript
    assert javascript.count("localStorage") == 2
