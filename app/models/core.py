from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampedModel


class User(TimestampedModel, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Activity(TimestampedModel, Base):
    __tablename__ = "activities"

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    module: Mapped[str] = mapped_column(String(50), default="system", index=True)
    description: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class WorkspaceRecord(TimestampedModel, Base):
    """Persistent records for smaller modules as they are progressively specialized."""

    __tablename__ = "workspace_records"

    module: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    responsible: Mapped[str] = mapped_column(String(100), default="")
    priority: Mapped[str] = mapped_column(String(30), default="Média")
    comments: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    contact: Mapped[str] = mapped_column(String(200), default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(50), default="Pendente")
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attachment_path: Mapped[str] = mapped_column(String(500), default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class RecordTombstone(Base):
    """Append-only marker for records removed permanently from the interface.

    The domain row itself is deliberately retained.  This marker hides it from
    everyday views while keeping an immutable snapshot and deletion audit trail
    available for technical recovery.
    """

    __tablename__ = "record_tombstones"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            name="uq_record_tombstones_entity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    module: Mapped[str] = mapped_column(String(50), index=True)
    snapshot_json: Mapped[str] = mapped_column(Text)
    deleted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class ProjectSettings(TimestampedModel, Base):
    __tablename__ = "project_settings"

    project_name: Mapped[str] = mapped_column(String(150), default="LV – Wedding Planner")
    partner_one_name: Mapped[str] = mapped_column(String(100), default="")
    partner_two_name: Mapped[str] = mapped_column(String(100), default="")
    primary_color: Mapped[str] = mapped_column(String(20), default="#D88BA7")
    secondary_color: Mapped[str] = mapped_column(String(20), default="#F8DCE8")
    accent_color: Mapped[str] = mapped_column(String(20), default="#C9A46A")
    background_color: Mapped[str] = mapped_column(String(20), default="#FAF8F6")
    logo_path: Mapped[str] = mapped_column(String(500), default="")
    wedding_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wedding_style: Mapped[str] = mapped_column(String(50), default="Mid-century vintage")
    wedding_timezone: Mapped[str] = mapped_column(String(64), default="Europe/Lisbon")
    wedding_city: Mapped[str] = mapped_column(String(150), default="")
    ceremony_venue: Mapped[str] = mapped_column(String(200), default="")
    reception_venue: Mapped[str] = mapped_column(String(200), default="")
    total_budget: Mapped[str] = mapped_column(String(50), default="0")
    currency: Mapped[str] = mapped_column(String(10), default="EUR")
    guest_target: Mapped[int] = mapped_column(Integer, default=0)
    budget_alert_percent: Mapped[int] = mapped_column(Integer, default=80)
    language: Mapped[str] = mapped_column(String(10), default="pt-PT")
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=7)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    default_assignee: Mapped[str] = mapped_column(String(100), default="")
    default_task_priority: Mapped[str] = mapped_column(String(30), default="Média")
    dashboard_show_countdown: Mapped[bool] = mapped_column(Boolean, default=True)
    dashboard_show_finance: Mapped[bool] = mapped_column(Boolean, default=True)
    dashboard_show_activity: Mapped[bool] = mapped_column(Boolean, default=True)
    dashboard_show_moodboard: Mapped[bool] = mapped_column(Boolean, default=True)
    motion_preference: Mapped[str] = mapped_column(String(20), default="full")
    settings_version: Mapped[int] = mapped_column(Integer, default=1)
