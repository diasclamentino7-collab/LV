from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.auth as auth_routes
import app.routes.pages as page_routes
from app.core.config import PROJECT_ROOT
from app.db.base import Base
from app.main import app
from app.models.core import ProjectSettings, User, WorkspaceRecord
from app.models.planning import BudgetCategory, Vendor
from app.routes.pages import MODULES
from app.services.security import hash_password


def csrf_from(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def form_test_session(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    for module in (auth_routes, page_routes, templating_module):
        monkeypatch.setattr(module, "SessionLocal", testing_session)

    with testing_session() as db:
        user = User(name="Vítor", password_hash=hash_password("password123"))
        db.add(user)
        db.flush()
        db.add(ProjectSettings(id=1, created_by_id=user.id, updated_by_id=user.id))
        category = BudgetCategory(
            name="Categoria base",
            planned_limit=1000,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        vendor = Vendor(
            vendor_type="Espaço",
            company="Fornecedor base",
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add_all([category, vendor])
        db.commit()
        return testing_session, user.id, category.id, vendor.id


def login(client: TestClient, user_id: int) -> None:
    response = client.get("/login")
    result = client.post(
        "/login",
        data={
            "user_id": user_id,
            "password": "password123",
            "csrf_token": csrf_from(response),
        },
        follow_redirects=False,
    )
    assert result.status_code == 303


def field_value(field, slug: str, category_id: int, vendor_id: int) -> str:
    if field.kind == "category":
        return str(category_id)
    if field.kind == "vendor":
        return str(vendor_id)
    if field.kind == "number":
        return "25.00"
    if field.kind == "integer":
        return "8"
    if field.kind == "date":
        return "2026-08-03"
    if field.kind == "datetime-local":
        return "2026-08-03T18:30"
    if field.kind == "select":
        return next((option for option in field.options if option), "")
    if field.name == "email":
        return f"{slug}@example.pt"
    if field.name in {"website", "source_url"}:
        return "https://example.pt"
    return f"Teste {slug} {field.name}"


def test_every_canonical_module_keeps_create_and_edit_workflows(monkeypatch):
    testing_session, user_id, category_id, vendor_id = form_test_session(monkeypatch)
    canonical_modules = {spec.slug: spec for spec in MODULES.values() if spec.slug != "settings"}

    with TestClient(app) as client:
        login(client, user_id)
        for slug, spec in canonical_modules.items():
            new_page = client.get(f"/{slug}/new")
            assert new_page.status_code == 200, slug
            assert 'data-form-mode="create"' in new_page.text, slug
            assert "/static/css/form-workspace.css" in new_page.text, slug
            assert "/static/js/form-workspace.js" in new_page.text, slug
            assert 'name="csrf_token"' in new_page.text, slug
            for field in spec.fields:
                assert f'name="{field.name}"' in new_page.text, (slug, field.name)

            payload = {
                field.name: field_value(field, slug, category_id, vendor_id)
                for field in spec.fields
            }
            payload["csrf_token"] = csrf_from(new_page)
            created = client.post(f"/{slug}/new", data=payload, follow_redirects=False)
            assert created.status_code == 303, slug
            assert created.headers["location"].startswith(f"/{slug}?message=created"), slug

            with testing_session() as db:
                model = spec.model or WorkspaceRecord
                statement = select(model)
                if spec.model is None:
                    statement = statement.where(WorkspaceRecord.module == slug)
                record = db.scalars(statement.order_by(model.id.desc())).first()
                assert record is not None, slug
                record_id = record.id

            edit_page = client.get(f"/{slug}/{record_id}/edit")
            assert edit_page.status_code == 200, slug
            assert 'data-form-mode="edit"' in edit_page.text, slug
            assert "Última atualização" in edit_page.text, slug
            assert "Tudo guardado" in edit_page.text, slug


def test_form_workspace_has_keyboard_safety_without_background_business_writes():
    javascript = (PROJECT_ROOT / "app/static/js/form-workspace.js").read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "app/static/css/form-workspace.css").read_text(encoding="utf-8")
    template = (PROJECT_ROOT / "app/templates/module_form.html").read_text(encoding="utf-8")

    assert "event.ctrlKey || event.metaKey" in javascript
    assert "form.requestSubmit" in javascript
    assert "beforeunload" in javascript
    assert 'form.removeAttribute("data-motion-dirty")' in javascript
    assert "window.confirm" in javascript
    assert "form.checkValidity()" in javascript
    assert "resizeTextarea" in javascript
    assert "control.required" in javascript
    assert "updateCharacterCount" in javascript
    assert 'form.setAttribute("aria-busy", "true")' in javascript
    assert "fetch(" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "position: sticky" in stylesheet
    assert "prefers-reduced-motion: reduce" in stylesheet
    assert "@media (max-width: 560px)" in stylesheet
    assert "data-required=" in template
    assert "data-form-character-count" in template
    assert 'aria-busy="false"' in template
    assert "data-form-submit-label" in template
