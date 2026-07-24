import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.templating import templates
from app.db.session import SessionLocal
from app.models.core import User
from app.repositories.project_settings import get_project_settings
from app.services.activity import record_activity
from app.services.auth_session import authenticated_user, start_user_session
from app.services.csrf import valid_csrf_token
from app.services.security import hash_password, verify_password

router = APIRouter()
MAX_PASSWORD_LENGTH = 256
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def valid_setup_access_token(provided_token: str) -> bool:
    """Protect first-run account creation on public production deployments."""

    settings = get_settings()
    if settings.environment.strip().casefold() not in {"production", "prod"}:
        return True
    return bool(settings.setup_token) and secrets.compare_digest(
        provided_token,
        settings.setup_token,
    )


def aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@router.get("/setup", response_class=HTMLResponse, include_in_schema=False)
def setup_page(request: Request) -> Response:
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return RedirectResponse("/login", status_code=303)
    environment = get_settings().environment.strip().casefold()
    return templates.TemplateResponse(
        request,
        "setup.html",
        {
            "app_name": get_settings().app_name,
            "setup_token_required": environment in {"production", "prod"},
        },
    )


@router.post("/setup", include_in_schema=False)
def setup_users(
    request: Request,
    first_name: str = Form("Vítor"),
    first_password: str = Form(...),
    second_name: str = Form("Leonor"),
    second_password: str = Form(...),
    csrf_token: str = Form(""),
    setup_access_token: str = Form(""),
) -> RedirectResponse:
    if not valid_setup_access_token(setup_access_token):
        return RedirectResponse("/setup?error=access", status_code=303)
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/setup?error=csrf", status_code=303)
    clean_first_name = first_name.strip()
    clean_second_name = second_name.strip()
    if (
        len(first_password) < 8
        or len(second_password) < 8
        or len(first_password) > MAX_PASSWORD_LENGTH
        or len(second_password) > MAX_PASSWORD_LENGTH
        or not clean_first_name
        or not clean_second_name
        or clean_first_name.casefold() == clean_second_name.casefold()
    ):
        return RedirectResponse(
            "/setup?error=Dados+inválidos",
            status_code=303,
        )
    with SessionLocal() as db:
        if not db.scalar(select(func.count()).select_from(User)):
            settings = get_project_settings(db)
            db.add_all(
                [
                    User(name=clean_first_name, password_hash=hash_password(first_password)),
                    User(name=clean_second_name, password_hash=hash_password(second_password)),
                ]
            )
            if settings is not None:
                settings.partner_one_name = clean_first_name
                settings.partner_two_name = clean_second_name
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/login?created=1", status_code=303)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request) -> Response:
    with SessionLocal() as db:
        if not db.scalar(select(func.count()).select_from(User)):
            return RedirectResponse("/setup", status_code=303)
        users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)).all()
    return templates.TemplateResponse(
        request, "login.html", {"app_name": get_settings().app_name, "users": users}
    )


@router.post("/login", include_in_schema=False)
def login(
    request: Request,
    user_id: int = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(""),
) -> RedirectResponse:
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/login?error=csrf", status_code=303)
    with SessionLocal() as db:
        user = db.get(User, user_id)
        now = datetime.now(UTC)
        if (
            user is not None
            and user.locked_until is not None
            and aware_utc(user.locked_until) > now
        ):
            return RedirectResponse("/login?error=locked", status_code=303)
        password_is_valid = (
            user is not None
            and user.is_active
            and len(password) <= MAX_PASSWORD_LENGTH
            and verify_password(password, user.password_hash)
        )
        if not password_is_valid:
            if user is not None and user.is_active:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                    user.failed_login_attempts = 0
                    user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                db.commit()
            return RedirectResponse("/login?error=1", status_code=303)
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        db.refresh(user)
        if user.name.casefold() == "leonor":
            request.session["pending_user_id"] = user.id
            request.session["pending_user_name"] = user.name
            request.session["pending_session_version"] = user.session_version
            return RedirectResponse("/love-confirmation", status_code=303)
        start_user_session(request, user)
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/love-confirmation", response_class=HTMLResponse, include_in_schema=False)
def love_confirmation_page(request: Request) -> Response:
    if request.session.get("pending_user_id") is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "love_confirmation.html", {"app_name": get_settings().app_name}
    )


@router.post("/love-confirmation", include_in_schema=False)
def love_confirmation(
    request: Request,
    answer: str = Form(...),
    csrf_token: str = Form(""),
) -> RedirectResponse:
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/login?error=csrf", status_code=303)
    user_id = request.session.pop("pending_user_id", None)
    user_name = request.session.pop("pending_user_name", None)
    session_version = request.session.pop("pending_session_version", None)
    if user_id is None or answer not in {"sim", "simmmm"}:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if (
            user is None
            or not user.is_active
            or user.session_version != session_version
            or user.name != user_name
        ):
            request.session.clear()
            return RedirectResponse("/login", status_code=303)
        start_user_session(request, user)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout", include_in_schema=False)
def logout(request: Request, csrf_token: str = Form("")) -> RedirectResponse:
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/dashboard?error=csrf", status_code=303)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/account/password", response_class=HTMLResponse, include_in_schema=False)
def password_page(request: Request) -> Response:
    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "password.html", {"app_name": get_settings().app_name}
    )


@router.post("/account/password", include_in_schema=False)
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    csrf_token: str = Form(""),
) -> RedirectResponse:
    if not valid_csrf_token(request, csrf_token):
        return RedirectResponse("/account/password?error=csrf", status_code=303)
    if not 8 <= len(new_password) <= MAX_PASSWORD_LENGTH:
        return RedirectResponse("/account/password?error=length", status_code=303)
    with SessionLocal() as db:
        user = authenticated_user(db, request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if len(current_password) > MAX_PASSWORD_LENGTH or not verify_password(
            current_password,
            user.password_hash,
        ):
            return RedirectResponse("/account/password?error=current", status_code=303)
        user.password_hash = hash_password(new_password)
        user.session_version += 1
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_by_id = user.id
        record_activity(
            db,
            user.id,
            "alterou",
            "alterou a própria password",
            "account",
        )
        db.commit()
    request.session.clear()
    return RedirectResponse("/login?password=changed", status_code=303)
