from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import SessionLocal
from app.models.core import User
from app.services.security import hash_password, verify_password

router = APIRouter()
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")


@router.get("/setup", response_class=HTMLResponse, include_in_schema=False)
def setup_page(request: Request) -> Response:
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "setup.html", {"app_name": get_settings().app_name})


@router.post("/setup", include_in_schema=False)
def setup_users(
    first_name: str = Form("Vítor"),
    first_password: str = Form(...),
    second_name: str = Form("Leonor"),
    second_password: str = Form(...),
) -> RedirectResponse:
    if not first_password or not second_password or first_name.strip() == second_name.strip():
        return RedirectResponse("/setup?error=Dados+inválidos", status_code=303)
    with SessionLocal() as db:
        if not db.scalar(select(func.count()).select_from(User)):
            db.add_all(
                [
                    User(name=first_name.strip(), password_hash=hash_password(first_password)),
                    User(name=second_name.strip(), password_hash=hash_password(second_password)),
                ]
            )
            db.commit()
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
    request: Request, user_id: int = Form(...), password: str = Form(...)
) -> RedirectResponse:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            return RedirectResponse("/login?error=1", status_code=303)
        request.session["user_id"] = user.id
        request.session["user_name"] = user.name
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout", include_in_schema=False)
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/account/password", response_class=HTMLResponse, include_in_schema=False)
def password_page(request: Request) -> Response:
    if request.session.get("user_id") is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request, "password.html", {"app_name": get_settings().app_name}
    )


@router.post("/account/password", include_in_schema=False)
def change_password(
    request: Request, current_password: str = Form(...), new_password: str = Form(...)
) -> RedirectResponse:
    if len(new_password) < 8:
        return RedirectResponse("/account/password?error=length", status_code=303)
    with SessionLocal() as db:
        user = db.get(User, request.session.get("user_id"))
        if user is None or not verify_password(current_password, user.password_hash):
            return RedirectResponse("/account/password?error=current", status_code=303)
        user.password_hash = hash_password(new_password)
        db.commit()
    return RedirectResponse("/dashboard?message=password", status_code=303)
