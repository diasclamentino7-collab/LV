from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampedModel


class MoodboardBoard(TimestampedModel, Base):
    __tablename__ = "moodboard_boards"

    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MoodboardCollection(TimestampedModel, Base):
    __tablename__ = "moodboard_collections"

    board_id: Mapped[int] = mapped_column(ForeignKey("moodboard_boards.id"), index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MoodboardItem(TimestampedModel, Base):
    __tablename__ = "moodboard_items"

    collection_id: Mapped[int] = mapped_column(ForeignKey("moodboard_collections.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(1000))
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    tags: Mapped[str] = mapped_column(String(300), default="")
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
