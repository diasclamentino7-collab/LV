import re
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.auth as auth_routes
import app.routes.pages as page_routes
import app.routes.web as web_routes
from app.db.base import Base
from app.main import app
from app.models.core import ProjectSettings, User
from app.services.security import hash_password


def csrf_from(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def secure_test_session(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    for module in (web_routes, auth_routes, page_routes, templating_module):
        monkeypatch.setattr(module, "SessionLocal", test_session)

    with Session(engine) as db:
        user = User(name="Vítor", password_hash=hash_password("password123"))
        db.add(user)
        db.flush()
        db.add(ProjectSettings(id=1, created_by_id=user.id, updated_by_id=user.id))
        db.commit()
        return engine, user.id


def login(client: TestClient, user_id: int, password: str = "password123"):
    token = csrf_from(client.get("/login"))
    return client.post(
        "/login",
        data={"user_id": user_id, "password": password, "csrf_token": token},
        follow_redirects=False,
    )


def test_password_change_revokes_every_existing_session(monkeypatch) -> None:
    _, user_id = secure_test_session(monkeypatch)

    with TestClient(app) as first_client, TestClient(app) as second_client:
        assert login(first_client, user_id).status_code == 303
        assert login(second_client, user_id).status_code == 303
        password_page = first_client.get("/account/password")
        changed = first_client.post(
            "/account/password",
            data={
                "current_password": "password123",
                "new_password": "a-new-secure-password",
                "csrf_token": csrf_from(password_page),
            },
            follow_redirects=False,
        )

        assert changed.headers["location"] == "/login?password=changed"
        assert (
            second_client.get("/dashboard", follow_redirects=False).headers["location"] == "/login"
        )
        assert login(first_client, user_id, "a-new-secure-password").status_code == 303


def test_repeated_failed_logins_temporarily_lock_the_account(monkeypatch) -> None:
    engine, user_id = secure_test_session(monkeypatch)

    with TestClient(app) as client:
        for _ in range(auth_routes.MAX_LOGIN_ATTEMPTS):
            response = login(client, user_id, "wrong-password")
            assert response.status_code == 303
        locked = login(client, user_id, "password123")

    assert locked.headers["location"] == "/login?error=locked"
    with Session(engine) as db:
        assert db.get(User, user_id).locked_until is not None


def test_production_setup_requires_the_private_installation_token(monkeypatch) -> None:
    token = "private-installation-token-with-more-than-32-characters"
    monkeypatch.setattr(
        auth_routes,
        "get_settings",
        lambda: SimpleNamespace(environment="production", setup_token=token),
    )

    assert auth_routes.valid_setup_access_token(token)
    assert not auth_routes.valid_setup_access_token("wrong-token")
