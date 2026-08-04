from app.core.config import PROJECT_ROOT
from app.core.templating import templates


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_auth_templates_compile_and_share_enterprise_shell() -> None:
    base = read_project_file("app/templates/auth_base.html")

    for template_name in (
        "auth_base.html",
        "login.html",
        "setup.html",
        "password.html",
        "love_confirmation.html",
    ):
        templates.env.get_template(template_name)

    assert 'class="skip-link"' in base
    assert 'class="auth-shell"' in base
    assert 'id="auth-content"' in base
    assert "css/auth.css" in base
    assert "js/auth.js" in base


def test_auth_forms_keep_secure_backend_fields_and_add_password_controls() -> None:
    login = read_project_file("app/templates/login.html")
    setup = read_project_file("app/templates/setup.html")
    password = read_project_file("app/templates/password.html")
    love = read_project_file("app/templates/love_confirmation.html")

    for template in (login, setup, password, love):
        assert 'name="csrf_token"' in template
        assert "data-auth-form" in template

    assert 'name="user_id"' in login
    assert 'name="password"' in login
    assert 'autocomplete="current-password"' in login
    assert 'name="first_password"' in setup
    assert 'name="second_password"' in setup
    assert 'name="setup_access_token"' in setup
    assert 'name="current_password"' in password
    assert 'name="new_password"' in password
    assert 'name="answer" value="sim"' in love
    assert 'name="answer" value="simmmm"' in love

    for template in (login, setup, password):
        assert "data-password-toggle" in template
        assert 'aria-pressed="false"' in template


def test_auth_assets_are_responsive_accessible_and_progressive() -> None:
    stylesheet = read_project_file("app/static/css/auth.css")
    javascript = read_project_file("app/static/js/auth.js")
    service_worker = read_project_file("app/static/sw.js")

    assert "100dvh" in stylesheet
    assert "@media (max-width: 760px)" in stylesheet
    assert "@media (max-width: 560px)" in stylesheet
    assert "env(safe-area-inset-bottom)" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ":focus-visible" in stylesheet

    assert "data-password-toggle" in javascript
    assert "data-password-strength" in javascript
    assert 'setAttribute("aria-busy"' in javascript
    assert "textContent" in javascript
    assert "innerHTML" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript

    # A submit that never navigates away must still tell the truth about
    # what's happening (e.g. a free-tier cold start): the one legitimate
    # `setTimeout` here reveals a "still connecting" hint purely from real
    # elapsed time, not a simulated/fake delay.
    assert "data-auth-wait-hint" in javascript

    assert '"/static/css/auth.css"' in service_worker
    assert '"/static/js/auth.js"' in service_worker
    assert 'const CACHE = "lv-wedding-v12"' in service_worker
