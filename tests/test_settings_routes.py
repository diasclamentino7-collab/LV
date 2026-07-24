import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.auth as auth_routes
import app.routes.pages as page_routes
import app.routes.web as web_routes
from app.db.base import Base
from app.main import app
from app.models.core import Activity, ProjectSettings, User
from app.models.planning import BudgetCategory, Task
from app.services.security import hash_password


def test_settings_save_is_audited_and_stale_forms_are_rejected(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(web_routes, "SessionLocal", test_session)
    monkeypatch.setattr(auth_routes, "SessionLocal", test_session)
    monkeypatch.setattr(page_routes, "SessionLocal", test_session)
    monkeypatch.setattr(templating_module, "SessionLocal", test_session)

    with Session(engine) as db:
        user = User(name="Vítor", password_hash=hash_password("password123"))
        db.add(user)
        db.flush()
        db.add(
            ProjectSettings(
                id=1,
                project_name="LV – Wedding Planner",
                language="pt-PT",
                settings_version=1,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.add(
            BudgetCategory(
                name="Espaço",
                planned_limit=1000,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.commit()
        user_id = user.id

    with TestClient(app) as client:
        login_page = client.get("/login")
        csrf_token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            login_page.text,
        ).group(1)
        login = client.post(
            "/login",
            data={
                "user_id": user_id,
                "password": "password123",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert login.status_code == 303

        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200
        assert "Próximas tarefas" in dashboard.text
        assert 'aria-controls="main-navigation"' in dashboard.text

        page = client.get("/settings")
        assert page.status_code == 200
        assert "Identidade do casamento" in page.text
        assert "Exportar dados" in page.text
        csrf_token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            page.text,
        ).group(1)

        rejected = client.post(
            "/settings/identity",
            data={
                "settings_version": "1",
                "project_name": "Sem token",
                "partner_one_name": "Leonor",
                "partner_two_name": "Vítor",
                "logo_path": "",
            },
            follow_redirects=False,
        )
        assert "error=csrf" in rejected.headers["location"]

        saved = client.post(
            "/settings/identity",
            data={
                "csrf_token": csrf_token,
                "settings_version": "1",
                "project_name": "O nosso casamento",
                "partner_one_name": "Leonor",
                "partner_two_name": "Vítor",
                "logo_path": "",
            },
            follow_redirects=False,
        )
        assert saved.status_code == 303
        assert saved.headers["location"].startswith("/settings?saved=identity")

        conflict = client.post(
            "/settings/identity",
            data={
                "csrf_token": csrf_token,
                "settings_version": "1",
                "project_name": "Valor antigo",
                "partner_one_name": "Leonor",
                "partner_two_name": "Vítor",
                "logo_path": "",
            },
            follow_redirects=False,
        )
        assert conflict.status_code == 303
        assert "error=conflict" in conflict.headers["location"]

        currency_rejected = client.post(
            "/settings/finance",
            data={
                "csrf_token": csrf_token,
                "settings_version": "2",
                "total_budget": "25000",
                "currency": "USD",
                "budget_alert_percent": "80",
            },
            follow_redirects=False,
        )
        assert "error=currency_confirmation" in currency_rejected.headers["location"]

        currency_saved = client.post(
            "/settings/finance",
            data={
                "csrf_token": csrf_token,
                "settings_version": "2",
                "total_budget": "25000",
                "currency": "USD",
                "budget_alert_percent": "80",
                "confirm_currency_change": "true",
            },
            follow_redirects=False,
        )
        assert currency_saved.headers["location"].startswith("/settings?saved=finance")

        history = client.get(f"/activity?module=settings&user_id={user_id}")
        assert history.status_code == 200
        assert "Histórico de atividade" in history.text
        assert "Vítor" in history.text
        assert "atualizou as configurações de finance" in history.text

        exported = client.get("/settings/export")
        assert exported.status_code == 200
        assert "attachment" in exported.headers["content-disposition"]
        assert "password_hash" not in exported.json()["tables"]["users"][0]

        manifest = client.get("/manifest.webmanifest")
        assert manifest.status_code == 200
        assert manifest.json()["name"] == "LV – Wedding Planner"
        assert manifest.json()["id"] == "/dashboard"
        assert manifest.json()["shortcuts"][1]["url"] == "/budget"

        task_saved = client.post(
            "/checklist/new",
            data={
                "csrf_token": csrf_token,
                "title": "Confirmar flores",
                "priority": "Alta",
                "status": "Pendente",
            },
            follow_redirects=False,
        )
        assert task_saved.status_code == 303

    with Session(engine) as db:
        settings = db.get(ProjectSettings, 1)
        activity_count = db.scalar(
            select(func.count()).select_from(Activity).where(Activity.module == "settings")
        )
        task_count = db.scalar(select(func.count()).select_from(Task))

    assert settings is not None
    assert settings.project_name == "O nosso casamento"
    assert settings.currency == "USD"
    assert settings.settings_version == 3
    assert activity_count == 2
    assert task_count == 1
