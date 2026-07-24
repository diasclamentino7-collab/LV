from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal

router = APIRouter(tags=["system"])


@router.get("/health", summary="Application health check")
def health_check() -> JSONResponse:
    """Report readiness only while the configured database is reachable."""
    try:
        with SessionLocal() as db:
            database_response = db.scalar(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            {"status": "unavailable", "database": "unavailable"},
            status_code=503,
        )
    if database_response != 1:
        return JSONResponse(
            {"status": "unavailable", "database": "unavailable"},
            status_code=503,
        )
    return JSONResponse({"status": "ok", "database": "ok"})
