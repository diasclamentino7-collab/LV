from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

import app.routes.communication_panel as panel
from app.db.base import Base
from app.models.core import Activity, User, WorkspaceRecord
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
        user = User(
            name="Leonor",
            password_hash="test-only",
            session_version=1,
        )
        db.add(user)
        db.commit()
        user_id = user.id

    monkeypatch.setattr(panel, "SessionLocal", testing_session)
    application = FastAPI()
    application.add_middleware(SessionMiddleware, secret_key="test-secret-that-is-long-enough")
    application.include_router(panel.router)

    @application.get("/test-login")
    def test_login(request: Request):
        request.session["user_id"] = user_id
        request.session["user_name"] = "Leonor"
        request.session["session_version"] = 1
        return {"csrf_token": get_csrf_token(request)}

    return TestClient(application), testing_session, user_id


def test_panel_requires_an_authenticated_database_session(monkeypatch):
    client, _, _ = make_client(monkeypatch)

    response = client.get("/api/communication-panel")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"


def test_panel_loads_and_searches_only_active_communication_records(monkeypatch):
    client, testing_session, user_id = make_client(monkeypatch)
    with testing_session() as db:
        db.add_all(
            [
                WorkspaceRecord(
                    module="communication",
                    title="Escolher flores",
                    description="Falar com a florista",
                    category="Ideia",
                    status="Ideia",
                    updated_by_id=user_id,
                ),
                WorkspaceRecord(
                    module="communication",
                    title="Decisão antiga",
                    category="Decisão",
                    status="Decisão",
                    is_archived=True,
                ),
                WorkspaceRecord(module="home", title="Comprar sofá"),
            ]
        )
        db.commit()
    client.get("/test-login")

    response = client.get("/api/communication-panel?q=florista")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    payload = response.json()
    assert len(payload["records"]) == 1
    assert payload["records"][0]["title"] == "Escolher flores"
    assert payload["records"][0]["category"] == "Ideia"
    assert payload["records"][0]["updated_by"] == "Leonor"


def test_quick_creation_is_csrf_protected_and_persisted_with_activity(monkeypatch):
    client, testing_session, user_id = make_client(monkeypatch)
    token = client.get("/test-login").json()["csrf_token"]

    rejected = client.post(
        "/api/communication-panel",
        data={"title": "Sem token", "category": "Nota"},
    )
    assert rejected.status_code == 403

    response = client.post(
        "/api/communication-panel",
        data={
            "csrf_token": token,
            "title": "Confirmar repertório",
            "description": "Enviar a seleção final.",
            "category": "Tarefa rápida",
            "responsible": "Vítor",
            "priority": "Alta",
            "event_date": "2026-08-01",
        },
    )

    assert response.status_code == 201
    assert response.json()["record"]["category"] == "Tarefa rápida"
    with testing_session() as db:
        record = db.scalar(
            select(WorkspaceRecord).where(WorkspaceRecord.title == "Confirmar repertório")
        )
        assert record is not None
        assert record.module == "communication"
        assert record.status == "Tarefa rápida"
        assert record.created_by_id == user_id
        assert db.scalar(select(func.count()).select_from(Activity)) == 1


def test_quick_creation_rejects_unknown_category_without_writing(monkeypatch):
    client, testing_session, _ = make_client(monkeypatch)
    token = client.get("/test-login").json()["csrf_token"]

    response = client.post(
        "/api/communication-panel",
        data={
            "csrf_token": token,
            "title": "Entrada inválida",
            "category": "Desconhecida",
        },
    )

    assert response.status_code == 422
    with testing_session() as db:
        assert db.scalar(select(func.count()).select_from(WorkspaceRecord)) == 0
