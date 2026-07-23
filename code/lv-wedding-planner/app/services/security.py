"""Password hashing with the standard library's PBKDF2 implementation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "$".join(
        (str(ITERATIONS), base64.b64encode(salt).decode(), base64.b64encode(digest).decode())
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        iterations, salt, expected = stored_hash.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt), int(iterations)
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(base64.b64encode(digest).decode(), expected)
