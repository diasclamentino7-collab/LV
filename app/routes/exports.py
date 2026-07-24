"""Authenticated PDF exports for the full workspace and every planning module."""

from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from app.db.session import SessionLocal
from app.routes.pages import MODULES, module_query
from app.services.auth_session import authenticated_user
from app.services.pdf_export import build_full_pdf, build_module_pdf

router = APIRouter(tags=["exports"])


def _pdf_response(content: bytes, filename: str) -> Response:
    safe_filename = re.sub(r"[^a-z0-9._-]+", "-", filename.casefold()).strip("-")
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/settings/export.pdf", include_in_schema=False)
@router.get("/exports/all.pdf", include_in_schema=False)
def export_all_pdf(request: Request) -> Response:
    """Download a complete human-readable report without authentication secrets."""

    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return RedirectResponse("/login", status_code=303)
        content = build_full_pdf(db)
    filename = f"lv-wedding-planeamento-{date.today().isoformat()}.pdf"
    return _pdf_response(content, filename)


@router.get("/exports/{slug}.pdf", include_in_schema=False)
def export_module_pdf(
    request: Request,
    slug: str,
    q: str = "",
    archived: bool = False,
) -> Response:
    """Download the currently selected active or archived module list."""

    spec = MODULES.get(slug)
    if spec is None or slug in {"settings", "ceremony", "quinta"}:
        return RedirectResponse("/dashboard", status_code=303)
    search = q.strip()[:100]
    with SessionLocal() as db:
        if authenticated_user(db, request) is None:
            return RedirectResponse("/login", status_code=303)
        records = db.scalars(module_query(spec, search, archived)).all()
        content = build_module_pdf(
            db,
            title=spec.title,
            records=records,
            archived=archived,
        )
    state = "eliminados" if archived else "ativos"
    filename = f"lv-{slug}-{state}-{date.today().isoformat()}.pdf"
    return _pdf_response(content, filename)
