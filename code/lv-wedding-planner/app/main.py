import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_settings
from app.routes import auth, health, pages, web


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepare filesystem storage; Alembic alone changes database schemas."""
    settings = get_settings()
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    settings.backups_path.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    application = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
    application.add_middleware(GZipMiddleware, minimum_size=1000)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=settings.session_https_only,
    )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'"
        )
        return response

    @application.exception_handler(413)
    async def file_too_large(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse({"detail": "Ficheiro demasiado grande."}, status_code=413)

    application.mount("/static", StaticFiles(directory=settings.static_path), name="static")
    application.include_router(web.router)
    application.include_router(auth.router)
    application.include_router(pages.router)
    application.include_router(health.router, prefix="/api")
    return application


app = create_app()
