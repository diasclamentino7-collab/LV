"""Shared Jinja environment and safe project-wide presentation context."""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import SessionLocal
from app.repositories.project_settings import get_project_settings
from app.services.csrf import get_csrf_token

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "BRL": "R$"}


def safe_color(value: str | None, fallback: str) -> str:
    return value if value and HEX_COLOR.fullmatch(value) else fallback


def contrast_text(background: str) -> str:
    """Return the most legible approved text colour for a theme background."""

    rgb = [int(background[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    channels = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in rgb
    ]
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    dark_contrast = (luminance + 0.05) / 0.05
    light_contrast = 1.05 / (luminance + 0.05)
    return "#333333" if dark_contrast >= light_contrast else "#FFFFFF"


def project_template_context(request: Request) -> dict[str, Any]:
    """Expose validated shared theme values to every rendered page."""

    with SessionLocal() as db:
        settings = get_project_settings(
            db,
            user_id=request.session.get("user_id"),
        )
        if settings is None:  # Defensive fallback; create=True normally prevents this.
            return {
                "csrf_token": get_csrf_token(request),
                "display_app_name": get_settings().app_name,
                "theme": {
                    "primary": "#D88BA7",
                    "secondary": "#F8DCE8",
                    "accent": "#C9A46A",
                    "background": "#FAF8F6",
                    "on_primary": "#333333",
                    "on_background": "#333333",
                },
                "currency_symbol": "€",
            }
        primary = safe_color(settings.primary_color, "#D88BA7")
        background = safe_color(settings.background_color, "#FAF8F6")
        context = {
            "csrf_token": get_csrf_token(request),
            "ui_settings": settings,
            "display_app_name": settings.project_name or get_settings().app_name,
            "theme": {
                "primary": primary,
                "secondary": safe_color(settings.secondary_color, "#F8DCE8"),
                "accent": safe_color(settings.accent_color, "#C9A46A"),
                "background": background,
                "on_primary": contrast_text(primary),
                "on_background": contrast_text(background),
            },
            "currency_symbol": CURRENCY_SYMBOLS.get(settings.currency, settings.currency),
        }
        db.expunge(settings)
    return context


templates = Jinja2Templates(
    directory=PROJECT_ROOT / "app" / "templates",
    context_processors=[project_template_context],
)
