"""Specialized visual overview for persisted table and guest assignments."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response

from app.core.config import get_settings
from app.core.templating import templates
from app.db.session import SessionLocal
from app.routes.pages import MODULES, module_query, record_label, require_login
from app.services.table_plan import build_table_plan

router = APIRouter()


@router.get("/table-plan", response_class=HTMLResponse, include_in_schema=False)
def table_plan_page(
    request: Request,
    q: str = Query("", max_length=100),
    archived: bool = False,
) -> Response:
    """Render the seating scheme while preserving the generic archive view."""

    if redirect := require_login(request):
        return redirect

    module = MODULES["table-plan"]
    search = q.strip()
    if archived:
        with SessionLocal() as db:
            records = db.scalars(module_query(module, search, archived=True)).all()
            record_labels = {record.id: record_label(record) for record in records}
        return templates.TemplateResponse(
            request,
            "module_list.html",
            {
                "app_name": get_settings().app_name,
                "current_section": "table-plan",
                "module": module,
                "records": records,
                "search": search,
                "record_labels": record_labels,
                "message": request.query_params.get("message"),
                "error": request.query_params.get("error"),
                "show_archived": True,
                "budget_data": None,
            },
        )

    with SessionLocal() as db:
        plan = build_table_plan(db)
    return templates.TemplateResponse(
        request,
        "table_plan.html",
        {
            "app_name": get_settings().app_name,
            "current_section": "table-plan",
            "module": module,
            "records": plan["tables"],
            "tables": plan["tables"],
            "unassigned_guests": plan["unassigned_guests"],
            "stats": plan["stats"],
            "table_options": plan["table_options"],
            "search": search,
            "show_archived": False,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )
