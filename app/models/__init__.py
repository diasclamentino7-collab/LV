"""SQLAlchemy models; import every model here for Alembic discovery."""

from app.db.base import Base
from app.models.core import Activity, ProjectSettings, User, WorkspaceRecord
from app.models.moodboard import (
    MoodboardBoard,
    MoodboardCollection,
    MoodboardInspirationPlacement,
    MoodboardItem,
)
from app.models.planning import BudgetCategory, Expense, Guest, LegalDocument, Payment, Task, Vendor

__all__ = [
    "Activity",
    "Base",
    "BudgetCategory",
    "Expense",
    "Guest",
    "LegalDocument",
    "MoodboardBoard",
    "MoodboardCollection",
    "MoodboardInspirationPlacement",
    "MoodboardItem",
    "Payment",
    "ProjectSettings",
    "Task",
    "User",
    "Vendor",
    "WorkspaceRecord",
]
