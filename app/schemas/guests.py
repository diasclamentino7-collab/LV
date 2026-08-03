"""Validated JSON contracts for the collaborative guest workspace."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RSVPStatus = Literal["Pendente", "Confirmado", "Recusado", "Talvez"]
GuestSide = Literal["", "Noivo", "Noiva", "Ambos"]
GuestSex = Literal["", "Feminino", "Masculino", "Outro"]
AgeGroup = Literal["Adulto", "Criança", "Bebé"]


class GuestFields(BaseModel):
    """Fields that may be persisted on one guest."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    congregation: str = Field(default="", max_length=150)
    sex: GuestSex = ""
    side: GuestSide = ""
    age_group: AgeGroup = "Adulto"
    rsvp_status: RSVPStatus = "Pendente"
    table_name: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=200)
    dietary_requirements: str = Field(default="", max_length=5_000)
    special_needs: str = Field(default="", max_length=5_000)
    address: str = Field(default="", max_length=5_000)
    invitation_sent: bool = False
    gift_received: bool = False
    notes: str = Field(default="", max_length=10_000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("O email não é válido.")
        return value


class GuestCreate(GuestFields):
    """Create request, with CSRF accepted in the body for non-fetch clients."""

    csrf_token: str = Field(default="", max_length=256, exclude=True)


class GuestUpdate(BaseModel):
    """Allowlisted partial update; omitted fields are never overwritten."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    congregation: str | None = Field(default=None, max_length=150)
    sex: GuestSex | None = None
    side: GuestSide | None = None
    age_group: AgeGroup | None = None
    rsvp_status: RSVPStatus | None = None
    table_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    dietary_requirements: str | None = Field(default=None, max_length=5_000)
    special_needs: str | None = Field(default=None, max_length=5_000)
    address: str | None = Field(default=None, max_length=5_000)
    invitation_sent: bool | None = None
    gift_received: bool | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    expected_updated_at: str | None = Field(default=None, max_length=64, exclude=True)
    csrf_token: str = Field(default="", max_length=256, exclude=True)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("O email não é válido.")
        return value

    @model_validator(mode="after")
    def require_change(self) -> GuestUpdate:
        excluded = {"csrf_token", "expected_updated_at"}
        if not (self.model_fields_set - excluded):
            raise ValueError("Indique pelo menos um campo para alterar.")
        return self


class GuestBulkUpdate(BaseModel):
    """A bounded bulk command for the spreadsheet-like guest list."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ids: list[int] = Field(min_length=1, max_length=200)
    action: Literal[
        "rsvp_status",
        "invitation_sent",
        "gift_received",
        "table_name",
        "side",
        "archive",
    ]
    value: Any = None
    expected_updated_at: dict[str, str] = Field(default_factory=dict, exclude=True)
    csrf_token: str = Field(default="", max_length=256, exclude=True)

    @field_validator("ids")
    @classmethod
    def unique_positive_ids(cls, value: list[int]) -> list[int]:
        unique = list(dict.fromkeys(value))
        if any(item <= 0 for item in unique):
            raise ValueError("Os identificadores devem ser positivos.")
        return unique
