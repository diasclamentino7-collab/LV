import re

from app.core.config import PROJECT_ROOT
from app.core.templating import templates


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_dashboard_compiles_as_a_command_center() -> None:
    template = read_project_file("app/templates/home.html")

    templates.env.get_template("home.html")
    for marker in (
        "dashboard-hero",
        "dashboard-quickbar",
        "dashboard-hero-meta",
        "dashboard-budget-breakdown",
        "dashboard-activity-list",
        "data-dashboard-live",
    ):
        assert marker in template
    assert "css/dashboard.css" in template
    assert 'data-live-key="open_tasks"' in template
    assert 'data-live-key="countdown_seconds"' in template


def test_dashboard_exposes_useful_database_backed_shortcuts() -> None:
    template = read_project_file("app/templates/home.html")

    for route in (
        "/checklist/new",
        "/communication/new",
        "/guests/new",
        "/expenses/new",
        "/documents/new",
        "/budget",
        "/activity",
        "/moodboard",
    ):
        assert route in template
    assert '<a class="metric-card" href="/guests"' in template
    assert '<a class="metric-card" href="/budget"' in template
    assert '<a class="metric-card" href="/checklist"' in template


def test_live_dashboard_updates_every_mirrored_metric_safely() -> None:
    javascript = read_project_file("app/static/js/dashboard.js")

    assert "liveElements.set(key, [])" in javascript
    assert "liveElements.get(key).push(element)" in javascript
    assert "for (const element of elements)" in javascript
    assert 'updateNumber("open_tasks"' in javascript
    assert 'cache: "no-store"' in javascript
    assert "replaceChildren" in javascript
    assert "innerHTML" not in javascript
    assert "insertAdjacentHTML" not in javascript
    assert "localStorage" not in javascript


def test_dashboard_visual_system_is_legible_and_responsive() -> None:
    stylesheet = read_project_file("app/static/css/dashboard.css")
    pixel_sizes = [
        float(value)
        for value in re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", stylesheet)
    ]

    assert pixel_sizes
    assert min(pixel_sizes) >= 9
    for breakpoint in ("1180px", "940px", "720px", "520px"):
        assert f"@media (max-width: {breakpoint})" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ".dashboard-hero" in stylesheet
    assert ".dashboard-live .metric-card:hover" in stylesheet
    assert ".dashboard-budget-breakdown" in stylesheet


def test_dashboard_asset_is_cached_by_the_pwa() -> None:
    service_worker = read_project_file("app/static/sw.js")

    assert '"/static/css/dashboard.css"' in service_worker
    assert 'const CACHE = "lv-wedding-v12"' in service_worker
