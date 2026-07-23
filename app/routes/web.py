from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import SessionLocal
from app.models.core import Activity, User
from app.models.planning import BudgetCategory, Guest, Task

router = APIRouter()
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> Response:
    user_id = request.session.get("user_id")
    if user_id is None:
        with SessionLocal() as db:
            has_users = db.scalar(select(func.count()).select_from(User)) > 0
        return RedirectResponse("/login" if has_users else "/setup", status_code=303)
    with SessionLocal() as db:
        activities = db.scalars(
            select(Activity).order_by(Activity.occurred_at.desc()).limit(6)
        ).all()
        stats = {
            "guests": db.scalar(
                select(func.count()).select_from(Guest).where(Guest.is_archived.is_(False))
            ),
            "tasks": db.scalar(
                select(func.count()).select_from(Task).where(Task.is_archived.is_(False))
            ),
            "categories": db.scalar(
                select(func.count())
                .select_from(BudgetCategory)
                .where(BudgetCategory.is_archived.is_(False))
            ),
        }
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "dashboard",
            "activities": activities,
            "stats": stats,
        },
    )
