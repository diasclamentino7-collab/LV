from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.templating import contrast_text, safe_color
from app.db.base import Base
from app.models.core import ProjectSettings
from app.repositories.project_settings import get_project_settings
from app.routes.web import (
    appearance_updates,
    decimal_or_zero,
    event_updates,
    identity_updates,
    planning_updates,
)


def configured_settings() -> ProjectSettings:
    return ProjectSettings(
        language="pt-PT",
        logo_path="",
        guest_target=120,
        settings_version=3,
    )


def test_identity_and_event_settings_are_normalized() -> None:
    settings = configured_settings()

    identity = identity_updates(
        {
            "project_name": "  O nosso casamento  ",
            "partner_one_name": "Leonor",
            "partner_two_name": "Vítor",
            "logo_path": "",
        },
        settings,
    )
    event = event_updates(
        {
            "wedding_date": "2026-09-14",
            "wedding_time": "15:30",
            "wedding_timezone": "Europe/Lisbon",
            "wedding_style": "Mid-century vintage",
            "wedding_city": "Lisboa",
            "ceremony_venue": "Salão do Reino",
            "reception_venue": "Copo de Água",
            "guest_target": "120",
        }
    )

    assert identity["project_name"] == "O nosso casamento"
    assert event["wedding_date"] == datetime(
        2026,
        9,
        14,
        15,
        30,
        tzinfo=ZoneInfo("Europe/Lisbon"),
    )
    assert event["guest_target"] == 120


def test_invalid_theme_values_are_rejected_and_never_reach_css() -> None:
    with pytest.raises(ValidationError):
        appearance_updates(
            {
                "primary_color": "red;}</style>",
                "secondary_color": "#F8DCE8",
                "accent_color": "#C9A46A",
                "background_color": "#FAF8F6",
            },
            configured_settings(),
        )

    assert safe_color("red;}</style>", "#D88BA7") == "#D88BA7"
    assert contrast_text("#FFFFFF") == "#333333"
    assert contrast_text("#000000") == "#FFFFFF"

    with pytest.raises(ValidationError):
        appearance_updates(
            {
                "primary_color": "#D88BA7",
                "secondary_color": "#222222",
                "accent_color": "#C9A46A",
                "background_color": "#111111",
            },
            configured_settings(),
        )


def test_planning_checkboxes_are_explicitly_persisted() -> None:
    updates = planning_updates(
        {
            "language": "pt-PT",
            "reminder_days_before": "14",
            "reminders_enabled": "true",
            "default_assignee": "Leonor",
            "default_task_priority": "Alta",
            "motion_preference": "reduced",
            "dashboard_show_countdown": "true",
            "dashboard_show_activity": "true",
        },
        submitted_version=3,
    )

    assert updates["reminders_enabled"] is True
    assert updates["dashboard_show_finance"] is False
    assert updates["dashboard_show_moodboard"] is False
    assert updates["motion_preference"] == "reduced"


def test_unknown_motion_preference_is_rejected() -> None:
    with pytest.raises(ValidationError):
        planning_updates(
            {
                "language": "pt-PT",
                "reminder_days_before": "7",
                "default_task_priority": "Média",
                "motion_preference": "cinematic",
            },
            submitted_version=3,
        )


def test_project_settings_repository_keeps_a_single_row() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        first = get_project_settings(db)
        second = get_project_settings(db)
        count = db.scalar(select(func.count()).select_from(ProjectSettings))

    assert first is not None
    assert second is not None
    assert first.id == second.id == 1
    assert count == 1


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", object()])
def test_invalid_legacy_budget_values_are_safely_treated_as_zero(value) -> None:
    assert decimal_or_zero(value) == 0
