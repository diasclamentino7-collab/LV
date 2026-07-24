"""Read models for the budget page built from persisted financial records."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.planning import BudgetCategory, Expense
from app.services.finance import financial_summary

PERCENTAGE_QUANTUM = Decimal("0.01")


def _decimal(value: object) -> Decimal:
    """Return a finite decimal while preserving legitimate negative balances."""

    try:
        parsed = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return parsed if parsed.is_finite() else Decimal("0")


def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= 0:
        return None
    return ((numerator / denominator) * 100).quantize(
        PERCENTAGE_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def budget_snapshot(
    db: Session,
    total_budget: object,
    *,
    search: str = "",
) -> dict[str, Any]:
    """Return the canonical totals and a precise active-category breakdown.

    ``financial_summary`` remains the single source of truth for global values.
    The category query only provides the drill-down required by the budget page.
    Archived and cancelled records never contribute to the visible breakdown.
    """

    summary = financial_summary(db, total_budget)  # type: ignore[arg-type]
    expense_total = _decimal(summary["expenses"])
    configured_total = _decimal(summary["total"])
    exact_percentage = _percentage(expense_total, configured_total) or Decimal("0")

    expense_join = and_(
        Expense.category_id == BudgetCategory.id,
        Expense.is_archived.is_(False),
        Expense.status != "Cancelada",
    )
    statement = (
        select(
            BudgetCategory,
            func.coalesce(func.sum(Expense.amount), 0).label("expense_total"),
        )
        .outerjoin(Expense, expense_join)
        .where(BudgetCategory.is_archived.is_(False))
        .group_by(BudgetCategory.id)
    )
    normalized_search = search.strip()
    if normalized_search:
        statement = statement.where(BudgetCategory.name.ilike(f"%{normalized_search}%"))

    rows = db.execute(statement).all()
    visible_expense_total = sum(
        (_decimal(row.expense_total) for row in rows),
        start=Decimal("0"),
    )
    categories: list[dict[str, Any]] = []
    for row in rows:
        category = row.BudgetCategory
        planned_limit = _decimal(category.planned_limit)
        expenses = _decimal(row.expense_total)
        usage_percentage = _percentage(expenses, planned_limit)
        share_percentage = _percentage(expenses, visible_expense_total) or Decimal("0")
        categories.append(
            {
                "id": category.id,
                "name": category.name,
                "planned_limit": planned_limit,
                "expenses": expenses,
                "remaining": planned_limit - expenses,
                "usage_percentage": usage_percentage,
                "progress_percentage": min(
                    Decimal("100"),
                    max(
                        Decimal("0"),
                        usage_percentage
                        if usage_percentage is not None
                        else Decimal("100")
                        if expenses > 0
                        else Decimal("0"),
                    ),
                ),
                "share_percentage": share_percentage,
                "over_limit": planned_limit > 0 and expenses > planned_limit,
                "has_limit": planned_limit > 0,
                "updated_at": category.updated_at,
            }
        )

    categories.sort(
        key=lambda item: (
            -item["expenses"],
            item["name"].casefold(),
            item["id"],
        )
    )
    return {
        "summary": summary,
        "exact_percentage": exact_percentage,
        "progress_percentage": min(
            Decimal("100"),
            max(Decimal("0"), exact_percentage),
        ),
        "categories": categories,
        "visible_expense_total": visible_expense_total,
    }


def serialize_budget_snapshot(
    snapshot: dict[str, Any],
    *,
    currency: str,
) -> dict[str, Any]:
    """Convert a budget snapshot to a stable, precision-safe JSON payload."""

    summary = snapshot["summary"]

    def money(value: object) -> str:
        return format(_decimal(value), ".2f")

    def percent(value: object) -> str:
        return format(_decimal(value), ".2f")

    categories = [
        {
            "id": item["id"],
            "name": item["name"],
            "planned_limit": money(item["planned_limit"]),
            "expenses": money(item["expenses"]),
            "remaining": money(item["remaining"]),
            "usage_percentage": (
                percent(item["usage_percentage"]) if item["usage_percentage"] is not None else None
            ),
            "progress_percentage": percent(item["progress_percentage"]),
            "share_percentage": percent(item["share_percentage"]),
            "over_limit": item["over_limit"],
            "has_limit": item["has_limit"],
            "updated_at": (item["updated_at"].isoformat() if item["updated_at"] else None),
        }
        for item in snapshot["categories"]
    ]
    return {
        "currency": currency,
        "summary": {
            "total": money(summary["total"]),
            "allocated": money(summary["allocated"]),
            "unallocated": money(summary["unallocated"]),
            "expenses": money(summary["expenses"]),
            "paid": money(summary["paid"]),
            "pending": money(summary["pending"]),
            "remaining": money(summary["remaining"]),
            "percentage": percent(snapshot["exact_percentage"]),
            "progress_percentage": percent(snapshot["progress_percentage"]),
            "categories": int(summary["categories"]),
        },
        "categories": categories,
    }
