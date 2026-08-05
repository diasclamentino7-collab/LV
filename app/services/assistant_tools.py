"""Tools the AI assistant can call to act on the couple's planning data.

Every tool here is safely reversible: it only creates new records or
archives existing ones. Archived records stay recoverable in ``/deleted``,
exactly like anything archived by hand from the app's own screens.
Permanently deleting a record requires a human to type "APAGAR" in the
app — that step is deliberately not exposed to the assistant.

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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import User
from app.models.planning import Guest, Task, Vendor
from app.services.activity import record_activity
from app.services.guests import AGE_GROUPS, RSVP_STATUSES, SIDES, active_guest_condition
from app.services.record_deletion import not_tombstoned

FETCH_TIMEOUT_SECONDS = 15.0
MAX_FETCHED_CHARS = 6000
TASK_PRIORITIES = ("Baixa", "Média", "Alta")
TASK_STATUSES = ("Pendente", "Em curso", "Concluído")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_amount(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value or 0).replace(",", "."))
        return parsed if parsed.is_finite() and parsed >= 0 else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _find_guest(db: Session, name: str) -> Guest | None:
    return db.scalar(
        select(Guest).where(*active_guest_condition(), Guest.name.ilike(name.strip()))
    )


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


def add_guest(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name", "")).strip()
    if not name:
        return {"ok": False, "error": "É preciso um nome para adicionar um convidado."}
    if _find_guest(db, name) is not None:
        return {"ok": False, "error": f"Já existe um convidado chamado {name}."}
    side = args.get("side") or ""
    if side and side not in SIDES:
        side = ""
    rsvp_status = args.get("rsvp_status") or "Pendente"
    if rsvp_status not in RSVP_STATUSES:
        rsvp_status = "Pendente"
    age_group = args.get("age_group") or "Adulto"
    if age_group not in AGE_GROUPS:
        age_group = "Adulto"
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
    if args.get("rsvp_status") in RSVP_STATUSES:
        guest.rsvp_status = args["rsvp_status"]
    if args.get("side") in SIDES:
        guest.side = args["side"]
    if args.get("age_group") in AGE_GROUPS:
        guest.age_group = args["age_group"]
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


def add_task(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        return {"ok": False, "error": "É preciso um título para criar uma tarefa."}
    priority = args.get("priority") or "Média"
    if priority not in TASK_PRIORITIES:
        priority = "Média"
    status = args.get("status") or "Pendente"
    if status not in TASK_STATUSES:
        status = "Pendente"
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


def update_task_status(db: Session, user: User, args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    task = _find_task(db, title) if title else None
    if task is None:
        return {"ok": False, "error": f"Não encontrei nenhuma tarefa ativa chamada '{title}'."}
    status = args.get("status")
    if status not in TASK_STATUSES:
        return {"ok": False, "error": f"Estado inválido; use um de: {', '.join(TASK_STATUSES)}."}
    task.status = status
    task.updated_by_id = user.id
    task.updated_at = datetime.now(UTC)
    task_title = task.title
    record_activity(
        db, user.id, "alterou", f"assistente atualizou tarefa: {task_title}", "checklist"
    )
    db.commit()
    return {"ok": True, "message": f"Tarefa '{task_title}' passou a '{status}'."}


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


TOOL_EXECUTORS: dict[str, Callable[[Session, User, dict[str, Any]], dict[str, Any]]] = {
    "add_guest": add_guest,
    "update_guest": update_guest,
    "remove_guest": remove_guest,
    "add_task": add_task,
    "update_task_status": update_task_status,
    "remove_task": remove_task,
    "add_vendor": add_vendor,
    "remove_vendor": remove_vendor,
    "fetch_webpage": fetch_webpage,
}


ASSISTANT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "add_guest",
            "description": "Adiciona um novo convidado à lista de convidados do casamento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome completo do convidado."},
                    "side": {"type": "string", "enum": list(SIDES)},
                    "rsvp_status": {"type": "string", "enum": list(RSVP_STATUSES)},
                    "age_group": {"type": "string", "enum": list(AGE_GROUPS)},
                    "table_name": {"type": "string", "description": "Mesa atribuída, se souberem."},
                    "dietary_requirements": {"type": "string"},
                    "special_needs": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_guest",
            "description": (
                "Atualiza dados de um convidado já existente (estado de resposta, mesa, "
                "restrições alimentares, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nome exato do convidado a atualizar.",
                    },
                    "side": {"type": "string", "enum": list(SIDES)},
                    "rsvp_status": {"type": "string", "enum": list(RSVP_STATUSES)},
                    "age_group": {"type": "string", "enum": list(AGE_GROUPS)},
                    "table_name": {"type": "string"},
                    "dietary_requirements": {"type": "string"},
                    "special_needs": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_guest",
            "description": (
                "Remove um convidado da lista ativa (ex.: já não vai comparecer). "
                "Fica recuperável em 'Todos os eliminados', não é apagado de vez."
            ),
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Cria uma nova tarefa na checklist de planeamento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "priority": {"type": "string", "enum": list(TASK_PRIORITIES)},
                    "assignee": {"type": "string"},
                    "due_date": {"type": "string", "description": "Formato AAAA-MM-DD."},
                    "status": {"type": "string", "enum": list(TASK_STATUSES)},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_status",
            "description": "Muda o estado de uma tarefa existente (ex.: marcar como concluída).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Título exato da tarefa."},
                    "status": {"type": "string", "enum": list(TASK_STATUSES)},
                },
                "required": ["title", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_task",
            "description": (
                "Remove uma tarefa da checklist ativa (recuperável em 'Todos os eliminados')."
            ),
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_vendor",
            "description": "Adiciona um novo fornecedor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "vendor_type": {
                        "type": "string",
                        "description": "Tipo de fornecedor, ex.: Fotografia, Catering, Flores.",
                    },
                    "contact_name": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                    "website": {"type": "string"},
                    "agreed_price": {"type": "number"},
                    "notes": {"type": "string"},
                },
                "required": ["company", "vendor_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_vendor",
            "description": "Remove um fornecedor (recuperável em 'Todos os eliminados').",
            "parameters": {
                "type": "object",
                "properties": {"company": {"type": "string"}},
                "required": ["company"],
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
