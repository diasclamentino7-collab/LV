"""Database-backed session helpers shared by protected web routes."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.core import User


def authenticated_user(db: Session, request: Request) -> User | None:
    """Return the active account represented by the current signed session."""

    user_id = request.session.get("user_id")
    session_version = request.session.get("session_version")
    if user_id is None or session_version is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.session_version != session_version:
        request.session.clear()
        return None
    return user


def start_user_session(request: Request, user: User) -> None:
    """Replace any previous state with one authenticated user session."""

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["user_name"] = user.name
    request.session["session_version"] = user.session_version
