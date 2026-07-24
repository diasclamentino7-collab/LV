from datetime import datetime, time
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import SessionLocal
from app.models.core import Activity, ProjectSettings, User
from app.models.moodboard import MoodboardItem
from app.models.planning import BudgetCategory, Guest, Task
from app.services.finance import financial_summary

router = APIRouter()
templates = Jinja2Templates(directory=PROJECT_ROOT / "app" / "templates")


def project_settings(db):
    settings = db.scalar(select(ProjectSettings).order_by(ProjectSettings.id).limit(1))
    if settings is None:
        settings = ProjectSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request) -> Response:
    if request.session.get("user_id") is None:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        settings = project_settings(db)
        db.expunge(settings)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"app_name": get_settings().app_name, "current_section": "settings", "settings": settings},
    )


@router.post("/settings", include_in_schema=False)
def save_settings(
    request: Request,
    project_name: str = Form(...),
    wedding_date: str = Form(""),
    total_budget: str = Form("0"),
    currency: str = Form("EUR"),
) -> RedirectResponse:
    if request.session.get("user_id") is None:
        return RedirectResponse("/login", status_code=303)
    with SessionLocal() as db:
        settings = project_settings(db)
        settings.project_name = project_name.strip()
        settings.wedding_date = (
            datetime.combine(datetime.fromisoformat(wedding_date).date(), time())
            if wedding_date
            else None
        )
        settings.total_budget = total_budget
        settings.currency = currency
        settings.updated_by_id = request.session["user_id"]
        db.commit()
    return RedirectResponse("/dashboard", status_code=303)


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
        settings = db.scalar(select(ProjectSettings).order_by(ProjectSettings.id).limit(1))
        configured_budget = settings.total_budget if settings and settings.total_budget else "0"
        finance = financial_summary(db, Decimal(configured_budget))
        users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)).all()
        moodboard_items = db.scalars(
            select(MoodboardItem)
            .where(MoodboardItem.is_archived.is_(False))
            .order_by(MoodboardItem.updated_at.desc())
            .limit(4)
        ).all()
        countdown = None
        if settings and settings.wedding_date:
            target = settings.wedding_date
            remaining = (
                target - datetime.now(target.tzinfo) if target.tzinfo else target - datetime.now()
            )
            countdown = {
                "days": max(0, remaining.days),
                "hours": max(0, remaining.seconds // 3600),
                "date": target,
            }
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "dashboard",
            "activities": activities,
            "stats": stats,
            "countdown": countdown,
            "couple_names": " e ".join(user.name for user in users),
            "finance": finance,
            "moodboard_items": moodboard_items,
        },
    )
