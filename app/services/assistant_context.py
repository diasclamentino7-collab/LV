"""Read-only wedding-planning snapshot handed to the AI assistant's system prompt."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.core import ProjectSettings
from app.models.planning import Task
from app.services.finance import financial_summary
from app.services.guests import guest_stats
from app.services.record_deletion import not_tombstoned


def _decimal_or_zero(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value or "0").replace(",", "."))
        return parsed if parsed.is_finite() and parsed >= 0 else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def build_context_snapshot(db: Session, settings: ProjectSettings) -> str:
    """Summarize the couple's current data for the assistant, without exposing raw records."""

    couple = f"{settings.partner_one_name or 'Vítor'} e {settings.partner_two_name or 'Leonor'}"
    wedding_date = (
        settings.wedding_date.strftime("%d/%m/%Y")
        if settings.wedding_date
        else "ainda não definida"
    )
    guests = guest_stats(db)
    finance = financial_summary(db, _decimal_or_zero(settings.total_budget))
    tasks_total = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.is_archived.is_(False), not_tombstoned(Task))
        )
        or 0
    )
    tasks_done = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.is_archived.is_(False),
                Task.status == "Concluído",
                not_tombstoned(Task),
            )
        )
        or 0
    )

    return "\n".join(
        [
            f"Casal: {couple}.",
            f"Data do casamento: {wedding_date}.",
            f"Estilo: {settings.wedding_style or 'não definido'}.",
            f"Local da cerimónia: {settings.ceremony_venue or 'não definido'}.",
            f"Local da receção: {settings.reception_venue or 'não definido'}.",
            (
                f"Convidados: {guests['total']} no total, {guests['confirmed']} confirmados, "
                f"{guests['pending']} por responder, {guests['declined']} recusaram."
            ),
            f"Tarefas: {tasks_done} de {tasks_total} concluídas.",
            (
                f"Orçamento total: {finance['total']} {settings.currency}. "
                f"Despesas registadas: {finance['expenses']} {settings.currency}. "
                f"Restante: {finance['remaining']} {settings.currency}."
            ),
        ]
    )
