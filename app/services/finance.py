"""Single financial source of truth used by every read model."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.planning import BudgetCategory, Payment


def financial_summary(db: Session, total_budget: Decimal) -> dict[str, Decimal | int]:
    paid = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.is_archived.is_(False), Payment.status == "Pago"
        )
    )
    categories = db.scalar(
        select(func.count())
        .select_from(BudgetCategory)
        .where(BudgetCategory.is_archived.is_(False))
    )
    paid_value = Decimal(paid)
    return {
        "total": total_budget,
        "paid": paid_value,
        "remaining": total_budget - paid_value,
        "percentage": int((paid_value / total_budget * 100) if total_budget else 0),
        "categories": categories,
    }
