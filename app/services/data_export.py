"""Portable, read-only export of all persisted wedding-planning records."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import Activity, ProjectSettings, RecordTombstone, User, WorkspaceRecord
from app.models.moodboard import (
    MoodboardBoard,
    MoodboardCollection,
    MoodboardInspirationPlacement,
    MoodboardItem,
)
from app.models.planning import BudgetCategory, Expense, Guest, LegalDocument, Payment, Task, Vendor

EXPORT_MODELS = (
    ProjectSettings,
    User,
    Activity,
    RecordTombstone,
    WorkspaceRecord,
    Task,
    Guest,
    Vendor,
    BudgetCategory,
    Expense,
    Payment,
    LegalDocument,
    MoodboardBoard,
    MoodboardCollection,
    MoodboardItem,
    MoodboardInspirationPlacement,
)
PUBLIC_USER_COLUMNS = frozenset(
    {
        "id",
        "name",
        "is_active",
        "created_at",
        "updated_at",
        "created_by_id",
        "updated_by_id",
    }
)


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def serialize_record(record: Any) -> dict[str, Any]:
    """Serialize mapped columns without ever exposing authentication secrets."""

    allowed_columns = (
        PUBLIC_USER_COLUMNS
        if isinstance(record, User)
        else {column.name for column in record.__table__.columns}
    )
    return {
        column.name: json_value(getattr(record, column.name))
        for column in record.__table__.columns
        if column.name in allowed_columns
    }


def build_data_export(db: Session) -> dict[str, Any]:
    """Build a database-independent snapshot suitable for personal recovery."""

    tables = {
        model.__tablename__: [
            serialize_record(record) for record in db.scalars(select(model)).all()
        ]
        for model in EXPORT_MODELS
    }
    return {
        "format": "lv-wedding-planner-export",
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "tables": tables,
    }
