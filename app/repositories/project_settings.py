"""Persistence helpers for the single shared wedding project configuration."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import ProjectSettings


def get_project_settings(
    db: Session,
    *,
    create: bool = True,
    user_id: int | None = None,
) -> ProjectSettings | None:
    """Return the canonical settings row, creating it safely when requested.

    Older installations created the first row with an automatic identifier.
    Looking up the oldest row first preserves that data. New installations use
    the stable identifier ``1`` so two workers cannot create two configurations.
    """

    settings = db.scalar(select(ProjectSettings).order_by(ProjectSettings.id).limit(1))
    if settings is not None or not create:
        return settings

    settings = ProjectSettings(id=1, created_by_id=user_id, updated_by_id=user_id)
    db.add(settings)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        settings = db.scalar(select(ProjectSettings).order_by(ProjectSettings.id).limit(1))
        if settings is None:
            raise
    else:
        db.refresh(settings)
    return settings
