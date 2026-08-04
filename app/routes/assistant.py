"""Database-backed API for the multi-provider AI assistant drawer."""

from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models.assistant import AssistantMessage
from app.repositories.project_settings import get_project_settings
from app.services.assistant_context import build_context_snapshot
from app.services.assistant_providers import (
    PROVIDER_LABELS,
    PROVIDERS,
    AssistantError,
    send_chat_message,
)
from app.services.auth_session import authenticated_user
from app.services.csrf import valid_csrf_token

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

MAX_MESSAGE_LENGTH = 2000
HISTORY_LIMIT = 20
DISPLAY_LIMIT = 50

SYSTEM_PROMPT_TEMPLATE = (
    "És um assistente de planeamento de casamento integrado na aplicação "
    '"LV – Wedding Planner". Respondem sempre em português de Portugal, de '
    "forma simpática, concisa e prática. Tens acesso apenas de leitura aos "
    "dados atuais da aplicação, listados abaixo; nunca finjas alterar dados "
    "— se vos pedirem para mudar algo, digam para o fazerem diretamente na "
    "aplicação. Se não tiverem a certeza de algo, digam isso claramente em "
    "vez de inventar.\n\n{context}"
)


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "message": message},
        status_code=status_code,
        headers={"Cache-Control": "private, no-store"},
    )


def message_payload(message: AssistantMessage) -> dict[str, object]:
    return {
        "id": message.id,
        "provider": message.provider,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def provider_credentials(settings: Settings, provider: str) -> tuple[str, str]:
    if provider == "openai":
        return settings.openai_api_key, settings.openai_model
    if provider == "anthropic":
        return settings.anthropic_api_key, settings.anthropic_model
    return settings.gemini_api_key, settings.gemini_model


@router.get("/messages")
def recent_messages(
    request: Request,
    provider: str = Query("openai"),
) -> JSONResponse:
    if provider not in PROVIDERS:
        return error_response("Assistente desconhecido.", 404)
    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return error_response("A sessão terminou. Iniciem sessão novamente.", 401)
        rows = db.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.provider == provider)
            .order_by(AssistantMessage.id.desc())
            .limit(DISPLAY_LIMIT)
        ).all()
    messages = [message_payload(row) for row in reversed(rows)]
    return JSONResponse(
        {"ok": True, "provider": provider, "messages": messages},
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/messages", status_code=201)
def send_message(
    request: Request,
    provider: str = Form(...),
    content: str = Form(..., min_length=1, max_length=MAX_MESSAGE_LENGTH),
    csrf_token: str = Form(""),
) -> JSONResponse:
    if provider not in PROVIDERS:
        return error_response("Assistente desconhecido.", 404)
    if not valid_csrf_token(request, csrf_token):
        return error_response("A sessão de segurança expirou. Recarreguem a página.", 403)

    clean_content = content.strip()
    if not clean_content:
        return error_response("Escrevam uma mensagem.", 422)

    settings = get_settings()
    api_key, model = provider_credentials(settings, provider)
    if not api_key:
        label = PROVIDER_LABELS[provider]
        return error_response(
            f"O {label} ainda não está configurado. Peçam a quem administra a aplicação "
            "para definir a chave da API.",
            503,
        )

    with SessionLocal() as db:
        user = authenticated_user(db, request)
        if user is None:
            return error_response("A sessão terminou. Iniciem sessão novamente.", 401)

        project_settings = get_project_settings(db)
        context = (
            build_context_snapshot(db, project_settings) if project_settings is not None else ""
        )
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context)

        history_rows = db.scalars(
            select(AssistantMessage)
            .where(AssistantMessage.provider == provider)
            .order_by(AssistantMessage.id.desc())
            .limit(HISTORY_LIMIT)
        ).all()
        history = [{"role": row.role, "content": row.content} for row in reversed(history_rows)]

        user_message = AssistantMessage(
            provider=provider,
            role="user",
            content=clean_content,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(user_message)
        db.flush()

        try:
            reply = send_chat_message(
                provider,
                api_key,
                model,
                system_prompt,
                [*history, {"role": "user", "content": clean_content}],
            )
        except AssistantError as error:
            db.rollback()
            return error_response(str(error), 502)

        assistant_message = AssistantMessage(
            provider=provider,
            role="assistant",
            content=reply,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(user_message)
        db.refresh(assistant_message)

        payload = {
            "ok": True,
            "user_message": message_payload(user_message),
            "assistant_message": message_payload(assistant_message),
        }
    return JSONResponse(payload, status_code=201, headers={"Cache-Control": "private, no-store"})
