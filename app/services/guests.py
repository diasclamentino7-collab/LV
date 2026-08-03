"""Querying, validation and serialization for the collaborative guest list."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.core import User
from app.models.planning import Guest
from app.services.record_deletion import not_tombstoned

RSVP_STATUSES = ("Pendente", "Confirmado", "Recusado", "Talvez")
SIDES = ("Noivo", "Noiva", "Ambos")
AGE_GROUPS = ("Adulto", "Criança", "Bebé")
SORT_COLUMNS = {
    "name": Guest.name,
    "congregation": Guest.congregation,
    "rsvp_status": Guest.rsvp_status,
    "side": Guest.side,
    "age_group": Guest.age_group,
    "table_name": Guest.table_name,
    "updated_at": Guest.updated_at,
}


def active_guest_condition() -> tuple[Any, ...]:
    return Guest.is_archived.is_(False), not_tombstoned(Guest)


def timestamp_string(value: datetime | None) -> str | None:
    """Produce one stable timestamp representation across SQLite/PostgreSQL."""

    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def timestamp_matches(value: datetime | None, expected: str | None) -> bool:
    if not expected:
        return True
    try:
        parsed = datetime.fromisoformat(expected.replace("Z", "+00:00"))
    except ValueError:
        return False
    return timestamp_string(value) == timestamp_string(parsed)


def touch_guest(guest: Guest, user_id: int) -> None:
    guest.updated_by_id = user_id
    guest.updated_at = datetime.now(UTC)


def serialize_guest(
    guest: Guest,
    *,
    updated_by: str = "",
    created_by: str = "",
) -> dict[str, Any]:
    return {
        "id": guest.id,
        "name": guest.name,
        "congregation": guest.congregation,
        "sex": guest.sex,
        "side": guest.side,
        "age_group": guest.age_group,
        "rsvp_status": guest.rsvp_status,
        "table_name": guest.table_name,
        "phone": guest.phone,
        "email": guest.email,
        "dietary_requirements": guest.dietary_requirements,
        "special_needs": guest.special_needs,
        "address": guest.address,
        "invitation_sent": guest.invitation_sent,
        "gift_received": guest.gift_received,
        "notes": guest.notes,
        "created_at": timestamp_string(guest.created_at),
        "created_by": created_by,
        "updated_at": timestamp_string(guest.updated_at),
        "updated_by": updated_by,
    }


def guest_stats(db: Session) -> dict[str, int | float]:
    conditions = active_guest_condition()
    values = db.execute(
        select(
            func.count(Guest.id),
            func.sum(case((Guest.rsvp_status == "Confirmado", 1), else_=0)),
            func.sum(case((Guest.rsvp_status.in_(("Pendente", "Talvez")), 1), else_=0)),
            func.sum(case((Guest.rsvp_status == "Recusado", 1), else_=0)),
            func.sum(case((func.length(func.trim(Guest.table_name)) > 0, 1), else_=0)),
            func.sum(case((Guest.invitation_sent.is_(True), 1), else_=0)),
            func.sum(case((Guest.gift_received.is_(True), 1), else_=0)),
        ).where(*conditions)
    ).one()
    total, confirmed, pending, declined, seated, invitations_sent, gifts_received = (
        int(value or 0) for value in values
    )
    return {
        "total": total,
        "confirmed": confirmed,
        "pending": pending,
        "declined": declined,
        "seated": seated,
        "invitations_sent": invitations_sent,
        "gifts_received": gifts_received,
        "confirmation_rate": round((confirmed / total * 100) if total else 0, 1),
    }


def guest_filter_options(db: Session) -> dict[str, list[str]]:
    conditions = active_guest_condition()

    def distinct_values(column: Any) -> list[str]:
        return list(
            db.scalars(
                select(column)
                .where(*conditions, func.length(func.trim(column)) > 0)
                .distinct()
                .order_by(column)
            ).all()
        )

    return {
        "congregations": distinct_values(Guest.congregation),
        "tables": distinct_values(Guest.table_name),
        "statuses": list(RSVP_STATUSES),
        "sides": list(SIDES),
        "age_groups": list(AGE_GROUPS),
    }


def list_guests(
    db: Session,
    *,
    q: str = "",
    status: str = "",
    side: str = "",
    age_group: str = "",
    congregation: str = "",
    table_name: str = "",
    invitation: str = "",
    gift: str = "",
    sort: str = "name",
    direction: str = "asc",
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    updated_user = aliased(User)
    created_user = aliased(User)
    conditions: list[Any] = list(active_guest_condition())
    search = q.strip()
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Guest.name.ilike(pattern),
                Guest.congregation.ilike(pattern),
                Guest.table_name.ilike(pattern),
                Guest.phone.ilike(pattern),
                Guest.email.ilike(pattern),
                Guest.notes.ilike(pattern),
            )
        )
    if status:
        conditions.append(Guest.rsvp_status == status)
    if side:
        conditions.append(Guest.side == side)
    if age_group:
        conditions.append(Guest.age_group == age_group)
    if congregation:
        conditions.append(Guest.congregation == congregation)
    if table_name:
        conditions.append(Guest.table_name == table_name)
    if invitation in {"sent", "pending"}:
        conditions.append(Guest.invitation_sent.is_(invitation == "sent"))
    if gift in {"received", "pending"}:
        conditions.append(Guest.gift_received.is_(gift == "received"))

    total_filtered = int(db.scalar(select(func.count(Guest.id)).where(*conditions)) or 0)
    sort_column = SORT_COLUMNS.get(sort, Guest.name)
    ordering = sort_column.desc() if direction == "desc" else sort_column.asc()
    rows = db.execute(
        select(Guest, updated_user.name, created_user.name)
        .outerjoin(updated_user, Guest.updated_by_id == updated_user.id)
        .outerjoin(created_user, Guest.created_by_id == created_user.id)
        .where(*conditions)
        .order_by(ordering, Guest.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return (
        [
            serialize_guest(guest, updated_by=updated_by or "", created_by=created_by or "")
            for guest, updated_by, created_by in rows
        ],
        total_filtered,
    )


def active_guest(db: Session, guest_id: int) -> Guest | None:
    return db.scalar(select(Guest).where(Guest.id == guest_id, *active_guest_condition()))


def current_revision(db: Session) -> str | None:
    value = db.scalar(select(func.max(Guest.updated_at)).where(*active_guest_condition()))
    return timestamp_string(value)
