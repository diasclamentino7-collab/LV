"""Validated input contracts for advanced project settings."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
City = Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)]
Venue = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Path = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
TimezoneName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]

Language = Literal["pt-PT", "en-GB", "en-US", "es-ES", "fr-FR"]
Currency = Literal["EUR", "USD", "GBP", "CHF", "BRL"]
WeddingStyle = Literal[
    "Elegante",
    "Minimalista",
    "Clássico",
    "Romântico",
    "Vintage",
    "Mid-century vintage",
    "Rústico",
    "Moderno",
    "Boho",
    "Personalizado",
]
TaskPriority = Literal["Baixa", "Média", "Alta", "Urgente"]
MotionPreference = Literal["full", "reduced", "none"]


def relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted(
        (relative_luminance(first), relative_luminance(second)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


class SettingsSection(BaseModel):
    """Strict base shared by every settings section."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class IdentitySettings(SettingsSection):
    """Project and couple identity."""

    project_name: ProjectName = "LV – Wedding Planner"
    partner_one_name: ShortText = ""
    partner_two_name: ShortText = ""
    language: Language = "pt-PT"

    @model_validator(mode="after")
    def partners_must_be_distinct(self) -> IdentitySettings:
        if (
            self.partner_one_name
            and self.partner_two_name
            and self.partner_one_name.casefold() == self.partner_two_name.casefold()
        ):
            raise ValueError("Os nomes do casal devem ser diferentes.")
        return self


class EventSettings(SettingsSection):
    """Wedding date, location and style."""

    wedding_date: date | None = None
    wedding_style: WeddingStyle = "Mid-century vintage"
    wedding_timezone: TimezoneName = "Europe/Lisbon"
    wedding_city: City = ""
    ceremony_venue: Venue = ""
    reception_venue: Venue = ""

    @field_validator("wedding_timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("O fuso horário indicado não existe.") from exc
        return value


class FinanceSettings(SettingsSection):
    """Budget targets and financial alerts."""

    total_budget: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0"),
        le=Decimal("9999999999.99"),
        max_digits=12,
        decimal_places=2,
    )
    currency: Currency = "EUR"
    guest_target: int = Field(default=0, ge=0, le=10_000)
    budget_alert_percent: int = Field(default=80, ge=0, le=100)

    @field_validator("total_budget", mode="before")
    @classmethod
    def accept_decimal_comma(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().replace(",", ".")
        return value


class AppearanceSettings(SettingsSection):
    """Brand colours and project logo."""

    primary_color: HexColor = "#D88BA7"
    secondary_color: HexColor = "#F8DCE8"
    accent_color: HexColor = "#C9A46A"
    background_color: HexColor = "#FAF8F6"
    logo_path: Path = ""

    @model_validator(mode="after")
    def surfaces_must_keep_text_readable(self) -> AppearanceSettings:
        for color in (self.secondary_color, self.background_color):
            if contrast_ratio(color, "#333333") < 4.5:
                raise ValueError("As cores de fundo devem manter contraste suficiente com o texto.")
        return self


class PlanningSettings(SettingsSection):
    """Planning defaults, reminders and dashboard visibility."""

    reminder_days_before: int = Field(default=7, ge=0, le=365)
    reminders_enabled: bool = True
    default_assignee: ShortText = ""
    default_task_priority: TaskPriority = "Média"
    dashboard_show_countdown: bool = True
    dashboard_show_finance: bool = True
    dashboard_show_activity: bool = True
    dashboard_show_moodboard: bool = True
    motion_preference: MotionPreference = "full"
    settings_version: int = Field(default=1, ge=1, le=2_147_483_647)


class ProjectSettingsUpdate(SettingsSection):
    """Complete settings payload composed from independently validated sections."""

    identity: IdentitySettings
    event: EventSettings
    finance: FinanceSettings
    appearance: AppearanceSettings
    planning: PlanningSettings


__all__ = [
    "AppearanceSettings",
    "Currency",
    "EventSettings",
    "FinanceSettings",
    "IdentitySettings",
    "Language",
    "MotionPreference",
    "PlanningSettings",
    "ProjectSettingsUpdate",
    "TaskPriority",
    "WeddingStyle",
]
