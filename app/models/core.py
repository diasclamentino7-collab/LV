from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampedModel


class User(TimestampedModel, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Activity(TimestampedModel, Base):
    __tablename__ = "activities"

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    module: Mapped[str] = mapped_column(String(50), default="system", index=True)
    description: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
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


class ProjectSettings(TimestampedModel, Base):
    __tablename__ = "project_settings"

    project_name: Mapped[str] = mapped_column(String(150), default="LV – Wedding Planner")
    primary_color: Mapped[str] = mapped_column(String(20), default="#D88BA7")
    secondary_color: Mapped[str] = mapped_column(String(20), default="#F8DCE8")
    logo_path: Mapped[str] = mapped_column(String(500), default="")
    wedding_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_budget: Mapped[str] = mapped_column(String(50), default="0")
    currency: Mapped[str] = mapped_column(String(10), default="EUR")
    language: Mapped[str] = mapped_column(String(10), default="pt-PT")
