from sqlalchemy.orm import Session

from app.models.core import Activity


def record_activity(
    db: Session, user_id: int | None, action_type: str, description: str, module: str = "system"
) -> None:
    """Append an audit entry within the caller's transaction."""
    db.add(
        Activity(user_id=user_id, action_type=action_type, description=description, module=module)
    )
