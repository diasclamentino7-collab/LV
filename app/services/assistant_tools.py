"""Tools the AI assistant can call to act on the couple's planning data.

Most tools here are safely reversible: they only create new records or
archive existing ones. Archived records stay recoverable in ``/deleted``,
exactly like anything archived by hand from the app's own screens.

One tool, ``permanently_delete_record``, is different: it mirrors the
app's own "type APAGAR" permanent-deletion flow (see
``app.services.record_deletion.create_tombstone``), and is only ever
reachable for a record that is *already* archived, and only when the
caller passes the literal confirmation string "APAGAR". Even then, the
underlying database row is never actually dropped — only tombstoned, the
same non-destructive mechanism the rest of the app uses — but it does
remove the last UI-level path back to the record. The system prompt
instructs the model to only use it after a human has unambiguously
confirmed they want a permanent deletion, not just a removal.

Each executor returns a small JSON-serializable dict that is fed straight
back to the model as the tool result, so keep messages short and in
Portuguese — the model quotes them almost verbatim in its reply.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import User, WorkspaceRecord
from app.models.moodboard import (
    MoodboardBoard,
    MoodboardCollection,
    MoodboardInspirationPlacement,
    MoodboardItem,
)
from app.models.planning import (
    BudgetCategory,
    Expense,
    Guest,
    LegalDocument,
    Payment,
    Task,
    Vendor,
)
from app.services.activity import record_activity
from app.services.guests import AGE_GROUPS, RSVP_STATUSES, SIDES, active_guest_condition
from app.services.record_deletion import create_tombstone, not_tombstoned

FETCH_TIMEOUT_SECONDS = 15.0
MAX_FETCHED_CHARS = 6000
TASK_PRIORITIES = ("Baixa", "Média", "Alta")
TASK_STATUSES = ("Pendente", "Em curso", "Concluído")
LEGAL_STATUSES = TASK_STATUSES
COMMUNICATION_CATEGORIES = ("Nota", "Ideia", "Decisão", "Lembrete", "Tarefa rápida")
COMMUNICATION_PRIORITIES = TASK_PRIORITIES
EXPENSE_STATUSES = ("Pendente", "Confirmada", "Cancelada")
PAYMENT_STATUSES = ("Pago", "Pendente")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_event_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        parsed_date = _parse_date(value)
        return datetime.combine(parsed_date, datetime.min.time()) if parsed_date else None


def _parse_amount(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value or 0).replace(",", "."))
        return parsed if parsed.is_finite() and parsed >= 0 else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _match_enum(value: object, options: tuple[str, ...]) -> str | None:
    """Match a model-supplied value against an enum, tolerating how it was written.

    The generic dispatcher tools no longer carry per-field JSON-schema enums
    (that was most of the token cost we cut), so the model may send
    differently-cased values (e.g. "noivo" instead of "Noivo") or, in
    Portuguese, a grammatically gender-agreed form of a fixed-form status
    (e.g. "confirmada" for a female guest, when the app's enum value is the
    invariant "Confirmado"). Without this, those would silently fail an
    exact-match check and the field would just be dropped.
    """

    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    # Exact matches always win, across *all* options, before any fuzzy
    # gender-swap attempt — "Noivo" and "Noiva" are both real, distinct
    # options (not gendered forms of each other), so an exact match on one
    # must never lose to a fuzzy match against the other.
    for option in options:
        if lowered == option.lower():
            return option
    for option in options:
        option_lower = option.lower()
        if (lowered[:-1] == option_lower[:-1]) and {lowered[-1:], option_lower[-1:]} <= {"a", "o"}:
            return option
    return None


def _find_guest(db: Session, name: str) -> Guest | None:
    return db.scalar(select(Guest).where(*active_guest_condition(), Guest.name.ilike(name.strip())))


def _find_task(db: Session, title: str) -> Task | None:
    return db.scalar(
        select(Task).where(
            Task.is_archived.is_(False), not_tombstoned(Task), Task.title.ilike(title.strip())
        )
    )


def _find_vendor(db: Session, company: str) -> Vendor | None:
    return db.scalar(
        select(Vendor).where(
            Vendor.is_archived.is_(False),
            not_tombstoned(Vendor),
            Vendor.company.ilike(company.strip()),
        )
    )


def _find_legal_document(db: Session, title: str) -> LegalDocument | None:
    return db.scalar(
        select(LegalDocument).where(
            LegalDocument.is_archived.is_(False),
            not_tombstoned(LegalDocument),
            LegalDocument.title.ilike(title.strip()),
        )
    )


def _find_budget_category(db: Session, name: str) -> BudgetCategory | None:
    return db.scalar(
        select(BudgetCategory).where(
            BudgetCategory.is_archived.is_(False),
            not_tombstoned(BudgetCategory),
            BudgetCategory.name.ilike(name.strip()),
        )
    )


def _find_expenses(
    db: Session, description: str, category_name: str | None = None
) -> list[Expense]:
    conditions = [
        Expense.is_archived.is_(False),
        not_tombstoned(Expense),
        Expense.description.ilike(description.strip()),
    ]
    if category_name:
        category = _find_budget_category(db, category_name)
        if category is not None:
            conditions.append(Expense.category_id == category.id)
    return list(db.scalars(select(Expense).where(*conditions)).all())


def _find_payments(db: Session, reference: str) -> list[Payment]:
    if not reference:
        return []
    return list(
        db.scalars(
            select(Payment).where(
                Payment.is_archived.is_(False),
                not_tombstoned(Payment),
                Payment.reference.ilike(reference.strip()),
            )
        ).all()
    )


def _find_communication(db: Session, title: str) -> WorkspaceRecord | None:
    return db.scalar(
        select(WorkspaceRecord).where(
            WorkspaceRecord.module == "communication",
            WorkspaceRecord.is_archived.is_(False),
            not_tombstoned(WorkspaceRecord),
            WorkspaceRecord.title.ilike(title.strip()),
        )
    )


def _find_moodboard_item(db: Session, title: str) -> MoodboardItem | None:
    return db.scalar(
        select(MoodboardItem).where(
            MoodboardItem.is_archived.is_(False),
            not_tombstoned(MoodboardItem),
            MoodboardItem.title.ilike(title.strip()),
        )
    )


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme in {"http", "https"} and parsed.netloc) and len(value) <= 1000


# --- Guests -----------------------------------------------------------------


def add_guest(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    if not name:
        return {"ok": False, "error": "É preciso um nome para adicionar um convidado."}
    if _find_guest(db, name) is not None:
        return {"ok": False, "error": f"Já existe um convidado chamado {name}."}
    side = _match_enum(args.get("side"), SIDES) or ""
    rsvp_status = _match_enum(args.get("rsvp_status"), RSVP_STATUSES) or "Pendente"
    age_group = _match_enum(args.get("age_group"), AGE_GROUPS) or "Adulto"
    guest = Guest(
        name=name,
        side=side,
        rsvp_status=rsvp_status,
        age_group=age_group,
        table_name=str(args.get("table_name", "") or ""),
        dietary_requirements=str(args.get("dietary_requirements", "") or ""),
        special_needs=str(args.get("special_needs", "") or ""),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(guest)
    record_activity(db, user.id, "criou", f"assistente adicionou convidado: {name}", "guests")
    db.commit()
    return {"ok": True, "message": f"Convidado {name} adicionado, estado {rsvp_status}."}


def update_guest(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    guest = _find_guest(db, name) if name else None
    if guest is None:
        return {"ok": False, "error": f"Não encontrei nenhum convidado ativo chamado {name}."}
    matched_rsvp_status = _match_enum(args.get("rsvp_status"), RSVP_STATUSES)
    if matched_rsvp_status:
        guest.rsvp_status = matched_rsvp_status
    matched_side = _match_enum(args.get("side"), SIDES)
    if matched_side:
        guest.side = matched_side
    matched_age_group = _match_enum(args.get("age_group"), AGE_GROUPS)
    if matched_age_group:
        guest.age_group = matched_age_group
    if args.get("table_name") is not None:
        guest.table_name = str(args["table_name"])
    if args.get("dietary_requirements") is not None:
        guest.dietary_requirements = str(args["dietary_requirements"])
    if args.get("special_needs") is not None:
        guest.special_needs = str(args["special_needs"])
    guest.updated_by_id = user.id
    guest.updated_at = datetime.now(UTC)
    record_activity(
        db, user.id, "alterou", f"assistente atualizou convidado: {guest.name}", "guests"
    )
    guest_name = guest.name
    db.commit()
    return {"ok": True, "message": f"Dados de {guest_name} atualizados."}


def remove_guest(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    guest = _find_guest(db, name) if name else None
    if guest is None:
        return {"ok": False, "error": f"Não encontrei nenhum convidado ativo chamado {name}."}
    guest.is_archived = True
    guest.updated_by_id = user.id
    guest_name = guest.name
    record_activity(
        db, user.id, "arquivou", f"assistente removeu convidado: {guest_name}", "guests"
    )
    db.commit()
    return {
        "ok": True,
        "message": f"{guest_name} foi removido da lista (recuperável em Todos os eliminados).",
    }


# --- Tasks / checklist --------------------------------------------------------


def add_task(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        return {"ok": False, "error": "É preciso um título para criar uma tarefa."}
    priority = _match_enum(args.get("priority"), TASK_PRIORITIES) or "Média"
    status = _match_enum(args.get("status"), TASK_STATUSES) or "Pendente"
    task = Task(
        title=title,
        category=str(args.get("category", "") or ""),
        priority=priority,
        assignee=str(args.get("assignee", "") or ""),
        due_date=_parse_date(args.get("due_date")),
        status=status,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(task)
    record_activity(db, user.id, "criou", f"assistente adicionou tarefa: {title}", "checklist")
    db.commit()
    return {"ok": True, "message": f"Tarefa '{title}' criada, estado {status}."}


def update_task(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    task = _find_task(db, title) if title else None
    if task is None:
        return {"ok": False, "error": f"Não encontrei nenhuma tarefa ativa chamada '{title}'."}
    if args.get("status") is not None:
        matched_status = _match_enum(args.get("status"), TASK_STATUSES)
        if not matched_status:
            return {
                "ok": False,
                "error": f"Estado inválido; use um de: {', '.join(TASK_STATUSES)}.",
            }
        task.status = matched_status
    matched_priority = _match_enum(args.get("priority"), TASK_PRIORITIES)
    if matched_priority:
        task.priority = matched_priority
    if args.get("description") is not None:
        task.description = str(args["description"])
    if args.get("category") is not None:
        task.category = str(args["category"])
    if args.get("assignee") is not None:
        task.assignee = str(args["assignee"])
    if "due_date" in args:
        task.due_date = _parse_date(args.get("due_date"))
    if args.get("comments") is not None:
        task.comments = str(args["comments"])
    task.updated_by_id = user.id
    task.updated_at = datetime.now(UTC)
    task_title = task.title
    record_activity(
        db, user.id, "alterou", f"assistente atualizou tarefa: {task_title}", "checklist"
    )
    db.commit()
    return {"ok": True, "message": f"Tarefa '{task_title}' atualizada."}


def remove_task(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    task = _find_task(db, title) if title else None
    if task is None:
        return {"ok": False, "error": f"Não encontrei nenhuma tarefa ativa chamada '{title}'."}
    task.is_archived = True
    task.updated_by_id = user.id
    task_title = task.title
    record_activity(
        db, user.id, "arquivou", f"assistente removeu tarefa: {task_title}", "checklist"
    )
    db.commit()
    return {
        "ok": True,
        "message": f"Tarefa '{task_title}' removida (recuperável em Todos os eliminados).",
    }


# --- Vendors -------------------------------------------------------------------


def add_vendor(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    company = str(args.get("company", "")).strip()
    vendor_type = str(args.get("vendor_type", "")).strip()
    if not company or not vendor_type:
        return {"ok": False, "error": "É preciso a empresa e o tipo de fornecedor."}
    if _find_vendor(db, company) is not None:
        return {"ok": False, "error": f"Já existe um fornecedor chamado {company}."}
    vendor = Vendor(
        vendor_type=vendor_type,
        company=company,
        contact_name=str(args.get("contact_name", "") or ""),
        phone=str(args.get("phone", "") or ""),
        email=str(args.get("email", "") or ""),
        website=str(args.get("website", "") or ""),
        agreed_price=_parse_amount(args.get("agreed_price")),
        notes=str(args.get("notes", "") or ""),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(vendor)
    record_activity(db, user.id, "criou", f"assistente adicionou fornecedor: {company}", "vendors")
    db.commit()
    return {"ok": True, "message": f"Fornecedor {company} ({vendor_type}) adicionado."}


def update_vendor(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    company = str(args.get("company", "")).strip()
    vendor = _find_vendor(db, company) if company else None
    if vendor is None:
        return {"ok": False, "error": f"Não encontrei nenhum fornecedor ativo chamado '{company}'."}
    if args.get("vendor_type") is not None:
        vendor.vendor_type = str(args["vendor_type"])
    if args.get("contact_name") is not None:
        vendor.contact_name = str(args["contact_name"])
    if args.get("phone") is not None:
        vendor.phone = str(args["phone"])
    if args.get("email") is not None:
        vendor.email = str(args["email"])
    if args.get("website") is not None:
        vendor.website = str(args["website"])
    if "agreed_price" in args:
        vendor.agreed_price = _parse_amount(args.get("agreed_price"))
    if "paid_amount" in args:
        vendor.paid_amount = _parse_amount(args.get("paid_amount"))
    if args.get("deposit_date"):
        parsed = _parse_date(args["deposit_date"])
        if parsed:
            vendor.deposit_date = parsed
    if args.get("final_payment_date"):
        parsed = _parse_date(args["final_payment_date"])
        if parsed:
            vendor.final_payment_date = parsed
    if args.get("notes") is not None:
        vendor.notes = str(args["notes"])
    vendor.updated_by_id = user.id
    vendor.updated_at = datetime.now(UTC)
    vendor_company = vendor.company
    record_activity(
        db, user.id, "alterou", f"assistente atualizou fornecedor: {vendor_company}", "vendors"
    )
    db.commit()
    return {"ok": True, "message": f"Fornecedor '{vendor_company}' atualizado."}


def remove_vendor(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    company = str(args.get("company", "")).strip()
    vendor = _find_vendor(db, company) if company else None
    if vendor is None:
        return {"ok": False, "error": f"Não encontrei nenhum fornecedor ativo chamado {company}."}
    vendor.is_archived = True
    vendor.updated_by_id = user.id
    record_activity(
        db, user.id, "arquivou", f"assistente removeu fornecedor: {vendor.company}", "vendors"
    )
    vendor_company = vendor.company
    db.commit()
    return {
        "ok": True,
        "message": f"Fornecedor {vendor_company} removido (recuperável em Todos os eliminados).",
    }


# --- Legal documents -----------------------------------------------------------


def add_legal_document(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        return {"ok": False, "error": "É preciso um título para o documento."}
    if _find_legal_document(db, title) is not None:
        return {"ok": False, "error": f"Já existe um documento legal chamado {title}."}
    status = _match_enum(args.get("status"), LEGAL_STATUSES) or "Pendente"
    document = LegalDocument(
        document_type=str(args.get("document_type", "") or "Documento"),
        title=title,
        status=status,
        due_date=_parse_date(args.get("due_date")),
        responsible=str(args.get("responsible", "") or ""),
        notes=str(args.get("notes", "") or ""),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(document)
    record_activity(
        db, user.id, "criou", f"assistente adicionou documento legal: {title}", "legal-process"
    )
    db.commit()
    return {"ok": True, "message": f"Documento '{title}' adicionado, estado {status}."}


def update_legal_document(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    document = _find_legal_document(db, title) if title else None
    if document is None:
        return {
            "ok": False,
            "error": f"Não encontrei nenhum documento legal ativo chamado '{title}'.",
        }
    if args.get("document_type") is not None:
        document.document_type = str(args["document_type"])
    matched_status = _match_enum(args.get("status"), LEGAL_STATUSES)
    if matched_status:
        document.status = matched_status
    if "due_date" in args:
        document.due_date = _parse_date(args.get("due_date"))
    if args.get("responsible") is not None:
        document.responsible = str(args["responsible"])
    if args.get("notes") is not None:
        document.notes = str(args["notes"])
    document.updated_by_id = user.id
    document.updated_at = datetime.now(UTC)
    document_title = document.title
    record_activity(
        db,
        user.id,
        "alterou",
        f"assistente atualizou documento legal: {document_title}",
        "legal-process",
    )
    db.commit()
    return {"ok": True, "message": f"Documento '{document_title}' atualizado."}


def remove_legal_document(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    document = _find_legal_document(db, title) if title else None
    if document is None:
        return {
            "ok": False,
            "error": f"Não encontrei nenhum documento legal ativo chamado '{title}'.",
        }
    document.is_archived = True
    document.updated_by_id = user.id
    document_title = document.title
    record_activity(
        db,
        user.id,
        "arquivou",
        f"assistente removeu documento legal: {document_title}",
        "legal-process",
    )
    db.commit()
    return {
        "ok": True,
        "message": f"Documento '{document_title}' removido (recuperável em Todos os eliminados).",
    }


# --- Budget categories -----------------------------------------------------------


def add_budget_category(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    if not name:
        return {"ok": False, "error": "É preciso um nome para a categoria."}
    if _find_budget_category(db, name) is not None:
        return {"ok": False, "error": f"Já existe uma categoria chamada {name}."}
    category = BudgetCategory(
        name=name,
        planned_limit=_parse_amount(args.get("planned_limit")),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(category)
    try:
        record_activity(
            db, user.id, "criou", f"assistente adicionou categoria de orçamento: {name}", "budget"
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"ok": False, "error": f"Já existe uma categoria chamada {name}."}
    return {"ok": True, "message": f"Categoria '{name}' criada."}


def update_budget_category(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    category = _find_budget_category(db, name) if name else None
    if category is None:
        return {"ok": False, "error": f"Não encontrei nenhuma categoria ativa chamada '{name}'."}
    new_name = args.get("new_name")
    if new_name:
        new_name = str(new_name).strip()
        if new_name and new_name.lower() != category.name.lower():
            if _find_budget_category(db, new_name) is not None:
                return {"ok": False, "error": f"Já existe uma categoria chamada {new_name}."}
            category.name = new_name
    if "planned_limit" in args:
        category.planned_limit = _parse_amount(args.get("planned_limit"))
    category.updated_by_id = user.id
    category.updated_at = datetime.now(UTC)
    category_name = category.name
    record_activity(
        db,
        user.id,
        "alterou",
        f"assistente atualizou categoria de orçamento: {category_name}",
        "budget",
    )
    db.commit()
    return {"ok": True, "message": f"Categoria '{category_name}' atualizada."}


def remove_budget_category(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    category = _find_budget_category(db, name) if name else None
    if category is None:
        return {"ok": False, "error": f"Não encontrei nenhuma categoria ativa chamada '{name}'."}
    category.is_archived = True
    category.updated_by_id = user.id
    category_name = category.name
    record_activity(
        db,
        user.id,
        "arquivou",
        f"assistente removeu categoria de orçamento: {category_name}",
        "budget",
    )
    db.commit()
    return {
        "ok": True,
        "message": f"Categoria '{category_name}' removida (recuperável em Todos os eliminados).",
    }


# --- Expenses ----------------------------------------------------------------------


def add_expense(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    description = str(args.get("description", "")).strip()
    category_name = str(args.get("category", "")).strip()
    if not description or not category_name:
        return {
            "ok": False,
            "error": "É preciso a descrição e a categoria de orçamento da despesa.",
        }
    category = _find_budget_category(db, category_name)
    if category is None:
        return {
            "ok": False,
            "error": (
                f"Não encontrei nenhuma categoria de orçamento ativa chamada '{category_name}'."
            ),
        }
    vendor = None
    vendor_name = args.get("vendor")
    if vendor_name:
        vendor = _find_vendor(db, str(vendor_name))
        if vendor is None:
            return {
                "ok": False,
                "error": f"Não encontrei nenhum fornecedor ativo chamado '{vendor_name}'.",
            }
    status = _match_enum(args.get("status"), EXPENSE_STATUSES) or "Pendente"
    expense = Expense(
        category_id=category.id,
        vendor_id=vendor.id if vendor else None,
        description=description,
        amount=_parse_amount(args.get("amount")),
        expense_date=_parse_date(args.get("expense_date")) or date.today(),
        status=status,
        notes=str(args.get("notes", "") or ""),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(expense)
    record_activity(
        db, user.id, "criou", f"assistente adicionou despesa: {description}", "expenses"
    )
    db.commit()
    return {
        "ok": True,
        "message": f"Despesa '{description}' adicionada em {category.name}, estado {status}.",
    }


def update_expense(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    description = str(args.get("description", "")).strip()
    matches = _find_expenses(db, description, args.get("category")) if description else []
    if not matches:
        return {"ok": False, "error": "Não encontrei nenhuma despesa ativa com essa descrição."}
    if len(matches) > 1:
        return {
            "ok": False,
            "error": "Há mais do que uma despesa com essa descrição; indiquem também a categoria.",
        }
    expense = matches[0]
    if args.get("category"):
        category = _find_budget_category(db, str(args["category"]))
        if category is None:
            return {
                "ok": False,
                "error": (
                    f"Não encontrei nenhuma categoria de orçamento ativa chamada "
                    f"'{args['category']}'."
                ),
            }
        expense.category_id = category.id
    if args.get("vendor"):
        vendor = _find_vendor(db, str(args["vendor"]))
        if vendor is None:
            return {
                "ok": False,
                "error": f"Não encontrei nenhum fornecedor ativo chamado '{args['vendor']}'.",
            }
        expense.vendor_id = vendor.id
    if "amount" in args:
        expense.amount = _parse_amount(args.get("amount"))
    if args.get("expense_date"):
        parsed = _parse_date(args["expense_date"])
        if parsed:
            expense.expense_date = parsed
    matched_status = _match_enum(args.get("status"), EXPENSE_STATUSES)
    if matched_status:
        expense.status = matched_status
    if args.get("notes") is not None:
        expense.notes = str(args["notes"])
    expense.updated_by_id = user.id
    expense.updated_at = datetime.now(UTC)
    expense_description = expense.description
    record_activity(
        db, user.id, "alterou", f"assistente atualizou despesa: {expense_description}", "expenses"
    )
    db.commit()
    return {"ok": True, "message": f"Despesa '{expense_description}' atualizada."}


def remove_expense(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    description = str(args.get("description", "")).strip()
    matches = _find_expenses(db, description, args.get("category")) if description else []
    if not matches:
        return {"ok": False, "error": "Não encontrei nenhuma despesa ativa com essa descrição."}
    if len(matches) > 1:
        return {
            "ok": False,
            "error": "Há mais do que uma despesa com essa descrição; indiquem também a categoria.",
        }
    expense = matches[0]
    expense.is_archived = True
    expense.updated_by_id = user.id
    expense_description = expense.description
    record_activity(
        db, user.id, "arquivou", f"assistente removeu despesa: {expense_description}", "expenses"
    )
    db.commit()
    return {
        "ok": True,
        "message": (
            f"Despesa '{expense_description}' removida (recuperável em Todos os eliminados)."
        ),
    }


# --- Payments ------------------------------------------------------------------------


def add_payment(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    category_name = str(args.get("category", "")).strip()
    if not category_name:
        return {"ok": False, "error": "É preciso indicar a categoria de orçamento do pagamento."}
    category = _find_budget_category(db, category_name)
    if category is None:
        return {
            "ok": False,
            "error": (
                f"Não encontrei nenhuma categoria de orçamento ativa chamada '{category_name}'."
            ),
        }
    vendor = None
    if args.get("vendor"):
        vendor = _find_vendor(db, str(args["vendor"]))
        if vendor is None:
            return {
                "ok": False,
                "error": f"Não encontrei nenhum fornecedor ativo chamado '{args['vendor']}'.",
            }
    status = _match_enum(args.get("status"), PAYMENT_STATUSES) or "Pago"
    payment = Payment(
        category_id=category.id,
        vendor_id=vendor.id if vendor else None,
        amount=_parse_amount(args.get("amount")),
        payment_date=_parse_date(args.get("payment_date")) or date.today(),
        status=status,
        reference=str(args.get("reference", "") or ""),
        notes=str(args.get("notes", "") or ""),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(payment)
    record_activity(
        db, user.id, "criou", f"assistente adicionou pagamento em {category.name}", "payments"
    )
    db.commit()
    return {
        "ok": True,
        "message": f"Pagamento de {payment.amount} em {category.name} registado, estado {status}.",
    }


def update_payment(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    reference = str(args.get("reference", "")).strip()
    matches = _find_payments(db, reference)
    if not matches:
        return {
            "ok": False,
            "error": (
                "Só consigo atualizar um pagamento pela referência exata; indiquem a referência."
            ),
        }
    if len(matches) > 1:
        return {
            "ok": False,
            "error": "Há mais do que um pagamento com essa referência; sejam mais específicos.",
        }
    payment = matches[0]
    if args.get("category"):
        category = _find_budget_category(db, str(args["category"]))
        if category is None:
            return {
                "ok": False,
                "error": (
                    f"Não encontrei nenhuma categoria de orçamento ativa chamada "
                    f"'{args['category']}'."
                ),
            }
        payment.category_id = category.id
    if args.get("vendor"):
        vendor = _find_vendor(db, str(args["vendor"]))
        if vendor is None:
            return {
                "ok": False,
                "error": f"Não encontrei nenhum fornecedor ativo chamado '{args['vendor']}'.",
            }
        payment.vendor_id = vendor.id
    if "amount" in args:
        payment.amount = _parse_amount(args.get("amount"))
    if args.get("payment_date"):
        parsed = _parse_date(args["payment_date"])
        if parsed:
            payment.payment_date = parsed
    matched_status = _match_enum(args.get("status"), PAYMENT_STATUSES)
    if matched_status:
        payment.status = matched_status
    if args.get("notes") is not None:
        payment.notes = str(args["notes"])
    payment.updated_by_id = user.id
    payment.updated_at = datetime.now(UTC)
    payment_reference = payment.reference
    record_activity(
        db, user.id, "alterou", f"assistente atualizou pagamento: {payment_reference}", "payments"
    )
    db.commit()
    return {"ok": True, "message": f"Pagamento '{payment_reference}' atualizado."}


def remove_payment(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    reference = str(args.get("reference", "")).strip()
    matches = _find_payments(db, reference)
    if not matches:
        return {
            "ok": False,
            "error": (
                "Só consigo remover um pagamento pela referência exata; indiquem a referência."
            ),
        }
    if len(matches) > 1:
        return {
            "ok": False,
            "error": "Há mais do que um pagamento com essa referência; sejam mais específicos.",
        }
    payment = matches[0]
    payment.is_archived = True
    payment.updated_by_id = user.id
    payment_reference = payment.reference
    record_activity(
        db, user.id, "arquivou", f"assistente removeu pagamento: {payment_reference}", "payments"
    )
    db.commit()
    return {
        "ok": True,
        "message": (
            f"Pagamento '{payment_reference}' removido (recuperável em Todos os eliminados)."
        ),
    }


# --- Communication notes --------------------------------------------------------------


def add_communication_note(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        return {"ok": False, "error": "É preciso um título para a nota."}
    category = _match_enum(args.get("category"), COMMUNICATION_CATEGORIES) or "Nota"
    priority = _match_enum(args.get("priority"), COMMUNICATION_PRIORITIES) or "Média"
    record = WorkspaceRecord(
        module="communication",
        title=title,
        description=str(args.get("description", "") or ""),
        category=category,
        status=category,
        responsible=str(args.get("responsible", "") or ""),
        priority=priority,
        event_date=_parse_event_datetime(args.get("event_date")),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(record)
    record_activity(
        db,
        user.id,
        "criou",
        f"assistente adicionou {category.lower()} na comunicação: {title}",
        "communication",
    )
    db.commit()
    return {"ok": True, "message": f"{category} '{title}' adicionada à comunicação."}


def update_communication_note(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    record = _find_communication(db, title) if title else None
    if record is None:
        return {"ok": False, "error": f"Não encontrei nenhuma nota ativa chamada '{title}'."}
    if args.get("description") is not None:
        record.description = str(args["description"])
    matched_category = _match_enum(args.get("category"), COMMUNICATION_CATEGORIES)
    if matched_category:
        record.category = matched_category
        record.status = matched_category
    if args.get("responsible") is not None:
        record.responsible = str(args["responsible"])
    matched_priority = _match_enum(args.get("priority"), COMMUNICATION_PRIORITIES)
    if matched_priority:
        record.priority = matched_priority
    if "event_date" in args:
        record.event_date = _parse_event_datetime(args.get("event_date"))
    record.updated_by_id = user.id
    record.updated_at = datetime.now(UTC)
    record_title = record.title
    record_activity(
        db,
        user.id,
        "alterou",
        f"assistente atualizou nota de comunicação: {record_title}",
        "communication",
    )
    db.commit()
    return {"ok": True, "message": f"Nota '{record_title}' atualizada."}


def remove_communication_note(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    record = _find_communication(db, title) if title else None
    if record is None:
        return {"ok": False, "error": f"Não encontrei nenhuma nota ativa chamada '{title}'."}
    record.is_archived = True
    record.updated_by_id = user.id
    record_title = record.title
    record_activity(
        db,
        user.id,
        "arquivou",
        f"assistente removeu nota de comunicação: {record_title}",
        "communication",
    )
    db.commit()
    return {
        "ok": True,
        "message": f"Nota '{record_title}' removida (recuperável em Todos os eliminados).",
    }


# --- Moodboard -------------------------------------------------------------------------


def _ensure_default_moodboard_collection(db: Session, user_id: int) -> MoodboardCollection:
    collection = db.scalar(
        select(MoodboardCollection)
        .where(MoodboardCollection.is_archived.is_(False))
        .order_by(MoodboardCollection.id)
    )
    if collection is not None:
        return collection
    board = MoodboardBoard(name="O nosso casamento", created_by_id=user_id, updated_by_id=user_id)
    db.add(board)
    db.flush()
    collection = MoodboardCollection(
        board_id=board.id, name="Inspirações", created_by_id=user_id, updated_by_id=user_id
    )
    db.add(collection)
    db.flush()
    return collection


def _default_moodboard_placement(
    index: int, owner_id: int, item_id: int
) -> MoodboardInspirationPlacement:
    columns = 4
    rotations = (-2.4, 1.8, -1.1, 2.6, -1.8, 1.2)
    column = index % columns
    row = (index // columns) % 4
    return MoodboardInspirationPlacement(
        item_id=item_id,
        x_percent=4.0 + (column * 24.0),
        y_percent=4.0 + (row * 23.0),
        rotation_degrees=rotations[index % len(rotations)],
        layer=index + 1,
        created_by_id=owner_id,
        updated_by_id=owner_id,
    )


def add_moodboard_item(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    image_url = str(args.get("image_url", "")).strip()
    if not title or not image_url:
        return {"ok": False, "error": "É preciso um título e o endereço (URL) da imagem."}
    if not _valid_http_url(image_url):
        return {
            "ok": False,
            "error": "O endereço da imagem tem de ser um link http:// ou https:// válido.",
        }
    source_url = str(args.get("source_url", "") or "")
    if source_url and not _valid_http_url(source_url):
        return {
            "ok": False,
            "error": "O endereço de origem tem de ser um link http:// ou https:// válido.",
        }
    collection = _ensure_default_moodboard_collection(db, user.id)
    item = MoodboardItem(
        collection_id=collection.id,
        title=title,
        image_url=image_url,
        source_url=source_url,
        tags=str(args.get("tags", "") or ""),
        notes=str(args.get("notes", "") or ""),
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(item)
    db.flush()
    placement_count = db.scalar(select(func.count(MoodboardInspirationPlacement.id))) or 0
    db.add(_default_moodboard_placement(placement_count, user.id, item.id))
    record_activity(db, user.id, "criou", f"assistente adicionou inspiração: {title}", "moodboard")
    db.commit()
    return {"ok": True, "message": f"Inspiração '{title}' adicionada ao moodboard."}


def remove_moodboard_item(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    item = _find_moodboard_item(db, title) if title else None
    if item is None:
        return {"ok": False, "error": f"Não encontrei nenhuma inspiração ativa chamada '{title}'."}
    item.is_archived = True
    item.updated_by_id = user.id
    item_title = item.title
    record_activity(
        db, user.id, "arquivou", f"assistente removeu inspiração: {item_title}", "moodboard"
    )
    db.commit()
    return {
        "ok": True,
        "message": f"Inspiração '{item_title}' removida (recuperável em Todos os eliminados).",
    }


# --- Permanent deletion (irreversible from the UI) --------------------------------------

PERMANENT_DELETE_MODULES: dict[str, tuple[type[Any], Any, str]] = {
    "guest": (Guest, Guest.name, "guests"),
    "task": (Task, Task.title, "checklist"),
    "vendor": (Vendor, Vendor.company, "vendors"),
    "legal_document": (LegalDocument, LegalDocument.title, "legal-process"),
    "budget_category": (BudgetCategory, BudgetCategory.name, "budget"),
    "expense": (Expense, Expense.description, "expenses"),
    "payment": (Payment, Payment.reference, "payments"),
}


def permanently_delete_record(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    if str(args.get("confirm", "")).strip() != "APAGAR":
        return {
            "ok": False,
            "error": (
                "Para apagar em definitivo é preciso o argumento confirm com o texto exato "
                "'APAGAR'. Esta ação não pode ser desfeita pela interface — só a usem depois "
                "de o casal confirmar claramente que é isso mesmo que querem."
            ),
        }
    module = str(args.get("module", ""))
    mapping = PERMANENT_DELETE_MODULES.get(module)
    if mapping is None:
        return {
            "ok": False,
            "error": f"Módulo desconhecido; use um de: {', '.join(PERMANENT_DELETE_MODULES)}.",
        }
    model, column, module_slug = mapping
    identifier = str(args.get("identifier", "")).strip()
    if not identifier:
        return {"ok": False, "error": "É preciso o nome/título exato do registo já arquivado."}
    matches = db.scalars(
        select(model).where(
            model.is_archived.is_(True), not_tombstoned(model), column.ilike(identifier)
        )
    ).all()
    if not matches:
        return {
            "ok": False,
            "error": (
                "Não encontrei nenhum registo arquivado com esse nome nesse módulo. Só é "
                "possível apagar em definitivo algo que já esteja removido/arquivado."
            ),
        }
    if len(matches) > 1:
        return {
            "ok": False,
            "error": (
                "Há mais do que um registo arquivado com esse nome; "
                "façam isso em 'Todos os eliminados'."
            ),
        }
    record = matches[0]
    record.updated_by_id = user.id
    create_tombstone(db, record, module=module_slug, user_id=user.id)
    record_activity(
        db,
        user.id,
        "eliminou definitivamente",
        f"assistente apagou em definitivo: {identifier} ({module_slug})",
        module_slug,
    )
    db.commit()
    return {
        "ok": True,
        "message": f"'{identifier}' foi apagado em definitivo. Não pode ser desfeito.",
    }


# --- Web fetch -------------------------------------------------------------------------


def _is_blocked_host(hostname: str) -> bool:
    """Refuse to fetch anything that looks like an internal/private address."""

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname in {"localhost"} or hostname.endswith(".local")
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def fetch_webpage(_db: Session, _user: User, args: dict[str, Any]) -> dict[str, Any]:
    url = str(args.get("url", "")).strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {"ok": False, "error": "Só consigo abrir endereços http:// ou https:// válidos."}
    if _is_blocked_host(parsed.hostname):
        return {"ok": False, "error": "Esse endereço não pode ser aberto."}
    try:
        response = httpx.get(
            url,
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "LV-Wedding-Planner-Assistant/1.0"},
        )
    except httpx.HTTPError:
        return {"ok": False, "error": "Não foi possível abrir esse endereço."}
    if response.status_code >= 400:
        return {"ok": False, "error": f"O endereço respondeu com o erro {response.status_code}."}
    text = response.text
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return {"ok": False, "error": "Essa página não devolveu texto legível."}
    return {"ok": True, "content": text[:MAX_FETCHED_CHARS]}


# --- Generic dispatch (keeps the tool schema small enough for the free tier) -----------
#
# Groq's free tier caps requests at ~12,000 tokens/minute, and every tool
# definition sent to the model counts against that budget on *every* round.
# Listing a separate add_/update_/remove_ tool per module (28 tools) cost
# ~3,700+ tokens before a single word of conversation, which left almost no
# room for the actual chat and made the assistant fail on ordinary use. These
# three generic tools replace that whole list with the same capabilities,
# dispatched internally by ``module`` — cutting the schema to a few hundred
# tokens.

IDENTIFIER_FIELD: dict[str, str] = {
    "guest": "name",
    "task": "title",
    "vendor": "company",
    "legal_document": "title",
    "budget_category": "name",
    "expense": "description",
    "payment": "reference",
    "communication_note": "title",
    "moodboard_item": "title",
}

CREATE_EXECUTORS: dict[str, Callable[[Session, User, dict[str, Any]], dict[str, Any]]] = {
    "guest": add_guest,
    "task": add_task,
    "vendor": add_vendor,
    "legal_document": add_legal_document,
    "budget_category": add_budget_category,
    "expense": add_expense,
    "payment": add_payment,
    "communication_note": add_communication_note,
    "moodboard_item": add_moodboard_item,
}

UPDATE_EXECUTORS: dict[str, Callable[[Session, User, dict[str, Any]], dict[str, Any]]] = {
    "guest": update_guest,
    "task": update_task,
    "vendor": update_vendor,
    "legal_document": update_legal_document,
    "budget_category": update_budget_category,
    "expense": update_expense,
    "payment": update_payment,
    "communication_note": update_communication_note,
}

REMOVE_EXECUTORS: dict[str, Callable[[Session, User, dict[str, Any]], dict[str, Any]]] = {
    "guest": remove_guest,
    "task": remove_task,
    "vendor": remove_vendor,
    "legal_document": remove_legal_document,
    "budget_category": remove_budget_category,
    "expense": remove_expense,
    "payment": remove_payment,
    "communication_note": remove_communication_note,
    "moodboard_item": remove_moodboard_item,
}

MODULE_FIELD_HINTS: dict[str, str] = {
    "guest": "side, rsvp_status, age_group, table_name, dietary_requirements, special_needs",
    "task": "category, priority, assignee, due_date (AAAA-MM-DD), status, description, comments",
    "vendor": (
        "vendor_type, contact_name, phone, email, website, agreed_price, paid_amount, "
        "deposit_date, final_payment_date, notes"
    ),
    "legal_document": "document_type, status, due_date (AAAA-MM-DD), responsible, notes",
    "budget_category": "planned_limit, new_name (só em update, para renomear)",
    "expense": "category, vendor, amount, expense_date (AAAA-MM-DD), status, notes",
    "payment": "category, vendor, amount, payment_date (AAAA-MM-DD), status, reference, notes",
    "communication_note": "category, description, responsible, priority, event_date (AAAA-MM-DD)",
    "moodboard_item": "image_url (obrigatório ao criar), source_url, tags, notes",
}


def create_record(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    module = str(args.get("module", ""))
    executor = CREATE_EXECUTORS.get(module)
    if executor is None:
        return {
            "ok": False,
            "error": f"Módulo desconhecido; use um de: {', '.join(CREATE_EXECUTORS)}.",
        }
    fields = args.get("fields")
    return executor(db, user, dict(fields) if isinstance(fields, dict) else {})


def update_record(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    module = str(args.get("module", ""))
    executor = UPDATE_EXECUTORS.get(module)
    if executor is None:
        return {
            "ok": False,
            "error": f"Módulo desconhecido; use um de: {', '.join(UPDATE_EXECUTORS)}.",
        }
    identifier = str(args.get("identifier", "")).strip()
    if not identifier:
        return {"ok": False, "error": "É preciso o nome/título exato do registo a atualizar."}
    fields = args.get("fields")
    merged = dict(fields) if isinstance(fields, dict) else {}
    merged[IDENTIFIER_FIELD[module]] = identifier
    return executor(db, user, merged)


def remove_record(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    module = str(args.get("module", ""))
    executor = REMOVE_EXECUTORS.get(module)
    if executor is None:
        return {
            "ok": False,
            "error": f"Módulo desconhecido; use um de: {', '.join(REMOVE_EXECUTORS)}.",
        }
    identifier = str(args.get("identifier", "")).strip()
    if not identifier:
        return {"ok": False, "error": "É preciso o nome/título exato do registo a remover."}
    return executor(db, user, {IDENTIFIER_FIELD[module]: identifier})


TOOL_EXECUTORS: dict[str, Callable[[Session, User, dict[str, Any]], dict[str, Any]]] = {
    "create_record": create_record,
    "update_record": update_record,
    "remove_record": remove_record,
    "permanently_delete_record": permanently_delete_record,
    "fetch_webpage": fetch_webpage,
}


_MODULE_FIELD_HINT_TEXT = " · ".join(
    f"{module}: {hint}" for module, hint in MODULE_FIELD_HINTS.items()
)

ASSISTANT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_record",
            "description": (
                "Cria um novo registo num módulo do casamento. 'fields' leva os dados desse "
                "registo, incluindo o nome/título. Campos típicos por módulo — "
                f"{_MODULE_FIELD_HINT_TEXT}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {"type": "string", "enum": list(CREATE_EXECUTORS)},
                    "fields": {
                        "type": "object",
                        "description": (
                            'Dados do novo registo (ex.: {"name": "Bruna", "side": "Noiva"}).'
                        ),
                    },
                },
                "required": ["module", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_record",
            "description": (
                "Atualiza um registo existente, encontrado pelo nome/título exato em "
                "'identifier'. 'fields' leva só os dados a mudar. Campos típicos por módulo — "
                f"{_MODULE_FIELD_HINT_TEXT}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {"type": "string", "enum": list(UPDATE_EXECUTORS)},
                    "identifier": {
                        "type": "string",
                        "description": "Nome/título exato do registo.",
                    },
                    "fields": {"type": "object", "description": "Só os campos a mudar."},
                },
                "required": ["module", "identifier", "fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_record",
            "description": (
                "Remove (arquiva) um registo existente, encontrado pelo nome/título exato. "
                "Fica recuperável em 'Todos os eliminados', nunca apaga em definitivo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {"type": "string", "enum": list(REMOVE_EXECUTORS)},
                    "identifier": {
                        "type": "string",
                        "description": "Nome/título exato do registo.",
                    },
                },
                "required": ["module", "identifier"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "permanently_delete_record",
            "description": (
                "APAGA UM REGISTO PARA SEMPRE, sem recuperação possível pela interface. Só "
                "funciona num registo já removido/arquivado. Só usem depois de o casal "
                "confirmar de forma clara e inequívoca, na própria conversa, que querem "
                "apagar em definitivo (não apenas remover) — se houver qualquer dúvida, "
                "usem antes remove_record e perguntem."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {"type": "string", "enum": list(PERMANENT_DELETE_MODULES)},
                    "identifier": {
                        "type": "string",
                        "description": "Nome/título exato do registo já arquivado.",
                    },
                    "confirm": {
                        "type": "string",
                        "description": "Tem de ser exatamente a palavra APAGAR.",
                    },
                },
                "required": ["module", "identifier", "confirm"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": (
                "Abre uma página da internet (ex.: o site de um fornecedor) e devolve o "
                "texto, para poderem extrair informação e usá-la noutras ferramentas."
            ),
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]
