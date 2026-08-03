from app.core.config import PROJECT_ROOT


def test_authenticated_shell_exposes_accessible_command_palette() -> None:
    base = (PROJECT_ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    partial = (PROJECT_ROOT / "app/templates/_command_palette.html").read_text(encoding="utf-8")

    assert 'data-motion-modal-open="command-palette"' in base
    assert 'aria-keyshortcuts="Control+K Meta+K"' in base
    assert '{% include "_command_palette.html" %}' in base
    assert "css/command-palette.css" in base
    assert "js/command-palette.js" in base
    assert 'role="combobox"' in partial
    assert 'role="listbox"' in partial
    assert "data-motion-modal-close" in partial


def test_command_palette_contains_main_areas_and_creation_shortcuts() -> None:
    partial = (PROJECT_ROOT / "app/templates/_command_palette.html").read_text(encoding="utf-8")

    main_routes = (
        "/dashboard",
        "/guests",
        "/budget",
        "/checklist",
        "/timeline",
        "/payments",
        "/expenses",
        "/vendors",
        "/table-plan",
        "/kingdom-hall",
        "/reception",
        "/documents",
        "/moodboard",
        "/communication",
        "/activity",
        "/settings",
    )
    for route in main_routes:
        assert f'href="{route}"' in partial

    for shortcut in (
        "/guests/new",
        "/expenses/new",
        "/checklist/new",
        "/vendors/new",
        "/moodboard/new",
        "/communication/new",
    ):
        assert f'href="{shortcut}"' in partial


def test_command_palette_is_instant_and_only_persists_navigation_recents() -> None:
    javascript = (PROJECT_ROOT / "app/static/js/command-palette.js").read_text(encoding="utf-8")

    assert 'const storageKey = "lv-command-recent"' in javascript
    assert "window.LVMotion.navigate(destination.href" in javascript
    assert "window.location.assign(destination.href)" in javascript
    assert 'event.key === "ArrowDown"' in javascript
    assert 'event.key === "ArrowUp"' in javascript
    assert 'event.key === "Enter"' in javascript
    assert 'event.key.toLocaleLowerCase("pt-PT") === "k"' in javascript
    assert "fetch(" not in javascript
    assert "setTimeout" not in javascript


def test_command_palette_assets_are_available_offline() -> None:
    service_worker = (PROJECT_ROOT / "app/static/sw.js").read_text(encoding="utf-8")

    assert '"/static/css/command-palette.css"' in service_worker
    assert '"/static/js/command-palette.js"' in service_worker
    assert 'const CACHE = "lv-wedding-v6"' not in service_worker
