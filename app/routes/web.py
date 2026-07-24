"""Dashboard, project settings and safe data portability routes."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.templating import CURRENCY_SYMBOLS, safe_color, templates
from app.db.session import SessionLocal
from app.models.core import Activity, ProjectSettings, User
from app.models.moodboard import MoodboardItem
from app.models.planning import Guest, Payment, Task
from app.repositories.project_settings import get_project_settings
from app.schemas.settings import (
    AppearanceSettings,
    EventSettings,
    FinanceSettings,
    IdentitySettings,
    PlanningSettings,
)
from app.services.activity import record_activity
from app.services.auth_session import authenticated_user
from app.services.csrf import valid_csrf_token
from app.services.data_export import build_data_export
from app.services.finance import financial_summary

router = APIRouter()
SETTINGS_SECTIONS = frozenset({"identity", "event", "finance", "appearance", "planning"})
LANGUAGES = frozenset({"pt-PT", "en-GB", "en-US", "es-ES", "fr-FR"})


def require_user(request: Request) -> RedirectResponse | None:
    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return RedirectResponse("/login", status_code=303)
    return None


def decimal_or_zero(value: str | Decimal | None) -> Decimal:
    try:
        parsed = Decimal(str(value or "0").replace(",", "."))
        if not parsed.is_finite() or parsed < 0:
            return Decimal("0")
        return parsed
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def checked(form: dict[str, str], field: str) -> bool:
    return field in form and form[field].casefold() not in {"", "0", "false", "off"}


def planning_snapshot(db, settings: ProjectSettings) -> tuple[dict[str, int], dict]:
    """Build the shared live dashboard totals from persisted records."""

    stats = {
        "guests": db.scalar(
            select(func.count()).select_from(Guest).where(Guest.is_archived.is_(False))
        ),
        "confirmed_guests": db.scalar(
            select(func.count())
            .select_from(Guest)
            .where(Guest.is_archived.is_(False), Guest.rsvp_status == "Confirmado")
        ),
        "tasks": db.scalar(
            select(func.count()).select_from(Task).where(Task.is_archived.is_(False))
        ),
        "completed_tasks": db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.is_archived.is_(False), Task.status == "Concluído")
        ),
    }
    stats["task_percentage"] = (
        int(stats["completed_tasks"] / stats["tasks"] * 100) if stats["tasks"] else 0
    )
    finance = financial_summary(db, decimal_or_zero(settings.total_budget))
    return stats, finance


def localized_wedding_target(settings: ProjectSettings) -> datetime | None:
    """Return the wedding moment in the configured project timezone."""

    if settings.wedding_date is None:
        return None
    try:
        wedding_timezone = ZoneInfo(settings.wedding_timezone)
    except ZoneInfoNotFoundError:
        wedding_timezone = ZoneInfo("Europe/Lisbon")
    if settings.wedding_date.tzinfo is None:
        return settings.wedding_date.replace(tzinfo=wedding_timezone)
    return settings.wedding_date.astimezone(wedding_timezone)


def valid_logo_path(value: str, current_value: str = "") -> bool:
    if not value:
        return True
    if value == current_value:
        return True
    normalized = value.replace("\\", "/")
    if ".." in normalized.split("/"):
        return False
    if normalized.startswith(("/static/", "/uploads/", "uploads/")):
        return True
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def identity_updates(
    form: dict[str, str],
    settings: ProjectSettings,
) -> dict[str, object]:
    payload = IdentitySettings.model_validate(
        {
            "project_name": form.get("project_name", ""),
            "partner_one_name": form.get("partner_one_name", ""),
            "partner_two_name": form.get("partner_two_name", ""),
            "language": settings.language,
        }
    )
    logo_path = form.get("logo_path", "").strip()
    if len(logo_path) > 500 or not valid_logo_path(logo_path, settings.logo_path):
        raise ValueError("invalid logo")
    return {**payload.model_dump(exclude={"language"}), "logo_path": logo_path}


def event_updates(form: dict[str, str]) -> dict[str, object]:
    wedding_date_value = form.get("wedding_date", "").strip() or None
    payload = EventSettings.model_validate(
        {
            "wedding_date": wedding_date_value,
            "wedding_style": form.get("wedding_style", "Mid-century vintage"),
            "wedding_timezone": form.get("wedding_timezone", "Europe/Lisbon"),
            "wedding_city": form.get("wedding_city", ""),
            "ceremony_venue": form.get("ceremony_venue", ""),
            "reception_venue": form.get("reception_venue", ""),
        }
    )
    raw_time = form.get("wedding_time", "").strip()
    wedding_time = time.fromisoformat(raw_time) if raw_time else time()
    wedding_date = None
    if payload.wedding_date:
        wedding_timezone = ZoneInfo(payload.wedding_timezone)
        wedding_date = datetime.combine(
            payload.wedding_date,
            wedding_time,
            tzinfo=wedding_timezone,
        )
    guest_target = int(form.get("guest_target", "0") or 0)
    if not 0 <= guest_target <= 10_000:
        raise ValueError("invalid guest target")
    return {
        **payload.model_dump(exclude={"wedding_date"}),
        "wedding_date": wedding_date,
        "guest_target": guest_target,
    }


def finance_updates(
    form: dict[str, str],
    settings: ProjectSettings,
) -> dict[str, object]:
    payload = FinanceSettings.model_validate(
        {
            "total_budget": form.get("total_budget", "0"),
            "currency": form.get("currency", "EUR"),
            "guest_target": settings.guest_target,
            "budget_alert_percent": form.get("budget_alert_percent", "80"),
        }
    )
    return {
        "total_budget": format(payload.total_budget, ".2f"),
        "currency": payload.currency,
        "budget_alert_percent": payload.budget_alert_percent,
    }


def appearance_updates(
    form: dict[str, str],
    settings: ProjectSettings,
) -> dict[str, object]:
    payload = AppearanceSettings.model_validate(
        {
            "primary_color": form.get("primary_color", ""),
            "secondary_color": form.get("secondary_color", ""),
            "accent_color": form.get("accent_color", ""),
            "background_color": form.get("background_color", ""),
            "logo_path": settings.logo_path,
        }
    )
    return payload.model_dump(exclude={"logo_path"})


def planning_updates(form: dict[str, str], submitted_version: int) -> dict[str, object]:
    language = form.get("language", "pt-PT")
    if language not in LANGUAGES:
        raise ValueError("invalid language")
    payload = PlanningSettings.model_validate(
        {
            "reminder_days_before": form.get("reminder_days_before", "7"),
            "reminders_enabled": checked(form, "reminders_enabled"),
            "default_assignee": form.get("default_assignee", ""),
            "default_task_priority": form.get("default_task_priority", "Média"),
            "dashboard_show_countdown": checked(form, "dashboard_show_countdown"),
            "dashboard_show_finance": checked(form, "dashboard_show_finance"),
            "dashboard_show_activity": checked(form, "dashboard_show_activity"),
            "dashboard_show_moodboard": checked(form, "dashboard_show_moodboard"),
            "motion_preference": form.get("motion_preference", "full"),
            "settings_version": submitted_version,
        }
    )
    return {**payload.model_dump(exclude={"settings_version"}), "language": language}


def build_section_updates(
    section: str,
    form: dict[str, str],
    settings: ProjectSettings,
    submitted_version: int,
) -> dict[str, object]:
    if section == "identity":
        return identity_updates(form, settings)
    if section == "event":
        return event_updates(form)
    if section == "finance":
        return finance_updates(form, settings)
    if section == "appearance":
        return appearance_updates(form, settings)
    return planning_updates(form, submitted_version)


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request) -> Response:
    if redirect := require_user(request):
        return redirect
    with SessionLocal() as db:
        settings = get_project_settings(db, user_id=request.session["user_id"])
        assert settings is not None
        users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)).all()
        current_user = db.get(User, request.session["user_id"])
        updater = db.get(User, settings.updated_by_id) if settings.updated_by_id else None
        finance = financial_summary(db, decimal_or_zero(settings.total_budget))
        try:
            display_timezone = ZoneInfo(settings.wedding_timezone)
        except ZoneInfoNotFoundError:
            display_timezone = ZoneInfo("Europe/Lisbon")
        updated_at_local = settings.updated_at
        if updated_at_local is not None:
            if updated_at_local.tzinfo is None:
                updated_at_local = updated_at_local.replace(tzinfo=UTC)
            updated_at_local = updated_at_local.astimezone(display_timezone)
        wedding_date_local = settings.wedding_date
        if wedding_date_local is not None:
            if wedding_date_local.tzinfo is None:
                wedding_date_local = wedding_date_local.replace(tzinfo=display_timezone)
            else:
                wedding_date_local = wedding_date_local.astimezone(display_timezone)
        stats = {
            "confirmed_guests": db.scalar(
                select(func.count())
                .select_from(Guest)
                .where(Guest.is_archived.is_(False), Guest.rsvp_status == "Confirmado")
            ),
            "open_tasks": db.scalar(
                select(func.count())
                .select_from(Task)
                .where(Task.is_archived.is_(False), Task.status != "Concluído")
            ),
        }
        db.expunge(settings)
        for user in users:
            db.expunge(user)
        if current_user is not None and current_user not in users:
            db.expunge(current_user)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "settings",
            "settings": settings,
            "users": users,
            "current_user": current_user,
            "updated_by_name": updater.name if updater else "Sistema",
            "finance": finance,
            "stats": stats,
            "updated_at_local": updated_at_local,
            "wedding_date_local": wedding_date_local,
            "saved_section": request.query_params.get("saved"),
            "error": request.query_params.get("error"),
            "currency_symbol": CURRENCY_SYMBOLS.get(settings.currency, settings.currency),
        },
    )


@router.post("/settings/{section}", include_in_schema=False)
async def save_settings_section(
    request: Request,
    section: str,
) -> RedirectResponse:
    if redirect := require_user(request):
        return redirect
    if section not in SETTINGS_SECTIONS:
        return RedirectResponse("/settings?error=section", status_code=303)
    form = {key: str(value) for key, value in (await request.form()).items()}
    if not valid_csrf_token(request, form.pop("csrf_token", "")):
        return RedirectResponse(
            f"/settings?error=csrf&section={section}#{section}",
            status_code=303,
        )
    try:
        submitted_version = int(form.get("settings_version", "0"))
    except ValueError:
        submitted_version = 0

    with SessionLocal() as db:
        settings = get_project_settings(db, user_id=request.session["user_id"])
        assert settings is not None
        try:
            updates = build_section_updates(section, form, settings, submitted_version)
        except (InvalidOperation, ValidationError, ValueError):
            return RedirectResponse(
                f"/settings?error=invalid&section={section}#{section}",
                status_code=303,
            )
        if section == "finance" and updates["currency"] != settings.currency:
            finance = financial_summary(db, decimal_or_zero(settings.total_budget))
            has_financial_data = any(
                decimal_or_zero(finance.get(key)) > 0
                for key in ("expenses", "allocated", "pending")
            )
            if has_financial_data and not checked(form, "confirm_currency_change"):
                return RedirectResponse(
                    "/settings?error=currency_confirmation&section=finance#finance",
                    status_code=303,
                )
        result = db.execute(
            update(ProjectSettings)
            .where(
                ProjectSettings.id == settings.id,
                ProjectSettings.settings_version == submitted_version,
            )
            .values(
                **updates,
                settings_version=submitted_version + 1,
                updated_by_id=request.session["user_id"],
                updated_at=func.now(),
            )
        )
        if result.rowcount != 1:
            db.rollback()
            return RedirectResponse(
                f"/settings?error=conflict&section={section}#{section}",
                status_code=303,
            )
        record_activity(
            db,
            request.session["user_id"],
            "alterou",
            f"atualizou as configurações de {section}",
            "settings",
        )
        db.commit()
    return RedirectResponse(f"/settings?saved={section}#{section}", status_code=303)


@router.get("/settings/export", include_in_schema=False)
def export_settings_data(request: Request) -> Response:
    if redirect := require_user(request):
        return redirect
    with SessionLocal() as db:
        payload = build_data_export(db)
    filename = f"lv-wedding-export-{date.today().isoformat()}.json"
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/manifest.webmanifest", include_in_schema=False)
def dynamic_manifest() -> JSONResponse:
    with SessionLocal() as db:
        settings = get_project_settings(db)
        assert settings is not None
        return JSONResponse(
            {
                "name": "LV – Wedding Planner",
                "short_name": "LV Wedding",
                "description": "Planeamento partilhado do vosso casamento.",
                "id": "/dashboard",
                "start_url": "/dashboard",
                "scope": "/",
                "display": "standalone",
                "orientation": "any",
                "categories": ["lifestyle", "productivity"],
                "background_color": safe_color(settings.background_color, "#FAF8F6"),
                "theme_color": safe_color(settings.primary_color, "#D88BA7"),
                "lang": "pt-PT",
                "shortcuts": [
                    {
                        "name": "Checklist",
                        "short_name": "Checklist",
                        "url": "/checklist",
                    },
                    {
                        "name": "Orçamento",
                        "short_name": "Orçamento",
                        "url": "/budget",
                    },
                    {
                        "name": "Comunicação",
                        "short_name": "Comunicação",
                        "url": "/communication",
                    },
                ],
                "icons": [
                    {
                        "src": "/static/icons/icon.svg",
                        "sizes": "any",
                        "type": "image/svg+xml",
                        "purpose": "any maskable",
                    }
                ],
            }
        )


@router.get("/api/dashboard-summary", include_in_schema=False)
def dashboard_summary(request: Request) -> Response:
    """Return small, no-cache live values for targeted dashboard refreshes."""

    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return JSONResponse({"detail": "Sessão necessária."}, status_code=401)
        settings = get_project_settings(db, user_id=request.session["user_id"])
        assert settings is not None
        stats, finance = planning_snapshot(db, settings)
        target = localized_wedding_target(settings)
        activity_rows = db.execute(
            select(Activity, User.name.label("user_name"))
            .outerjoin(User, Activity.user_id == User.id)
            .order_by(Activity.occurred_at.desc())
            .limit(6)
        ).all()
        payload = {
            "confirmed_guests": stats["confirmed_guests"],
            "guest_target": settings.guest_target,
            "guests": stats["guests"],
            "task_percentage": stats["task_percentage"],
            "completed_tasks": stats["completed_tasks"],
            "tasks": stats["tasks"],
            "currency_symbol": CURRENCY_SYMBOLS.get(
                settings.currency,
                settings.currency,
            ),
            "expenses": format(finance["expenses"], ".2f"),
            "categories": finance["categories"],
            "budget_total": format(finance["total"], ".2f"),
            "budget_allocated": format(finance["allocated"], ".2f"),
            "budget_pending": format(finance["pending"], ".2f"),
            "budget_remaining": format(finance["remaining"], ".2f"),
            "budget_percentage": finance["percentage"],
            "budget_progress": finance["progress_percentage"],
            "budget_alert": (
                settings.budget_alert_percent > 0
                and finance["percentage"] >= settings.budget_alert_percent
            ),
            "budget_alert_percent": settings.budget_alert_percent,
            "wedding_target": target.isoformat() if target else None,
            "wedding_timezone": settings.wedding_timezone,
            "activities": [
                {
                    "id": activity.id,
                    "user_name": user_name or "Sistema",
                    "description": activity.description,
                    "occurred_at": (
                        activity.occurred_at.replace(tzinfo=UTC).isoformat()
                        if activity.occurred_at.tzinfo is None
                        else activity.occurred_at.isoformat()
                    ),
                }
                for activity, user_name in activity_rows
            ],
        }
    return JSONResponse(
        payload,
        headers={"Cache-Control": "private, no-store, max-age=0"},
    )


@router.get("/activity", response_class=HTMLResponse, include_in_schema=False)
def activity_history(
    request: Request,
    user_id: int | None = None,
    module: str = "",
    action_type: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    """Show the shared, filterable audit trail in the project timezone."""

    if redirect := require_user(request):
        return redirect
    with SessionLocal() as db:
        settings = get_project_settings(db, user_id=request.session["user_id"])
        assert settings is not None
        try:
            display_timezone = ZoneInfo(settings.wedding_timezone)
        except ZoneInfoNotFoundError:
            display_timezone = ZoneInfo("Europe/Lisbon")

        statement = (
            select(Activity, User.name.label("user_name"))
            .outerjoin(User, Activity.user_id == User.id)
            .order_by(Activity.occurred_at.desc())
            .limit(250)
        )
        if user_id is not None:
            statement = statement.where(Activity.user_id == user_id)
        if module:
            statement = statement.where(Activity.module == module[:50])
        if action_type:
            statement = statement.where(Activity.action_type == action_type[:50])
        if date_from:
            statement = statement.where(
                Activity.occurred_at
                >= datetime.combine(date_from, time.min, tzinfo=display_timezone)
            )
        if date_to:
            statement = statement.where(
                Activity.occurred_at
                < datetime.combine(
                    date_to + timedelta(days=1),
                    time.min,
                    tzinfo=display_timezone,
                )
            )

        activity_rows = []
        for activity, user_name in db.execute(statement):
            occurred_at = activity.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=UTC)
            activity_rows.append(
                {
                    "user_name": user_name or "Sistema",
                    "occurred_at": occurred_at.astimezone(display_timezone),
                    "module": activity.module,
                    "action_type": activity.action_type,
                    "description": activity.description,
                }
            )
        users = db.scalars(select(User).order_by(User.name)).all()
        modules = db.scalars(select(Activity.module).distinct().order_by(Activity.module)).all()
        actions = db.scalars(
            select(Activity.action_type).distinct().order_by(Activity.action_type)
        ).all()

    return templates.TemplateResponse(
        request,
        "activity_history.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "activity",
            "activities": activity_rows,
            "users": users,
            "modules": modules,
            "actions": actions,
            "filters": {
                "user_id": user_id,
                "module": module,
                "action_type": action_type,
                "date_from": date_from,
                "date_to": date_to,
            },
        },
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> Response:
    user_id = request.session.get("user_id")
    if user_id is None:
        with SessionLocal() as db:
            has_users = db.scalar(select(func.count()).select_from(User)) > 0
        return RedirectResponse("/login" if has_users else "/setup", status_code=303)

    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return RedirectResponse("/login", status_code=303)
        settings = get_project_settings(db, user_id=user_id)
        assert settings is not None
        activities = db.scalars(
            select(Activity).order_by(Activity.occurred_at.desc()).limit(6)
        ).all()
        stats, finance = planning_snapshot(db, settings)
        users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)).all()
        user_names = dict(db.execute(select(User.id, User.name)).all())
        moodboard_items = db.scalars(
            select(MoodboardItem)
            .where(MoodboardItem.is_archived.is_(False))
            .order_by(MoodboardItem.updated_at.desc())
            .limit(4)
        ).all()
        task_statement = (
            select(Task)
            .where(
                Task.is_archived.is_(False),
                Task.status != "Concluído",
                Task.due_date.is_not(None),
            )
            .order_by(Task.due_date, Task.priority.desc())
            .limit(6)
        )
        if settings.reminders_enabled:
            task_statement = task_statement.where(
                Task.due_date <= date.today() + timedelta(days=settings.reminder_days_before)
            )
        upcoming_tasks = db.scalars(task_statement).all()
        payment_statement = (
            select(Payment)
            .where(
                Payment.is_archived.is_(False),
                Payment.status == "Pendente",
            )
            .order_by(Payment.payment_date)
            .limit(4)
        )
        if settings.reminders_enabled:
            payment_statement = payment_statement.where(
                Payment.payment_date <= date.today() + timedelta(days=settings.reminder_days_before)
            )
        upcoming_payments = db.scalars(payment_statement).all()

        configured_names = [
            name for name in (settings.partner_one_name, settings.partner_two_name) if name
        ]
        couple_names = " e ".join(configured_names or [user.name for user in users])
        try:
            wedding_timezone = ZoneInfo(settings.wedding_timezone)
        except ZoneInfoNotFoundError:
            wedding_timezone = ZoneInfo("Europe/Lisbon")
        activity_items = []
        for activity in activities:
            occurred_at = activity.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=UTC)
            activity_items.append(
                {
                    "description": activity.description,
                    "user_name": user_names.get(activity.user_id, "Sistema"),
                    "occurred_at": occurred_at.astimezone(wedding_timezone),
                }
            )
        countdown = None
        target = localized_wedding_target(settings)
        if target:
            raw_seconds = int((target - datetime.now(wedding_timezone)).total_seconds())
            seconds = max(0, raw_seconds)
            countdown = {
                "days": seconds // 86_400,
                "hours": seconds % 86_400 // 3_600,
                "minutes": seconds % 3_600 // 60,
                "seconds": seconds % 60,
                "date": target,
                "is_past": raw_seconds <= 0,
            }
        db.expunge(settings)
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "dashboard",
            "activities": activity_items,
            "stats": stats,
            "countdown": countdown,
            "couple_names": couple_names or "Leonor e Vítor",
            "finance": finance,
            "moodboard_items": moodboard_items,
            "upcoming_tasks": upcoming_tasks,
            "upcoming_payments": upcoming_payments,
            "settings": settings,
            "budget_alert": (
                settings.budget_alert_percent > 0
                and finance["percentage"] >= settings.budget_alert_percent
            ),
            "currency_symbol": CURRENCY_SYMBOLS.get(settings.currency, settings.currency),
        },
    )
