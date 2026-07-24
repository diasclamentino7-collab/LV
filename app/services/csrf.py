"""Session-bound CSRF protection for every state-changing HTML form."""

from __future__ import annotations

import hmac
import secrets

from fastapi import Request

CSRF_SESSION_KEY = "_csrf_token"


def get_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return str(token)


def valid_csrf_token(request: Request, supplied_token: str | None) -> bool:
    expected_token = request.session.get(CSRF_SESSION_KEY)
    return bool(
        expected_token
        and supplied_token
        and hmac.compare_digest(str(expected_token), supplied_token)
    )
