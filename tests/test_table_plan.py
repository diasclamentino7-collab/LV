from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.pages as page_routes
import app.routes.table_plan as table_plan_routes
from app.core.config import get_settings
from app.db.base import Base
from app.models.core import RecordTombstone, User, WorkspaceRecord
from app.models.planning import Guest
from app.routes.pages import Field, value_for
from app.services.csrf import get_csrf_token
from app.services.table_plan import build_table_plan, sync_table_name_assignments


def make_testing_session() -> sessionmaker:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    return factory


def make_client(monkeypatch) -> tuple[TestClient, sessionmaker, int]:
    testing_session = make_testing_session()
    with testing_session() as db:
        user = User(name="Leonor", password_hash="test-only", session_version=1)
        db.add(user)
        db.commit()
        user_id = user.id

    monkeypatch.setattr(table_plan_routes, "SessionLocal", testing_session)
    monkeypatch.setattr(page_routes, "SessionLocal", testing_session)
    monkeypatch.setattr(templating_module, "SessionLocal", testing_session)
    application = FastAPI()
    application.add_middleware(SessionMiddleware, secret_key="test-secret-that-is-long-enough")
    application.mount(
        "/static",
        StaticFiles(directory=get_settings().static_path),
        name="static",
    )

    @application.get("/test-login")
    def test_login(request: Request):
        request.session["user_id"] = user_id
        request.session["user_name"] = "Leonor"
        request.session["session_version"] = 1
        return {"csrf_token": get_csrf_token(request)}

    application.include_router(table_plan_routes.router)
    application.include_router(page_routes.router)

    return TestClient(application), testing_session, user_id


def test_table_plan_groups_active_guests_without_duplicate_table_spellings():
    testing_session = make_testing_session()
    with testing_session() as db:
        db.add(
            WorkspaceRecord(
                module="table-plan",
                title="Mesa Aurora",
                responsible="2",
                category="Oval",
                location="Janela",
                status="Em organização",
                description="Família próxima",
            )
        )
        db.add_all(
            [
                Guest(name="Ana", table_name="Mesa Aurora", rsvp_status="Confirmado"),
                Guest(name="Bruno", table_name=" mesa  aurora ", side="Noivo"),
                Guest(name="Carla", table_name="MESA AURORA", age_group="Criança"),
                Guest(name="Dinis", table_name=""),
                Guest(name="Arquivado", table_name="Mesa Aurora", is_archived=True),
            ]
        )
        db.commit()

        plan = build_table_plan(db)

    assert plan["table_options"] == ["Mesa Aurora"]
    table = plan["tables"][0]
    assert table["name"] == "Mesa Aurora"
    assert table["capacity"] == 2
    assert table["occupancy"] == 3
    assert table["is_over_capacity"] is True
    assert table["shape"] == "Oval"
    assert table["zone"] == "Janela"
    assert [guest["name"] for guest in table["guests"]] == ["Ana", "Bruno", "Carla"]
    assert {
        "id",
        "name",
        "side",
        "age_group",
        "rsvp_status",
        "updated_at",
    }.issubset(table["guests"][0])
    assert [guest["name"] for guest in plan["unassigned_guests"]] == ["Dinis"]
    assert plan["stats"]["assigned_guests"] == 3
    assert plan["stats"]["unassigned_guests"] == 1


def test_table_plan_builds_synthetic_tables_and_safe_default_capacities():
    testing_session = make_testing_session()
    with testing_session() as db:
        db.add(
            WorkspaceRecord(
                module="table-plan",
                title="Mesa Jardim",
                responsible="valor antigo inválido",
            )
        )
        db.add(Guest(name="Jardim", table_name="Mesa Jardim"))
        db.add_all([Guest(name=f"Convidado {index}", table_name="Mesa Sol") for index in range(9)])
        db.commit()

        plan = build_table_plan(db)

    tables = {table["name"]: table for table in plan["tables"]}
    assert tables["Mesa Jardim"]["capacity"] == 8
    assert tables["Mesa Jardim"]["is_synthetic"] is False
    assert tables["Mesa Sol"]["capacity"] == 9
    assert tables["Mesa Sol"]["id"] is None
    assert tables["Mesa Sol"]["is_synthetic"] is True
    assert set(plan["table_options"]) == {"Mesa Jardim", "Mesa Sol"}


