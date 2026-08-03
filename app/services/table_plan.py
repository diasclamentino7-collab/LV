"""Read-only assembly of the visual seating plan from persisted records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.models.core import User, WorkspaceRecord
from app.models.planning import Guest
from app.services.guests import active_guest_condition, serialize_guest, timestamp_string
from app.services.record_deletion import not_tombstoned

DEFAULT_TABLE_CAPACITY = 8
MAX_TABLE_CAPACITY = 100
DEFAULT_TABLE_SHAPE = "Redonda"


def clean_table_name(value: str | None) -> str:
    """Return a readable table name with accidental whitespace removed."""

    return " ".join((value or "").split())


def table_name_key(value: str | None) -> str:
    """Build the matching key used across definitions and guest assignments."""

    return clean_table_name(value).casefold()


def configured_capacity(value: str | None) -> int | None:
    """Parse a positive configured capacity without raising on legacy values."""

    try:
        capacity = int((value or "").strip())
    except (AttributeError, TypeError, ValueError):
        return None
    if capacity < 1:
        return None
    return min(capacity, MAX_TABLE_CAPACITY)


def sync_table_name_assignments(
    db: Session,
    previous_name: str,
    new_name: str,
    *,
    user_id: int | None,
) -> int:
    """Keep guest assignments attached when a persisted table is renamed.

    Archived guests are included because restoring one later must not recreate
    the old table. Tombstoned rows remain immutable and are deliberately skipped.
    The caller owns the transaction, making the table and guest rename atomic.
    """

    cleaned_previous_name = clean_table_name(previous_name)
    canonical_name = clean_table_name(new_name)
    if not cleaned_previous_name or not canonical_name or cleaned_previous_name == canonical_name:
        return 0
    previous_key = cleaned_previous_name.casefold()

    changed = 0
    guests = db.scalars(select(Guest).where(not_tombstoned(Guest))).all()
    for guest in guests:
        if table_name_key(guest.table_name) != previous_key:
            continue
        guest.table_name = canonical_name
        guest.updated_by_id = user_id
        guest.updated_at = datetime.now(UTC)
        changed += 1
    return changed


def _guest_rows(db: Session) -> list[dict[str, Any]]:
    updated_user = aliased(User)
    created_user = aliased(User)
    rows = db.execute(
        select(Guest, updated_user.name, created_user.name)
        .outerjoin(updated_user, Guest.updated_by_id == updated_user.id)
        .outerjoin(created_user, Guest.created_by_id == created_user.id)
        .where(*active_guest_condition())
        .order_by(func.lower(Guest.name), Guest.id)
    ).all()
    return [
        serialize_guest(
            guest,
            updated_by=updated_by or "",
            created_by=created_by or "",
        )
        for guest, updated_by, created_by in rows
    ]


def _table_definitions(db: Session) -> list[WorkspaceRecord]:
    return list(
        db.scalars(
            select(WorkspaceRecord)
            .where(
                WorkspaceRecord.module == "table-plan",
                WorkspaceRecord.is_archived.is_(False),
                not_tombstoned(WorkspaceRecord),
            )
            # The oldest persisted definition remains the stable canonical one;
            # later historical duplicates are exposed separately for resolution.
            .order_by(WorkspaceRecord.id)
        ).all()
    )


def table_definition_name_exists(
    db: Session,
    name: str,
    *,
    exclude_id: int | None = None,
) -> bool:
    """Check logical uniqueness among recoverable, active table definitions."""

    candidate_key = table_name_key(name)
    if not candidate_key:
        return False
    return any(
        definition.id != exclude_id and table_name_key(definition.title) == candidate_key
        for definition in _table_definitions(db)
    )


def _definition_payload(record: WorkspaceRecord) -> dict[str, Any]:
    name = clean_table_name(record.title) or f"Mesa #{record.id}"
    description = (record.description or "").strip()
    comments = (record.comments or "").strip()
    return {
        "id": record.id,
        "name": name,
        "capacity": configured_capacity(record.responsible),
        "shape": (record.category or "").strip() or DEFAULT_TABLE_SHAPE,
        "zone": (record.location or "").strip(),
        "description": description,
        "comments": comments,
        "notes": description or comments,
        "status": (record.status or "").strip() or "A planear",
        "guests": [],
        "is_synthetic": False,
        "definition_ids": [record.id],
        "duplicate_definitions": [],
        "created_at": timestamp_string(record.created_at),
        "updated_at": timestamp_string(record.updated_at),
    }


def _synthetic_payload(name: str) -> dict[str, Any]:
    return {
        "id": None,
        "name": name,
        "capacity": None,
        "shape": DEFAULT_TABLE_SHAPE,
        "zone": "",
        "description": "",
        "comments": "",
        "notes": "",
        "status": "A planear",
        "guests": [],
        "is_synthetic": True,
        "definition_ids": [],
        "duplicate_definitions": [],
        "created_at": None,
        "updated_at": None,
    }


def build_table_plan(db: Session) -> dict[str, Any]:
    """Group active guests by persisted or implicitly assigned tables.

    Definitions are loaded first so their readable spelling becomes canonical.
    Matching ignores surrounding/repeated whitespace and letter casing. Duplicate
    legacy definitions remain in the database, but render as one logical table.
    """

    tables_by_key: dict[str, dict[str, Any]] = {}
    for definition in _table_definitions(db):
        payload = _definition_payload(definition)
        key = table_name_key(payload["name"])
        if not key:
            continue
        if key not in tables_by_key:
            tables_by_key[key] = payload
            continue
        primary = tables_by_key[key]
        primary["definition_ids"].append(definition.id)
        primary["duplicate_definitions"].append(
            {
                "id": definition.id,
                "name": payload["name"],
                "capacity": payload["capacity"],
                "shape": payload["shape"],
                "zone": payload["zone"],
                "status": payload["status"],
                "updated_at": payload["updated_at"],
                "edit_url": f"/table-plan/{definition.id}/edit",
            }
        )

    unassigned_guests: list[dict[str, Any]] = []
    for guest in _guest_rows(db):
        assigned_name = clean_table_name(guest["table_name"])
        key = table_name_key(assigned_name)
        if not key:
            unassigned_guests.append(guest)
            continue
        table = tables_by_key.get(key)
        if table is None:
            table = _synthetic_payload(assigned_name)
            tables_by_key[key] = table
        guest["table_name"] = table["name"]
        table["guests"].append(guest)

    tables = sorted(tables_by_key.values(), key=lambda table: table["name"].casefold())
    for table in tables:
        occupancy = len(table["guests"])
        if table["capacity"] is None:
            table["capacity"] = max(DEFAULT_TABLE_CAPACITY, occupancy)
        table["occupancy"] = occupancy
        table["available"] = max(table["capacity"] - occupancy, 0)
        table["is_over_capacity"] = occupancy > table["capacity"]
        table["definition_count"] = len(table["definition_ids"])

    assigned_guests = sum(table["occupancy"] for table in tables)
    total_guests = assigned_guests + len(unassigned_guests)
    seats_total = sum(table["capacity"] for table in tables)
    seats_available = sum(table["available"] for table in tables)
    stats = {
        "total_guests": total_guests,
        "assigned_guests": assigned_guests,
        "unassigned_guests": len(unassigned_guests),
        "table_count": len(tables),
        "seats_total": seats_total,
        "seats_available": seats_available,
        "occupancy_percent": round((assigned_guests / seats_total * 100) if seats_total else 0, 1),
        "over_capacity_tables": sum(table["is_over_capacity"] for table in tables),
        "duplicate_definition_count": sum(len(table["duplicate_definitions"]) for table in tables),
        "confirmed_guests": sum(
            guest["rsvp_status"] == "Confirmado" for table in tables for guest in table["guests"]
        )
        + sum(guest["rsvp_status"] == "Confirmado" for guest in unassigned_guests),
    }
    return {
        "tables": tables,
        "unassigned_guests": unassigned_guests,
        "stats": stats,
        "table_options": [table["name"] for table in tables],
    }
