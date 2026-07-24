import re
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.auth as auth_routes
import app.routes.pages as page_routes
from app.db.base import Base
from app.main import app
from app.models.core import ProjectSettings, User
from app.models.planning import BudgetCategory, Expense
from app.services.security import hash_password


def csrf_from(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def test_budget_view_uses_real_totals_and_preserves_archived_categories(
    monkeypatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(page_routes, "SessionLocal", test_session)
    monkeypatch.setattr(auth_routes, "SessionLocal", test_session)
    monkeypatch.setattr(templating_module, "SessionLocal", test_session)

    with Session(engine) as db:
        user = User(name="Vítor", password_hash=hash_password("password123"))
        db.add(user)
        db.flush()
        db.add(
            ProjectSettings(
                id=1,
                total_budget="5000.00",
                currency="EUR",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        reception = BudgetCategory(
            name="Receção",
            planned_limit=Decimal("2000.00"),
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        music = BudgetCategory(
            name="Música",
            planned_limit=Decimal("1000.00"),
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add_all([reception, music])
        db.flush()
        db.add_all(
            [
                Expense(
                    category_id=reception.id,
                    description="Espaço",
                    amount=Decimal("750.25"),
                    expense_date=date(2026, 7, 24),
                    status="Confirmada",
                    created_by_id=user.id,
                    updated_by_id=user.id,
                ),
                Expense(
                    category_id=reception.id,
                    description="Opção cancelada",
                    amount=Decimal("99.00"),
                    expense_date=date(2026, 7, 24),
                    status="Cancelada",
                    created_by_id=user.id,
                    updated_by_id=user.id,
                ),
            ]
        )
        db.commit()
        user_id = user.id

    with TestClient(app) as client:
        unauthenticated = client.get("/api/budget-summary")
        assert unauthenticated.status_code == 401
        assert unauthenticated.headers["cache-control"] == "no-store"

        login_page = client.get("/login")
        login = client.post(
            "/login",
            data={
                "user_id": user_id,
                "password": "password123",
                "csrf_token": csrf_from(login_page),
            },
            follow_redirects=False,
        )
        assert login.status_code == 303

        page = client.get("/budget")
        assert page.status_code == 200
        assert "data-budget-live" in page.text
        assert "Despesas atuais" in page.text
        assert "Receção" in page.text
        assert "budget.css" in page.text
        assert "budget.js" in page.text

        response = client.get("/api/budget-summary")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store, max-age=0"
        payload = response.json()
        assert payload["summary"]["total"] == "5000.00"
        assert payload["summary"]["expenses"] == "750.25"
        assert payload["summary"]["remaining"] == "4249.75"
        assert payload["summary"]["allocated"] == "3000.00"
        assert payload["summary"]["percentage"] == "15.01"
        assert payload["categories"][0]["name"] == "Receção"
        assert payload["categories"][0]["usage_percentage"] == "37.51"
        assert payload["categories"][0]["share_percentage"] == "100.00"

        new_page = client.get("/budget/new")
        created = client.post(
            "/budget/new",
            data={
                "name": "Flores",
                "planned_limit": "600.00",
                "csrf_token": csrf_from(new_page),
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        assert created.headers["location"] == "/budget?message=created"
        redirected_page = client.get(created.headers["location"])
        assert "Flores" in redirected_page.text

        refreshed = client.get("/api/budget-summary").json()
        flowers = next(
            category for category in refreshed["categories"] if category["name"] == "Flores"
        )
        assert refreshed["summary"]["allocated"] == "3600.00"

        archived = client.post(
            f"/budget/{flowers['id']}/archive",
            data={"csrf_token": csrf_from(redirected_page)},
            follow_redirects=False,
        )
        assert archived.status_code == 303
        assert all(
            category["id"] != flowers["id"]
            for category in client.get("/api/budget-summary").json()["categories"]
        )

    with Session(engine) as db:
        preserved = db.scalar(select(BudgetCategory).where(BudgetCategory.name == "Flores"))
        assert preserved is not None
        assert preserved.is_archived is True
        assert preserved.planned_limit == Decimal("600.00")