def test_table_plan_excludes_archived_and_tombstoned_definitions_and_guests():
    testing_session = make_testing_session()
    with testing_session() as db:
        hidden_guest = Guest(name="Eliminado", table_name="Mesa Oculta")
        hidden_table = WorkspaceRecord(module="table-plan", title="Mesa Eliminada")
        db.add_all(
            [
                hidden_guest,
                hidden_table,
                Guest(name="Ativo", table_name="Mesa Visível"),
                Guest(name="Arquivado", table_name="Mesa Arquivada", is_archived=True),
                WorkspaceRecord(
                    module="table-plan",
                    title="Mesa Arquivada",
                    is_archived=True,
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                RecordTombstone(
                    entity_type="guests",
                    entity_id=hidden_guest.id,
                    module="guests",
                    snapshot_json="{}",
                ),
                RecordTombstone(
                    entity_type="workspace_records",
                    entity_id=hidden_table.id,
                    module="table-plan",
                    snapshot_json="{}",
                ),
            ]
        )
        db.commit()

        plan = build_table_plan(db)

    assert plan["table_options"] == ["Mesa Visível"]
    assert [guest["name"] for guest in plan["tables"][0]["guests"]] == ["Ativo"]


def test_table_plan_page_requires_authentication(monkeypatch):
    client, _, _ = make_client(monkeypatch)

    response = client.get("/table-plan", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_archived_table_plan_keeps_generic_recovery_view(monkeypatch):
    client, testing_session, _ = make_client(monkeypatch)
    with testing_session() as db:
        db.add_all(
            [
                WorkspaceRecord(module="table-plan", title="Mesa Ativa"),
                WorkspaceRecord(
                    module="table-plan",
                    title="Mesa Arquivada",
                    is_archived=True,
                ),
            ]
        )
        db.commit()
    client.get("/test-login")

    response = client.get("/table-plan?archived=true")

    assert response.status_code == 200
    assert "Mesa Arquivada" in response.text
    assert "Mesa Ativa" not in response.text


def test_table_rename_updates_active_and_archived_assignments_atomically(monkeypatch):
    client, testing_session, user_id = make_client(monkeypatch)
    with testing_session() as db:
        table = WorkspaceRecord(
            module="table-plan",
            title="Mesa Antiga",
            responsible="8",
        )
        active_guest = Guest(name="Ativo", table_name=" mesa antiga ")
        archived_guest = Guest(
            name="Arquivado",
            table_name="MESA ANTIGA",
            is_archived=True,
        )
        deleted_guest = Guest(name="Eliminado", table_name="Mesa Antiga")
        db.add_all([table, active_guest, archived_guest, deleted_guest])
        db.flush()
        db.add(
            RecordTombstone(
                entity_type="guests",
                entity_id=deleted_guest.id,
                module="guests",
                snapshot_json="{}",
            )
        )
        db.commit()
        table_id = table.id
        active_id = active_guest.id
        archived_id = archived_guest.id
        deleted_id = deleted_guest.id
    token = client.get("/test-login").json()["csrf_token"]

    response = client.post(
        f"/table-plan/{table_id}/edit",
        data={
            "csrf_token": token,
            "title": "Mesa Nova",
            "responsible": "12.00",
            "category": "Redonda",
            "location": "Centro",
            "status": "Em organização",
            "description": "",
            "comments": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/table-plan?message=updated"
    with testing_session() as db:
        changed_table = db.get(WorkspaceRecord, table_id)
        active = db.get(Guest, active_id)
        archived = db.get(Guest, archived_id)
        deleted = db.get(Guest, deleted_id)
        assert changed_table.title == "Mesa Nova"
        assert changed_table.responsible == "12"
        assert active.table_name == "Mesa Nova"
        assert archived.table_name == "Mesa Nova"
        assert active.updated_by_id == user_id
        assert archived.updated_by_id == user_id
        assert deleted.table_name == "Mesa Antiga"


def test_invalid_capacity_rolls_back_table_and_guest_rename(monkeypatch):
    client, testing_session, _ = make_client(monkeypatch)
    with testing_session() as db:
        table = WorkspaceRecord(
            module="table-plan",
            title="Mesa Segura",
            responsible="8",
        )
        guest = Guest(name="Convidado", table_name="Mesa Segura")
        db.add_all([table, guest])
        db.commit()
        table_id = table.id
        guest_id = guest.id
    token = client.get("/test-login").json()["csrf_token"]

    response = client.post(
        f"/table-plan/{table_id}/edit",
        data={
            "csrf_token": token,
            "title": "Nome que não deve ficar",
            "responsible": "1e1000000",
            "category": "Redonda",
            "location": "",
            "status": "Pendente",
            "description": "",
            "comments": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("?error=invalid")
    with testing_session() as db:
        assert db.get(WorkspaceRecord, table_id).title == "Mesa Segura"
        assert db.get(Guest, guest_id).table_name == "Mesa Segura"


def test_capacity_form_is_integer_without_currency_affix(monkeypatch):
    client, testing_session, _ = make_client(monkeypatch)
    with testing_session() as db:
        table = WorkspaceRecord(module="table-plan", title="Mesa", responsible="25.00")
        db.add(table)
        db.commit()
    client.get("/test-login")

    response = client.get("/table-plan/new")

    assert response.status_code == 200
    assert 'name="responsible" type="number"' in response.text
    assert 'step="1" min="1" inputmode="numeric"' in response.text
    with testing_session() as db:
        assert build_table_plan(db)["tables"][0]["capacity"] == 8


def test_integer_field_accepts_only_safe_positive_whole_capacities():
    field = Field("responsible", "Lugares", "integer")

    assert value_for(field, "") == ""
    assert value_for(field, "12.00") == "12"
    for invalid in (
        "texto",
        "0",
        "12.5",
        "101",
        "NaN",
        "Infinity",
        "1e1000000",
    ):
        with pytest.raises(ValueError):
            value_for(field, invalid)


def test_unchanged_table_name_does_not_touch_guest_authorship_or_timestamp():
    testing_session = make_testing_session()
    original_timestamp = datetime(2026, 7, 14, 18, 30, tzinfo=UTC)
    with testing_session() as db:
        original_author = User(name="Vítor", password_hash="test-only")
        editor = User(name="Leonor", password_hash="test-only")
        db.add_all([original_author, editor])
        db.flush()
        guest = Guest(
            name="Ana",
            table_name="Mesa Aurora",
            updated_by_id=original_author.id,
            updated_at=original_timestamp,
        )
        db.add(guest)
        db.commit()
        guest_id = guest.id

        changed = sync_table_name_assignments(
            db,
            "Mesa Aurora",
            "  Mesa   Aurora  ",
            user_id=editor.id,
        )
        db.commit()
        db.refresh(guest)

        assert changed == 0
        assert guest.id == guest_id
        assert guest.table_name == "Mesa Aurora"
        assert guest.updated_by_id == original_author.id
        stored_timestamp = guest.updated_at
        if stored_timestamp.tzinfo is None:
            stored_timestamp = stored_timestamp.replace(tzinfo=UTC)
        assert stored_timestamp == original_timestamp


def test_create_rejects_active_logical_duplicate_table_name(monkeypatch):
    client, testing_session, _ = make_client(monkeypatch)
    with testing_session() as db:
        db.add(WorkspaceRecord(module="table-plan", title="Mesa Aurora"))
        db.commit()
    token = client.get("/test-login").json()["csrf_token"]

    response = client.post(
        "/table-plan/new",
        data={
            "csrf_token": token,
            "title": "  mesa   AURORA ",
            "responsible": "8",
            "category": "Redonda",
            "location": "",
            "status": "A planear",
            "description": "",
            "comments": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/table-plan/new?error=duplicate"
    with testing_session() as db:
        definitions = db.scalars(
            select(WorkspaceRecord).where(WorkspaceRecord.module == "table-plan")
        ).all()
        assert [definition.title for definition in definitions] == ["Mesa Aurora"]


def test_rename_collision_rolls_back_definition_and_guest_atomically(monkeypatch):
    client, testing_session, original_author_id = make_client(monkeypatch)
    original_timestamp = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    with testing_session() as db:
        source = WorkspaceRecord(module="table-plan", title="Mesa Um", responsible="8")
        target = WorkspaceRecord(module="table-plan", title="Mesa Dois", responsible="8")
        guest = Guest(
            name="Ana",
            table_name="Mesa Um",
            updated_by_id=original_author_id,
            updated_at=original_timestamp,
        )
        db.add_all([source, target, guest])
        db.commit()
        source_id = source.id
        guest_id = guest.id
    token = client.get("/test-login").json()["csrf_token"]

    response = client.post(
        f"/table-plan/{source_id}/edit",
        data={
            "csrf_token": token,
            "title": " mesa   DOIS ",
            "responsible": "12",
            "category": "Oval",
            "location": "Janela",
            "status": "Em organização",
            "description": "Não deve persistir",
            "comments": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (f"/table-plan/{source_id}/edit?error=duplicate")
    with testing_session() as db:
        unchanged_table = db.get(WorkspaceRecord, source_id)
        unchanged_guest = db.get(Guest, guest_id)
        assert unchanged_table.title == "Mesa Um"
        assert unchanged_table.responsible == "8"
        assert unchanged_table.description == ""
        assert unchanged_guest.table_name == "Mesa Um"
        assert unchanged_guest.updated_by_id == original_author_id
        stored_timestamp = unchanged_guest.updated_at
        if stored_timestamp.tzinfo is None:
            stored_timestamp = stored_timestamp.replace(tzinfo=UTC)
        assert stored_timestamp == original_timestamp


def test_name_can_be_reused_after_archive_or_tombstone(monkeypatch):
    client, testing_session, _ = make_client(monkeypatch)
    with testing_session() as db:
        archived = WorkspaceRecord(
            module="table-plan",
            title="Mesa Livre",
            is_archived=True,
        )
        tombstoned = WorkspaceRecord(
            module="table-plan",
            title=" mesa livre ",
            is_archived=False,
        )
        db.add_all([archived, tombstoned])
        db.flush()
        db.add(
            RecordTombstone(
                entity_type="workspace_records",
                entity_id=tombstoned.id,
                module="table-plan",
                snapshot_json="{}",
            )
        )
        db.commit()
    token = client.get("/test-login").json()["csrf_token"]

    response = client.post(
        "/table-plan/new",
        data={
            "csrf_token": token,
            "title": "MESA LIVRE",
            "responsible": "8",
            "category": "Redonda",
            "location": "Centro",
            "status": "A planear",
            "description": "Nova definição ativa",
            "comments": "",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/table-plan?message=created"
    with testing_session() as db:
        definitions = db.scalars(
            select(WorkspaceRecord)
            .where(WorkspaceRecord.module == "table-plan")
            .order_by(WorkspaceRecord.id)
        ).all()
        assert len(definitions) == 3
        assert definitions[-1].title == "MESA LIVRE"
        assert definitions[-1].is_archived is False


def test_historical_duplicate_definitions_are_exposed_for_manual_resolution():
    testing_session = make_testing_session()
    with testing_session() as db:
        first = WorkspaceRecord(
            module="table-plan",
            title="Mesa Histórica",
            responsible="8",
        )
        second = WorkspaceRecord(
            module="table-plan",
            title=" mesa   HISTÓRICA ",
            responsible="10",
            category="Oval",
            location="Janela",
        )
        db.add_all([first, second])
        db.commit()
        definition_ids = {first.id, second.id}

        plan = build_table_plan(db)

    assert len(plan["tables"]) == 1
    table = plan["tables"][0]
    assert set(table["definition_ids"]) == definition_ids
    assert table["definition_count"] == 2
    assert len(table["duplicate_definitions"]) == 1
    duplicate = table["duplicate_definitions"][0]
    assert duplicate["id"] in definition_ids
    assert duplicate["edit_url"] == f"/table-plan/{duplicate['id']}/edit"
    assert duplicate["name"].casefold() == "mesa histórica"
    assert plan["stats"]["duplicate_definition_count"] == 1
    assert plan["table_options"] == ["Mesa Histórica"]
