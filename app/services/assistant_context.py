"""Read-only wedding-planning snapshot handed to the AI assistant's system prompt.

Everything here is the couple's own planning data, sent to Groq on every
message. Guest phone/email/address are deliberately left out — that's
third-party contact data belonging to people who never agreed to it being
sent to an external AI provider. Legal document notes are left out too,
since they're the most likely place for ID/passport-style identifiers.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import ProjectSettings
from app.models.planning import Guest, LegalDocument, Task, Vendor
from app.services.budget import budget_snapshot
from app.services.finance import financial_summary
from app.services.guests import active_guest_condition, guest_stats
from app.services.record_deletion import not_tombstoned

MAX_LISTED_RECORDS = 300


def _decimal_or_zero(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value or "0").replace(",", "."))
        return parsed if parsed.is_finite() and parsed >= 0 else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _guest_lines(db: Session) -> list[str]:
    guests = db.scalars(
        select(Guest).where(*active_guest_condition()).order_by(Guest.name).limit(MAX_LISTED_RECORDS)
    ).all()
    lines = []
    for guest in guests:
        bits = [guest.rsvp_status or "Pendente"]
        if guest.side:
            bits.append(guest.side)
        if guest.table_name:
            bits.append(f"mesa {guest.table_name}")
        if guest.dietary_requirements:
            bits.append(f"dieta: {guest.dietary_requirements}")
        if guest.special_needs:
            bits.append(f"necessidades: {guest.special_needs}")
        lines.append(f"- {guest.name} ({', '.join(bits)})")
    return lines


def _task_lines(db: Session) -> list[str]:
    tasks = db.scalars(
        select(Task)
        .where(Task.is_archived.is_(False), not_tombstoned(Task))
        .order_by(Task.due_date.is_(None), Task.due_date, Task.title)
        .limit(MAX_LISTED_RECORDS)
    ).all()
    lines = []
    for task in tasks:
        bits = [task.status or "Pendente"]
        if task.assignee:
            bits.append(f"responsável: {task.assignee}")
        if task.due_date:
            bits.append(f"prazo: {task.due_date.strftime('%d/%m/%Y')}")
        if task.priority:
            bits.append(f"prioridade: {task.priority}")
        lines.append(f"- {task.title} ({', '.join(bits)})")
    return lines


def _vendor_lines(db: Session, currency: str) -> list[str]:
    vendors = db.scalars(
        select(Vendor)
        .where(Vendor.is_archived.is_(False), not_tombstoned(Vendor))
        .order_by(Vendor.vendor_type, Vendor.company)
        .limit(MAX_LISTED_RECORDS)
    ).all()
    lines = []
    for vendor in vendors:
        bits = [
            f"acordado: {vendor.agreed_price} {currency}",
            f"pago: {vendor.paid_amount} {currency}",
        ]
        if vendor.notes:
            bits.append(f"notas: {vendor.notes}")
        lines.append(f"- {vendor.company} ({vendor.vendor_type}) — {', '.join(bits)}")
    return lines


def _budget_category_lines(db: Session, total_budget: Decimal, currency: str) -> list[str]:
    snapshot = budget_snapshot(db, total_budget)
    return [
        (
            f"- {category['name']}: limite {category['planned_limit']} {currency}, "
            f"gasto {category['expenses']} {currency}, resta {category['remaining']} {currency}"
        )
        for category in snapshot["categories"]
    ]


def _legal_document_lines(db: Session) -> list[str]:
    documents = db.scalars(
        select(LegalDocument)
        .where(LegalDocument.is_archived.is_(False), not_tombstoned(LegalDocument))
        .order_by(LegalDocument.due_date.is_(None), LegalDocument.due_date, LegalDocument.title)
        .limit(MAX_LISTED_RECORDS)
    ).all()
    lines = []
    for document in documents:
        bits = [document.status or "Pendente"]
        if document.responsible:
            bits.append(f"responsável: {document.responsible}")
        if document.due_date:
            bits.append(f"prazo: {document.due_date.strftime('%d/%m/%Y')}")
        lines.append(f"- {document.title} ({document.document_type}) — {', '.join(bits)}")
    return lines


def build_context_snapshot(db: Session, settings: ProjectSettings) -> str:
    """Summarize the couple's current data for the assistant.

    Includes the couple's own planning data (guests' RSVP/seating/dietary
    info, tasks, vendors, budget, legal-process status) but never guest
    contact details (phone/email/address) or legal document identifiers —
    those stay out of any request sent to the AI provider.
    """

    couple = f"{settings.partner_one_name or 'Vítor'} e {settings.partner_two_name or 'Leonor'}"
    wedding_date = (
        settings.wedding_date.strftime("%d/%m/%Y")
        if settings.wedding_date
        else "ainda não definida"
    )
    total_budget = _decimal_or_zero(settings.total_budget)
    guest_totals = guest_stats(db)
    finance = financial_summary(db, total_budget)
    currency = settings.currency

    sections = [
        f"Casal: {couple}.",
        f"Data do casamento: {wedding_date}.",
        f"Estilo: {settings.wedding_style or 'não definido'}.",
        f"Local da cerimónia: {settings.ceremony_venue or 'não definido'}.",
        f"Local da receção: {settings.reception_venue or 'não definido'}.",
        (
            f"Convidados: {guest_totals['total']} no total, {guest_totals['confirmed']} "
            f"confirmados, {guest_totals['pending']} por responder, "
            f"{guest_totals['declined']} recusaram."
        ),
        (
            f"Orçamento total: {finance['total']} {currency}. "
            f"Despesas registadas: {finance['expenses']} {currency}. "
            f"Restante: {finance['remaining']} {currency}."
        ),
    ]

    guest_lines = _guest_lines(db)
    if guest_lines:
        sections.append(
            "Lista de convidados (sem contactos, por privacidade):\n" + "\n".join(guest_lines)
        )

    task_lines = _task_lines(db)
    if task_lines:
        sections.append("Tarefas:\n" + "\n".join(task_lines))

    vendor_lines = _vendor_lines(db, currency)
    if vendor_lines:
        sections.append("Fornecedores:\n" + "\n".join(vendor_lines))

    budget_lines = _budget_category_lines(db, total_budget, currency)
    if budget_lines:
        sections.append("Categorias de orçamento:\n" + "\n".join(budget_lines))

    legal_lines = _legal_document_lines(db)
    if legal_lines:
        sections.append(
            "Processo legal (sem detalhes de documentos, por privacidade):\n"
            + "\n".join(legal_lines)
        )

    return "\n\n".join(sections)
