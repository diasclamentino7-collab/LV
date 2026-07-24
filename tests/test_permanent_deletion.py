import re

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
from app.models.core import Activity, RecordTombstone, User, WorkspaceRecord
from app.services.security import hash_password


def csrf_from(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def test_global_deleted_view_uses_non_destructive_tombstones(monkeypatch) -> None:
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
        hidden_candidate = WorkspaceRecord(
            module="home",
            title="Máquina de café",
            description="Modelo escolhido",
            is_archived=True,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        recoverable = WorkspaceRecord(
            module="communication",
            title="Confirmar flores",
            is_archived=True,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add_all([hidden_candidate, recoverable])
        db.commit()
        user_id = user.id
        hidden_id = hidden_candidate.id
        recoverable_id = recoverable.id

    with TestClient(app) as client:
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

        deleted_page = client.get("/deleted")
        assert deleted_page.status_code == 200
        assert "Máquina de café" in deleted_page.text
        assert "Confirmar flores" in deleted_page.text
        assert "APAGAR" in deleted_page.text
        token = csrf_from(deleted_page)

        rejected = client.post(
            f"/home/{hidden_id}/delete-permanently?return_to=deleted",
            data={"csrf_token": "invalid", "confirmation": "APAGAR"},
            follow_redirects=False,
        )
        assert rejected.status_code == 303
        assert rejected.headers["location"] == "/deleted?error=csrf"
        with Session(engine) as db:
            assert db.scalar(select(RecordTombstone)) is None

        deleted = client.post(
            f"/home/{hidden_id}/delete-permanently?return_to=deleted",
            data={"csrf_token": token, "confirmation": "APAGAR"},
            follow_redirects=False,
        )
        assert deleted.status_code == 303
        assert deleted.headers["location"] == "/deleted?message=permanently_deleted"

        refreshed = client.get("/deleted")
        assert "Máquina de café" not in refreshed.text
        assert "Confirmar flores" in refreshed.text
        assert "Máquina de café" not in client.get("/home?archived=true").text

        crafted_restore = client.post(
            f"/home/{hidden_id}/restore",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert crafted_restore.status_code == 303

        restored = client.post(
            f"/communication/{recoverable_id}/restore?return_to=deleted",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert restored.status_code == 303
        assert restored.headers["location"] == "/deleted?message=restored"

    with Session(engine) as db:
        original = db.get(WorkspaceRecord, hidden_id)
        assert original is not None
        assert original.title == "Máquina de café"
        assert original.description == "Modelo escolhido"
        assert original.is_archived is True

        tombstone = db.scalar(
            select(RecordTombstone).where(
                RecordTombstone.entity_type == "workspace_records",
                RecordTombstone.entity_id == hidden_id,
            )
        )
        assert tombstone is not None
        assert tombstone.module == "home"
        assert tombstone.deleted_by_id == user_id
        assert '"title": "Máquina de café"' in tombstone.snapshot_json

        assert db.get(WorkspaceRecord, recoverable_id).is_archived is False
        activity = db.scalar(
            select(Activity).where(Activity.action_type == "eliminou definitivamente")
        )
        assert activity is not None
        assert activity.user_id == user_id
