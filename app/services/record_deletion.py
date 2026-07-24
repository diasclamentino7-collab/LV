"""Non-destructive permanent deletion for user-facing planning records."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.core import RecordTombstone


def entity_type_for(model_or_record: Any) -> str:
    """Return the stable database-table identifier used by tombstones."""

    table = inspect(model_or_record).mapper.local_table
    return str(table.name)


def not_tombstoned(model: type[Any]) -> ColumnElement[bool]:
    """Build a correlated condition that keeps tombstoned rows out of a query."""

    return ~exists().where(
        RecordTombstone.entity_type == entity_type_for(model),
        RecordTombstone.entity_id == model.id,
    )


def is_tombstoned(db: Session, model_or_record: Any, record_id: int | None = None) -> bool:
    """Check whether a record is no longer recoverable through the interface."""

    entity_id = record_id if record_id is not None else getattr(model_or_record, "id", None)
    if entity_id is None:
        return False
    return (
        db.scalar(
            select(RecordTombstone.id).where(
                RecordTombstone.entity_type == entity_type_for(model_or_record),
                RecordTombstone.entity_id == entity_id,
            )
        )
        is not None
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def snapshot_record(record: Any) -> str:
    """Serialize every persisted column before hiding the row from the UI."""

    mapper = inspect(record).mapper
    snapshot = {
        attribute.key: _json_value(getattr(record, attribute.key))
        for attribute in mapper.column_attrs
    }
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True)


def create_tombstone(
    db: Session,
    record: Any,
    *,
    module: str,
    user_id: int | None,
) -> RecordTombstone:
    """Add an immutable UI-deletion marker while preserving the source row."""

    tombstone = RecordTombstone(
        entity_type=entity_type_for(record),
        entity_id=record.id,
        module=module,
        snapshot_json=snapshot_record(record),
        deleted_by_id=user_id,
    )
    db.add(tombstone)
    return tombstone
