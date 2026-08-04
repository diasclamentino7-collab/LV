from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampedModel


class AssistantMessage(TimestampedModel, Base):
    """One turn of a household conversation with a configured AI assistant."""

    __tablename__ = "assistant_messages"

    provider: Mapped[str] = mapped_column(String(20), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
