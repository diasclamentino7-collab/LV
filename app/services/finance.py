"""Single financial source of truth used by every read model."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.planning import BudgetCategory, Expense, Payment


def _decimal(value: object) -> Decimal:
    return Decimal(value or 0)


def financial_summary(db: Session, total_budget: Decimal) -> dict[str, Decimal | int]:
    """Build the canonical financial snapshot from persisted records."""
    paid = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.is_archived.is_(False), Payment.status == "Pago"
            )
        )
    )
    pending = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.is_archived.is_(False), Payment.status == "Pendente"
            )
        )
    )
    expenses = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.is_archived.is_(False), Expense.status != "Cancelada"
            )
        )
    )
    allocated = _decimal(
        db.scalar(
            select(func.coalesce(func.sum(BudgetCategory.planned_limit), 0)).where(
                BudgetCategory.is_archived.is_(False)
            )
        )
    )
    categories = db.scalar(
        select(func.count())
        .select_from(BudgetCategory)
        .where(BudgetCategory.is_archived.is_(False))
    )
    percentage = int((expenses / total_budget * 100) if total_budget else 0)
    return {
        "total": total_budget,
        "allocated": allocated,
        "unallocated": total_budget - allocated,
        "expenses": expenses,
        "paid": paid,
        "pending": pending,
        "remaining": total_budget - expenses,
        "percentage": percentage,
        "progress_percentage": min(100, max(0, percentage)),
        "categories": categories,
    }
