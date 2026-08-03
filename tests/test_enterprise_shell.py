from jinja2 import Environment

from app.core.config import PROJECT_ROOT


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_enterprise_shell_keeps_navigation_semantic_and_complete() -> None:
    base = _read("app/templates/base.html")
    Environment().parse(base)

    assert 'aria-label="Navegação principal"' in base
    assert 'aria-label="Áreas da aplicação"' in base
    assert 'aria-label="Contexto da página"' in base
    assert 'class="skip-link"' in base
    assert 'aria-current="page"' in base
    assert 'data-motion-home aria-label=' in base
    assert 'href="/settings" aria-label="Abrir Configurações"' in base

    for route in (
        "/dashboard",
        "/checklist",
        "/timeline",
        "/budget",
        "/payments",
        "/expenses",
        "/vendors",
        "/guests",
        "/table-plan",
        "/kingdom-hall",
        "/reception",
        "/legal-process",
        "/attire",
        "/honeymoon",
        "/home",
        "/gifts",
        "/documents",
        "/moodboard",
        "/communication",
        "/activity",
    ):
        assert f"'{route}'" in base


def test_account_and_global_actions_are_explicit_and_accessible() -> None:
    base = _read("app/templates/base.html")

    assert 'aria-controls="account-menu-panel"' in base
    assert 'id="account-menu-panel"' in base
    assert 'aria-expanded="false"' in base
    assert 'href="/account/password"' in base
    assert 'href="/deleted"' in base
    assert 'action="/logout"' in base
    assert 'type="submit"' in base
    assert "Pesquisar áreas e ações" in base
    assert "Centro de comunicação" in base


def test_shell_styles_cover_responsiveness_focus_and_reduced_motion() -> None:
    css = _read("app/static/css/app.css")

    for token in (
        "--surface:",
        "--ink-strong:",
        "--muted: #756c6e",
        "--focus-ring:",
        "--shadow-sm:",
        "--radius-lg:",
    ):
        assert token in css

    assert "@media (max-width: 850px)" in css
    assert "@media (max-width: 560px)" in css
    assert "100dvh" in css
    assert "env(safe-area-inset-bottom)" in css
    assert ":focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert 'html[data-motion="none"]' in css
    assert "transition: all" not in css


def test_shell_javascript_preserves_mobile_focus_and_truthful_state() -> None:
    javascript = _read("app/static/js/app.js")

    assert 'register("/static/sw.js")' in javascript
    assert 'toggleAttribute("inert", !available)' in javascript
    assert 'setAttribute("aria-hidden"' in javascript
    assert 'setAttribute("aria-expanded"' in javascript
    assert 'event.key === "Escape"' in javascript
    assert 'event.key !== "Tab"' in javascript
    assert 'document.body.classList.contains("navigation-open")' in javascript
    assert 'scrollIntoView({' in javascript
    assert "innerHTML" not in javascript
    assert "localStorage" not in javascript
    assert "setTimeout" not in javascript
