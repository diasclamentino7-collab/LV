import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.auth as auth_routes
import app.routes.exports as export_routes
from app.db.base import Base
from app.main import app
from app.models.core import ProjectSettings, User, WorkspaceRecord
from app.models.planning import BudgetCategory, Task
from app.services.pdf_export import build_full_pdf
from app.services.security import hash_password


def memory_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_full_pdf_is_valid_paginated_and_never_contains_password_hashes() -> None:
    engine, _ = memory_database()
    with Session(engine) as db:
        db.add(User(name="Leonor", password_hash="never-export-this-secret"))
        db.add(
            ProjectSettings(
                project_name="O nosso casamento",
                currency="EUR",
                total_budget="25000",
            )
        )
        db.add_all(
            [
                Task(
                    title=f"Tarefa real {number}",
                    description=(
                        "Descrição suficientemente longa para comprovar a paginação "
                        "automática e preservar os dados reais do planeamento."
                    ),
                    status="Pendente",
                )
                for number in range(70)
            ]
        )
        db.commit()

        pdf = build_full_pdf(db)

    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in pdf
    assert len(re.findall(rb"/Type /Page\b", pdf)) > 1
    assert b"Tarefa real 69" in pdf
    assert b"never-export-this-secret" not in pdf
    assert b"password_hash" not in pdf
    assert b"session_version" not in pdf


def test_authenticated_pdf_routes_export_full_communication_and_budget_data(
    monkeypatch,
) -> None:
    engine, test_session = memory_database()
    monkeypatch.setattr(export_routes, "SessionLocal", test_session)
    monkeypatch.setattr(auth_routes, "SessionLocal", test_session)
    monkeypatch.setattr(templating_module, "SessionLocal", test_session)

    with Session(engine) as db:
        user = User(name="Vitor", password_hash=hash_password("password123"))
        db.add(user)
        db.flush()
        db.add(
            ProjectSettings(
                project_name="LV - Teste",
                currency="EUR",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.add(
            WorkspaceRecord(
                module="communication",
                title="Escolher flores",
                status="Ideia",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.add(
            BudgetCategory(
                name="Fotografia",
                planned_limit="1750.50",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.commit()
        user_id = user.id

    with TestClient(app) as client:
        unauthenticated = client.get("/settings/export.pdf", follow_redirects=False)
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/login"

        login_page = client.get("/login")
        csrf_token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            login_page.text,
        ).group(1)
        logged_in = client.post(
            "/login",
            data={
                "user_id": user_id,
                "password": "password123",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert logged_in.status_code == 303

        full_export = client.get("/settings/export.pdf")
        assert full_export.status_code == 200
        assert full_export.headers["content-type"] == "application/pdf"
        assert "attachment" in full_export.headers["content-disposition"]
        assert full_export.content.startswith(b"%PDF-1.4")
        assert b"Escolher flores" in full_export.content

        communication = client.get("/exports/communication.pdf")
        assert communication.status_code == 200
        assert communication.headers["content-type"] == "application/pdf"
        assert b"Escolher flores" in communication.content
        assert communication.headers["cache-control"].startswith("private, no-store")

        budget = client.get("/exports/budget.pdf")
        assert budget.status_code == 200
        assert b"Fotografia" in budget.content
        assert b"1 750,50 \\200" in budget.content

        archived = client.get("/exports/budget.pdf?archived=true")
        assert archived.status_code == 200
        assert b"Fotografia" not in archived.content
