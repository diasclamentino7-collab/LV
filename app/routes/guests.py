"""Fast, database-backed guest workspace and collaborative JSON API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.templating import templates
from app.db.session import SessionLocal
from app.models.core import User
from app.models.planning import Guest
from app.routes.pages import MODULES, module_query, record_label, require_login
from app.schemas.guests import GuestBulkUpdate, GuestCreate, GuestUpdate
from app.services.activity import record_activity
from app.services.auth_session import authenticated_user
from app.services.csrf import valid_csrf_token
from app.services.guests import (
    AGE_GROUPS,
    RSVP_STATUSES,
    SIDES,
    SORT_COLUMNS,
    active_guest,
    active_guest_condition,
    current_revision,
    guest_filter_options,
    guest_stats,
    list_guests,
    serialize_guest,
    timestamp_matches,
    touch_guest,
)

router = APIRouter()
NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
}


def json_error(detail: str, status_code: int, **extra: Any) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "detail": detail, **extra},
        status_code=status_code,
        headers=NO_STORE_HEADERS,
    )


def supplied_csrf(request: Request, body_token: str = "") -> str:
    return request.headers.get("X-CSRF-Token", "") or body_token


def validated_filters(
    *,
    status: str,
    side: str,
    age_group: str,
    invitation: str,
    gift: str,
    sort: str,
    direction: str,
) -> str | None:
    checks = (
        (status, RSVP_STATUSES, "estado de confirmação"),
        (side, SIDES, "parte"),
        (age_group, AGE_GROUPS, "grupo etário"),
        (invitation, ("sent", "pending"), "filtro de convite"),
        (gift, ("received", "pending"), "filtro de presente"),
        (sort, tuple(SORT_COLUMNS), "ordenação"),
        (direction, ("asc", "desc"), "direção"),
    )
    for value, allowed, label in checks:
        if value and value not in allowed:
            return f"O {label} não é válido."
    return None


def filters_payload(
    db,
    *,
    q: str,
    status: str,
    side: str,
    age_group: str,
    congregation: str,
    table_name: str,
    invitation: str,
    gift: str,
    sort: str,
    direction: str,
) -> dict[str, Any]:
    return {
        "q": q,
        "status": status,
        "rsvp_status": status,
        "side": side,
        "age_group": age_group,
        "congregation": congregation,
        "table_name": table_name,
        "invitation": invitation,
        "gift": gift,
        "sort": sort,
        "direction": direction,
        **guest_filter_options(db),
    }


@router.get("/guests", response_class=HTMLResponse, include_in_schema=False)
def guests_page(
    request: Request,
    q: str = Query("", max_length=100),
    archived: bool = False,
    status: str = Query("", max_length=30),
    rsvp_status: str = Query("", max_length=30),
    side: str = Query("", max_length=30),
    age_group: str = Query("", max_length=30),
    congregation: str = Query("", max_length=150),
    table_name: str = Query("", max_length=100),
    invitation: str = Query("", max_length=20),
    gift: str = Query("", max_length=20),
    sort: str = Query("name", max_length=30),
    direction: str = Query("asc", max_length=4),
) -> Response:
    """Render the active spreadsheet view while preserving the archived URL."""

    if redirect := require_login(request):
        return redirect
    spec = MODULES["guests"]
    search = q.strip()
    if archived:
        with SessionLocal() as db:
            records = db.scalars(module_query(spec, search, archived=True)).all()
            labels = {record.id: record_label(record) for record in records}
        return templates.TemplateResponse(
            request,
            "module_list.html",
            {
                "app_name": get_settings().app_name,
                "current_section": "guests",
                "module": spec,
                "records": records,
                "search": search,
                "record_labels": labels,
                "message": request.query_params.get("message"),
                "error": request.query_params.get("error"),
                "show_archived": True,
                "budget_data": None,
            },
        )

    status = rsvp_status or status
    validation_error = validated_filters(
        status=status,
        side=side,
        age_group=age_group,
        invitation=invitation,
        gift=gift,
        sort=sort,
        direction=direction,
    )
    if validation_error:
        return RedirectResponse("/guests?error=invalid_filter", status_code=303)

    with SessionLocal() as db:
        items, filtered = list_guests(
            db,
            q=search,
            status=status,
            side=side,
            age_group=age_group,
            congregation=congregation.strip(),
            table_name=table_name.strip(),
            invitation=invitation,
            gift=gift,
            sort=sort,
            direction=direction,
        )
        stats = guest_stats(db)
        filters = filters_payload(
            db,
            q=search,
            status=status,
            side=side,
            age_group=age_group,
            congregation=congregation.strip(),
            table_name=table_name.strip(),
            invitation=invitation,
            gift=gift,
            sort=sort,
            direction=direction,
        )
        revision = current_revision(db)
    initial_payload = {
        "ok": True,
        "items": items,
        "stats": stats,
        "filters": filters,
        "filtered": filtered,
        "revision": revision,
    }
    return templates.TemplateResponse(
        request,
        "guests.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "guests",
            "module": spec,
            "records": items,
            "guests": items,
            "guest_rows": items,
            "guest_stats": stats,
            "guest_filters": filters,
            "filtered_count": filtered,
            "initial_guest_payload": initial_payload,
            "guest_revision": revision,
            "search": search,
            "show_archived": False,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/api/guests")
def guests_api(
    request: Request,
    q: str = Query("", max_length=100),
    status: str = Query("", max_length=30),
    rsvp_status: str = Query("", max_length=30),
    side: str = Query("", max_length=30),
    age_group: str = Query("", max_length=30),
    congregation: str = Query("", max_length=150),
    table_name: str = Query("", max_length=100),
    invitation: str = Query("", max_length=20),
    gift: str = Query("", max_length=20),
    sort: str = Query("name", max_length=30),
    direction: str = Query("asc", max_length=4),
    limit: int = Query(500, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100_000),
) -> JSONResponse:
    status = rsvp_status or status
    validation_error = validated_filters(
        status=status,
        side=side,
        age_group=age_group,
        invitation=invitation,
        gift=gift,
        sort=sort,
        direction=direction,
    )
    if validation_error:
        return json_error(validation_error, 422)

    search = q.strip()
    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return json_error("A sessão terminou. Inicie sessão novamente.", 401)
        items, filtered = list_guests(
            db,
            q=search,
            status=status,
            side=side,
            age_group=age_group,
            congregation=congregation.strip(),
            table_name=table_name.strip(),
            invitation=invitation,
            gift=gift,
            sort=sort,
            direction=direction,
            limit=limit,
            offset=offset,
        )
        payload = {
            "ok": True,
            "items": items,
            "stats": guest_stats(db),
            "filters": filters_payload(
                db,
                q=search,
                status=status,
                side=side,
                age_group=age_group,
                congregation=congregation.strip(),
                table_name=table_name.strip(),
                invitation=invitation,
                gift=gift,
                sort=sort,
                direction=direction,
            ),
            "filtered": filtered,
            "limit": limit,
            "offset": offset,
            "revision": current_revision(db),
        }
    return JSONResponse(payload, headers=NO_STORE_HEADERS)


@router.post("/api/guests", status_code=201)
def create_guest(request: Request, payload: GuestCreate) -> JSONResponse:
    with SessionLocal() as db:
        user = authenticated_user(db, request)
        if user is None:
            return json_error("A sessão terminou. Inicie sessão novamente.", 401)
        if not valid_csrf_token(request, supplied_csrf(request, payload.csrf_token)):
            return json_error("A sessão de segurança expirou. Recarregue a página.", 403)

        values = payload.model_dump(exclude={"csrf_token"})
        guest = Guest(**values, created_by_id=user.id, updated_by_id=user.id)
        db.add(guest)
        try:
            db.flush()
            record_activity(
                db,
                user.id,
                "criou",
                f"adicionou convidado: {guest.name}",
                "guests",
            )
            db.commit()
            db.refresh(guest)
        except (IntegrityError, ValueError):
            db.rollback()
            return json_error("Não foi possível guardar o convidado.", 422)

        response = {
            "ok": True,
            "message": f"{guest.name} foi adicionado.",
            "guest": serialize_guest(guest, updated_by=user.name, created_by=user.name),
            "stats": guest_stats(db),
            "revision": current_revision(db),
        }
    return JSONResponse(response, status_code=201, headers=NO_STORE_HEADERS)


def validated_bulk_value(action: str, value: Any) -> tuple[bool, Any]:
    if action == "rsvp_status":
        return value in RSVP_STATUSES, value
    if action == "side":
        return value in ("", *SIDES), value
    if action in {"invitation_sent", "gift_received"}:
        return isinstance(value, bool), value
    if action == "table_name":
        return isinstance(value, str) and len(value.strip()) <= 100, value.strip() if isinstance(
            value, str
        ) else value
    if action == "archive":
        return value in (None, True), True
    return False, value


@router.post("/api/guests/bulk")
def bulk_update_guests(request: Request, payload: GuestBulkUpdate) -> JSONResponse:
    with SessionLocal() as db:
        user = authenticated_user(db, request)
        if user is None:
            return json_error("A sessão terminou. Inicie sessão novamente.", 401)
        if not valid_csrf_token(request, supplied_csrf(request, payload.csrf_token)):
            return json_error("A sessão de segurança expirou. Recarregue a página.", 403)
        valid, value = validated_bulk_value(payload.action, payload.value)
        if not valid:
            return json_error("O valor da alteração em grupo não é válido.", 422)

        guests = list(
            db.scalars(
                select(Guest)
                .where(Guest.id.in_(payload.ids), *active_guest_condition())
                .order_by(Guest.id)
            ).all()
        )
        found_ids = {guest.id for guest in guests}
        missing_ids = [guest_id for guest_id in payload.ids if guest_id not in found_ids]
        if not guests:
            return json_error(
                "Nenhum convidado ativo foi encontrado.", 404, missing_ids=missing_ids
            )

        conflicts = [
            guest.id
            for guest in guests
            if str(guest.id) in payload.expected_updated_at
            and not timestamp_matches(
                guest.updated_at,
                payload.expected_updated_at[str(guest.id)],
            )
        ]
        if conflicts:
            return json_error(
                "A lista foi alterada noutra sessão. Atualize antes de repetir.",
                409,
                conflict_ids=conflicts,
                revision=current_revision(db),
            )

        for guest in guests:
            if payload.action == "archive":
                guest.is_archived = True
            else:
                setattr(guest, payload.action, value)
            touch_guest(guest, user.id)
        labels = {
            "rsvp_status": "a confirmação",
            "invitation_sent": "o envio do convite",
            "gift_received": "a receção do presente",
            "table_name": "a mesa",
            "side": "a parte",
            "archive": "o arquivo",
        }
        record_activity(
            db,
            user.id,
            "alterou em grupo" if payload.action != "archive" else "arquivou",
            f"atualizou {labels[payload.action]} de {len(guests)} convidado(s)",
            "guests",
        )
        try:
            db.commit()
            for guest in guests:
                db.refresh(guest)
        except (IntegrityError, ValueError):
            db.rollback()
            return json_error("Não foi possível aplicar a alteração em grupo.", 422)

        response_items = [
            serialize_guest(guest, updated_by=user.name)
            for guest in guests
            if not guest.is_archived
        ]
        response = {
            "ok": True,
            "message": f"{len(guests)} convidado(s) atualizado(s).",
            "items": response_items,
            "updated_ids": [guest.id for guest in guests],
            "archived_ids": [guest.id for guest in guests if guest.is_archived],
            "missing_ids": missing_ids,
            "stats": guest_stats(db),
            "revision": current_revision(db),
        }
    return JSONResponse(response, headers=NO_STORE_HEADERS)


@router.patch("/api/guests/{guest_id}")
def update_guest(request: Request, guest_id: int, payload: GuestUpdate) -> JSONResponse:
    with SessionLocal() as db:
        user = authenticated_user(db, request)
        if user is None:
            return json_error("A sessão terminou. Inicie sessão novamente.", 401)
        if not valid_csrf_token(request, supplied_csrf(request, payload.csrf_token)):
            return json_error("A sessão de segurança expirou. Recarregue a página.", 403)
        guest = active_guest(db, guest_id)
        if guest is None:
            return json_error("O convidado não existe ou foi arquivado.", 404)
        if not timestamp_matches(guest.updated_at, payload.expected_updated_at):
            updated_by = ""
            if guest.updated_by_id:
                updated_by = (
                    db.scalar(select(User.name).where(User.id == guest.updated_by_id)) or ""
                )
            return json_error(
                "Este convidado foi alterado noutra sessão. Atualize a lista antes de guardar.",
                409,
                guest=serialize_guest(guest, updated_by=updated_by),
                revision=current_revision(db),
            )

        changes = payload.model_dump(
            exclude_unset=True,
            exclude={"csrf_token", "expected_updated_at"},
        )
        for field, value in changes.items():
            setattr(guest, field, value)
        touch_guest(guest, user.id)
        changed_labels = ", ".join(changes)
        record_activity(
            db,
            user.id,
            "alterou",
            f"alterou convidado {guest.name}: {changed_labels}",
            "guests",
        )
        try:
            db.commit()
            db.refresh(guest)
        except (IntegrityError, ValueError):
            db.rollback()
            return json_error("Não foi possível guardar a alteração.", 422)

        response = {
            "ok": True,
            "message": f"{guest.name} foi atualizado.",
            "guest": serialize_guest(guest, updated_by=user.name),
            "stats": guest_stats(db),
            "revision": current_revision(db),
        }
    return JSONResponse(response, headers=NO_STORE_HEADERS)
