from jinja2 import Environment

from app.core.config import PROJECT_ROOT


def read_project_file(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_utility_templates_keep_server_fallbacks_and_add_progressive_controls() -> None:
    activity = read_project_file("app/templates/activity_history.html")
    deleted = read_project_file("app/templates/deleted.html")

    Environment().parse(activity)
    Environment().parse(deleted)

    for template in (activity, deleted):
        assert "css/utility-workspaces.css" in template
        assert "js/utility-workspaces.js" in template
        assert "data-utility-workspace" in template
        assert "data-utility-search" in template
        assert "data-utility-summary" in template
        assert "data-utility-empty" in template

    assert 'method="get" action="/activity"' in activity
    assert "data-utility-sort-key" in activity
    assert "utility-overview-grid" in activity
    assert "activity-user" in activity
    assert "activity-action" in activity
    assert 'method="get"' in deleted
    assert 'method="post"' in deleted
    assert 'name="csrf_token"' in deleted
    assert "permanent_delete_form" in deleted
    assert "/restore?return_to=deleted" in deleted
    assert "utility-safety-note" in deleted
    assert "deleted-record-icon" in deleted


def test_utility_javascript_is_local_safe_and_instant() -> None:
    javascript = read_project_file("app/static/js/utility-workspaces.js")

    assert 'addEventListener("input", filterItems)' in javascript
    assert "Intl.Collator" in javascript
    assert "aria-sort" in javascript
    assert 'event.key === "/"' in javascript
    assert 'event.key === "Escape"' in javascript
    assert ".textContent =" in javascript
    assert ".append(item)" in javascript
    assert "innerHTML" not in javascript
    assert "fetch(" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "setTimeout" not in javascript


def test_utility_styles_cover_mobile_accessibility_and_reduced_motion() -> None:
    stylesheet = read_project_file("app/static/css/utility-workspaces.css")

    assert "@media (max-width: 560px)" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ":focus-visible" in stylesheet
    assert ".utility-filter-empty" in stylesheet
    assert ".activity-table thead" in stylesheet
