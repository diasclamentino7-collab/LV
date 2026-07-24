from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.planning import BudgetCategory, Expense, Payment
from app.services.finance import financial_summary


def test_financial_summary_separates_planned_expenses_and_paid() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        category = BudgetCategory(name="Receção", planned_limit=Decimal("1000"))
        db.add(category)
        db.flush()
        db.add_all(
            [
                Expense(
                    category_id=category.id,
                    description="Espaço",
                    amount=Decimal("400"),
                    expense_date=date(2026, 7, 24),
                    status="Confirmada",
                ),
                Expense(
                    category_id=category.id,
                    description="Opção cancelada",
                    amount=Decimal("100"),
                    expense_date=date(2026, 7, 24),
                    status="Cancelada",
                ),
                Payment(
                    category_id=category.id,
                    amount=Decimal("200"),
                    payment_date=date(2026, 7, 24),
                    status="Pago",
                ),
            ]
        )
        db.commit()

        summary = financial_summary(db, Decimal("2000"))

    assert summary["allocated"] == Decimal("1000")
    assert summary["expenses"] == Decimal("400")
    assert summary["paid"] == Decimal("200")
    assert summary["remaining"] == Decimal("1600")
    assert summary["percentage"] == 20
