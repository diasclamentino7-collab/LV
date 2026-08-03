from app.core.config import PROJECT_ROOT


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_guest_workspace_exposes_spreadsheet_controls_and_fallbacks() -> None:
    template = read_project_file("app/templates/guests.html")

    assert "data-guest-workspace" in template
    assert "data-guest-quick-row" in template
    assert 'data-guest-field="name"' in template
    assert 'data-guest-bulk="rsvp_status"' in template
    assert 'data-guest-bulk="gift_received"' in template
    assert "data-guest-density" in template
    assert 'data-revision="{{ guest_revision' in template
    assert 'method="post" action="/guests/new"' in template
    assert 'href="/guests?archived=true"' in template
    assert "Talvez" in template
    assert "Bebé" in template


def test_guest_workspace_persists_through_authenticated_api_without_unsafe_html() -> None:
    javascript = read_project_file("app/static/js/guests.js")

    assert 'method: "PATCH"' in javascript
    assert 'method: "POST"' in javascript
    assert "expected_updated_at" in javascript
    assert 'cache: "no-store"' in javascript
    assert 'headers.set("X-CSRF-Token", csrfToken)' in javascript
    assert 'new BroadcastChannel("lv-wedding-guests")' in javascript
    assert 'event.key === "/"' in javascript
    assert "innerHTML" not in javascript
    assert "insertAdjacentHTML" not in javascript


def test_guest_workspace_assets_are_in_the_pwa_cache() -> None:
    service_worker = read_project_file("app/static/sw.js")

    assert '"/static/css/guests.css"' in service_worker
    assert '"/static/js/guests.js"' in service_worker
    assert '"/static/css/module-workspace.css"' in service_worker
    assert '"/static/js/module-workspace.js"' in service_worker
    assert '"/static/css/form-workspace.css"' in service_worker
    assert '"/static/js/form-workspace.js"' in service_worker
    assert '"/static/css/utility-workspaces.css"' in service_worker
    assert '"/static/js/utility-workspaces.js"' in service_worker
    assert 'const CACHE = "lv-wedding-v9"' in service_worker
