"""Database-backed API used by the compact communication drawer."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.core import User, WorkspaceRecord
from app.services.activity import record_activity
from app.services.auth_session import authenticated_user
from app.services.csrf import valid_csrf_token
from app.services.record_deletion import not_tombstoned

router = APIRouter(prefix="/api/communication-panel", tags=["communication"])

COMMUNICATION_CATEGORIES = (
    "Nota",
    "Ideia",
    "Decisão",
    "Lembrete",
    "Tarefa rápida",
)
PRIORITIES = ("Baixa", "Média", "Alta")


def record_payload(
    record: WorkspaceRecord,
    updated_by_name: str | None = None,
) -> dict[str, object]:
    """Return the small, non-sensitive representation needed by the drawer."""

    category = record.category if record.category in COMMUNICATION_CATEGORIES else record.status
    if category not in COMMUNICATION_CATEGORIES:
        category = "Nota"
    return {
        "id": record.id,
        "title": record.title,
        "description": record.description,
        "category": category,
        "responsible": record.responsible,
        "priority": record.priority,
        "event_date": record.event_date.isoformat() if record.event_date else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "updated_by": updated_by_name or "",
        "url": f"/communication/{record.id}/edit",
    }


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "message": message},
        status_code=status_code,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("")
def recent_communication(
    request: Request,
    q: str = Query("", max_length=100),
) -> JSONResponse:
    """Load the latest persisted communication records, optionally filtered."""

    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return error_response("A sessão terminou. Iniciem sessão novamente.", 401)

        statement = (
            select(WorkspaceRecord, User.name.label("updated_by_name"))
            .outerjoin(User, WorkspaceRecord.updated_by_id == User.id)
            .where(
                WorkspaceRecord.module == "communication",
                WorkspaceRecord.is_archived.is_(False),
                not_tombstoned(WorkspaceRecord),
            )
        )
        search = q.strip()
        if search:
            pattern = f"%{search}%"
            statement = statement.where(
                or_(
                    WorkspaceRecord.title.ilike(pattern),
                    WorkspaceRecord.description.ilike(pattern),
                    WorkspaceRecord.category.ilike(pattern),
                    WorkspaceRecord.status.ilike(pattern),
                    WorkspaceRecord.responsible.ilike(pattern),
                )
            )
        rows = db.execute(statement.order_by(WorkspaceRecord.updated_at.desc()).limit(20)).all()
        records = [record_payload(record, updated_by_name) for record, updated_by_name in rows]

    return JSONResponse(
        {"ok": True, "records": records, "query": search},
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("", status_code=201)
def create_quick_communication(
    request: Request,
    title: str = Form(..., min_length=1, max_length=200),
    category: str = Form("Nota"),
    description: str = Form("", max_length=5000),
    responsible: str = Form("", max_length=100),
    priority: str = Form("Média"),
    event_date: str = Form("", max_length=16),
    csrf_token: str = Form(""),
) -> JSONResponse:
    """Persist a compact note/idea/decision/reminder/task and its audit event."""

    if not valid_csrf_token(request, csrf_token):
        return error_response("A sessão de segurança expirou. Recarreguem a página.", 403)

    clean_title = title.strip()
    if not clean_title:
        return error_response("Escrevam um título.", 422)
    if category not in COMMUNICATION_CATEGORIES:
        return error_response("Escolham uma categoria válida.", 422)
    if priority not in PRIORITIES:
        return error_response("Escolham uma prioridade válida.", 422)

    parsed_event_date = None
    if event_date:
        try:
            parsed_event_date = datetime.fromisoformat(event_date)
        except ValueError:
            return error_response("A data indicada não é válida.", 422)

    with SessionLocal() as db:
        user = authenticated_user(db, request)
        if user is None:
            return error_response("A sessão terminou. Iniciem sessão novamente.", 401)

        record = WorkspaceRecord(
            module="communication",
            title=clean_title,
            description=description.strip(),
            category=category,
            # The full Communication page historically stores its type in
            # ``status``. Mirroring it preserves two-way compatibility.
            status=category,
            responsible=responsible.strip(),
            priority=priority,
            event_date=parsed_event_date,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(record)
        try:
            db.flush()
            record_activity(
                db,
                user.id,
                "criou",
                f"adicionou {category.lower()} na comunicação: {clean_title}",
                "communication",
            )
            db.commit()
            db.refresh(record)
        except (IntegrityError, ValueError):
            db.rollback()
            return error_response("Não foi possível guardar. Confirmem os dados.", 422)

        payload = record_payload(record, user.name)

    return JSONResponse(
        {"ok": True, "message": "Guardado na base de dados.", "record": payload},
        status_code=201,
        headers={"Cache-Control": "private, no-store"},
    )
