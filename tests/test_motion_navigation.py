from app.core.config import PROJECT_ROOT


def test_route_navigation_has_no_artificial_delay() -> None:
    javascript = (PROJECT_ROOT / "app/static/js/motion.js").read_text(encoding="utf-8")
    navigate_source = javascript.split("function navigate(destination, options)", 1)[1].split(
        "function pulseHomeBrand", 1
    )[0]

    assert "window.location.assign(url.href)" in navigate_source
    assert "setTimeout" not in navigate_source
    assert "routeTimer" not in javascript
    assert "data-route-leaving" not in javascript


def test_route_motion_is_a_short_entry_effect_only() -> None:
    stylesheet = (PROJECT_ROOT / "app/static/css/motion.css").read_text(encoding="utf-8")

    assert "--motion-route-home-enter: 220ms" in stylesheet
    assert "--motion-route-subtle-enter: 140ms" in stylesheet
    assert "route-out" not in stylesheet
    assert "@view-transition" not in stylesheet
