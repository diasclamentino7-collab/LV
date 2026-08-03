from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.guests as guest_routes
import app.routes.pages as page_routes
from app.core.config import get_settings
from app.db.base import Base
from app.models.core import Activity, User
from app.models.planning import Guest
from app.services.csrf import get_csrf_token


def make_client(monkeypatch) -> tuple[TestClient, sessionmaker, int]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as db:
        user = User(name="Leonor", password_hash="test-only", session_version=1)
        db.add(user)
        db.commit()
        user_id = user.id

    monkeypatch.setattr(guest_routes, "SessionLocal", testing_session)
    monkeypatch.setattr(page_routes, "SessionLocal", testing_session)
    monkeypatch.setattr(templating_module, "SessionLocal", testing_session)
    application = FastAPI()
    application.add_middleware(SessionMiddleware, secret_key="test-secret-that-is-long-enough")
    application.mount(
        "/static",
        StaticFiles(directory=get_settings().static_path),
        name="static",
    )
    application.include_router(guest_routes.router)

    @application.get("/test-login")
    def test_login(request: Request):
        request.session["user_id"] = user_id
        request.session["user_name"] = "Leonor"
        request.session["session_version"] = 1
        return {"csrf_token": get_csrf_token(request)}

    return TestClient(application), testing_session, user_id


def test_guest_api_requires_database_authenticated_session_and_never_caches(monkeypatch):
    client, _, _ = make_client(monkeypatch)

    response = client.get("/api/guests")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store, max-age=0"


def test_guest_api_returns_real_filtered_rows_stats_and_authorship(monkeypatch):
    client, testing_session, user_id = make_client(monkeypatch)
    with testing_session() as db:
        db.add_all(
            [
                Guest(
                    name="Ana Martins",
                    congregation="Lisboa",
                    side="Noiva",
                    rsvp_status="Confirmado",
                    table_name="Rosa",
                    invitation_sent=True,
                    created_by_id=user_id,
                    updated_by_id=user_id,
                ),
                Guest(
                    name="Bruno Costa",
                    congregation="Porto",
                    side="Noivo",
                    rsvp_status="Pendente",
                    gift_received=True,
                    created_by_id=user_id,
                    updated_by_id=user_id,
                ),
                Guest(
                    name="Registo arquivado",
                    is_archived=True,
                    created_by_id=user_id,
                    updated_by_id=user_id,
                ),
            ]
        )
        db.commit()
    client.get("/test-login")

    response = client.get("/api/guests?q=Ana&side=Noiva&sort=name&direction=asc")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filtered"] == 1
    assert [item["name"] for item in payload["items"]] == ["Ana Martins"]
    assert payload["items"][0]["updated_by"] == "Leonor"
    assert payload["stats"] == {
        "total": 2,
        "confirmed": 1,
        "pending": 1,
        "declined": 0,
        "seated": 1,
        "invitations_sent": 1,
        "gifts_received": 1,
        "confirmation_rate": 50.0,
    }
    assert payload["filters"]["congregations"] == ["Lisboa", "Porto"]
    assert payload["filters"]["tables"] == ["Rosa"]


def test_create_and_patch_are_csrf_protected_persist_immediately_and_detect_conflicts(
    monkeypatch,
):
    client, testing_session, user_id = make_client(monkeypatch)
    token = client.get("/test-login").json()["csrf_token"]
    guest_data = {
        "name": "Carla Silva",
        "congregation": "Sintra",
        "email": "carla@example.pt",
        "rsvp_status": "Pendente",
    }

    rejected = client.post("/api/guests", json=guest_data)
    assert rejected.status_code == 403

    created = client.post(
        "/api/guests",
        json=guest_data,
        headers={"X-CSRF-Token": token},
    )
    assert created.status_code == 201
    original = created.json()["guest"]
    assert original["updated_by"] == "Leonor"

    changed = client.patch(
        f"/api/guests/{original['id']}",
        json={
            "name": "Carla Lopes",
            "rsvp_status": "Confirmado",
            "expected_updated_at": original["updated_at"],
        },
        headers={"X-CSRF-Token": token},
    )
    assert changed.status_code == 200
    assert changed.json()["guest"]["name"] == "Carla Lopes"
    assert changed.json()["stats"]["confirmed"] == 1

    conflict = client.patch(
        f"/api/guests/{original['id']}",
        json={
            "notes": "Alteração baseada numa versão antiga",
            "expected_updated_at": original["updated_at"],
        },
        headers={"X-CSRF-Token": token},
    )
    assert conflict.status_code == 409

    unknown_field = client.patch(
        f"/api/guests/{original['id']}",
        json={"is_archived": True},
        headers={"X-CSRF-Token": token},
    )
    assert unknown_field.status_code == 422
    with testing_session() as db:
        stored = db.get(Guest, original["id"])
        assert stored is not None
        assert stored.name == "Carla Lopes"
        assert stored.rsvp_status == "Confirmado"
        assert stored.notes == ""
        assert stored.updated_by_id == user_id
        assert db.scalar(select(func.count()).select_from(Activity)) == 2


def test_bulk_guest_actions_are_bounded_audited_and_archive_compatibly(monkeypatch):
    client, testing_session, user_id = make_client(monkeypatch)
    with testing_session() as db:
        first = Guest(name="Duarte", created_by_id=user_id, updated_by_id=user_id)
        second = Guest(name="Eva", created_by_id=user_id, updated_by_id=user_id)
        db.add_all([first, second])
        db.commit()
        ids = [first.id, second.id]
    token = client.get("/test-login").json()["csrf_token"]

    rejected = client.post(
        "/api/guests/bulk",
        json={"ids": ids, "action": "invitation_sent", "value": True},
    )
    assert rejected.status_code == 403

    changed = client.post(
        "/api/guests/bulk",
        json={"ids": ids, "action": "table_name", "value": "Mesa Vintage"},
        headers={"X-CSRF-Token": token},
    )
    assert changed.status_code == 200
    assert changed.json()["updated_ids"] == ids
    assert changed.json()["stats"]["seated"] == 2

    archived = client.post(
        "/api/guests/bulk",
        json={"ids": [ids[0]], "action": "archive"},
        headers={"X-CSRF-Token": token},
    )
    assert archived.status_code == 200
    assert archived.json()["archived_ids"] == [ids[0]]
    assert archived.json()["stats"]["total"] == 1
    assert [item["id"] for item in client.get("/api/guests").json()["items"]] == [ids[1]]

    archived_page = client.get("/guests?archived=true")
    assert archived_page.status_code == 200
    assert "Duarte" in archived_page.text
    assert f"/guests/{ids[0]}/restore" in archived_page.text
    assert f"/guests/{ids[0]}/delete-permanently" in archived_page.text
    with testing_session() as db:
        assert db.get(Guest, ids[0]).is_archived is True
        assert db.scalar(select(func.count()).select_from(Activity)) == 2
