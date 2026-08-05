from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.core import User
from app.models.planning import Guest, Task, Vendor
from app.services import assistant_tools as tools
from app.services.security import hash_password


def make_session_and_user() -> tuple[Session, User]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(name="Vítor", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return db, user


def test_add_guest_creates_a_record_and_rejects_duplicates() -> None:
    db, user = make_session_and_user()

    result = tools.add_guest(db, user, {"name": "Bruna", "side": "Noiva"})
    assert result["ok"] is True
    guest = db.scalar(select(Guest).where(Guest.name == "Bruna"))
    assert guest is not None
    assert guest.side == "Noiva"
    assert guest.rsvp_status == "Pendente"

    duplicate = tools.add_guest(db, user, {"name": "Bruna"})
    assert duplicate["ok"] is False
    assert db.scalar(select(Guest).where(Guest.name == "Bruna")).id == guest.id


def test_add_guest_requires_a_name_and_ignores_invalid_enum_values() -> None:
    db, user = make_session_and_user()

    missing_name = tools.add_guest(db, user, {})
    assert missing_name["ok"] is False

    result = tools.add_guest(db, user, {"name": "Ana", "side": "not-a-real-side"})
    assert result["ok"] is True
    guest = db.scalar(select(Guest).where(Guest.name == "Ana"))
    assert guest.side == ""


def test_update_guest_changes_fields_on_an_existing_guest() -> None:
    db, user = make_session_and_user()
    tools.add_guest(db, user, {"name": "João"})

    result = tools.update_guest(
        db, user, {"name": "João", "rsvp_status": "Confirmado", "table_name": "Mesa 5"}
    )
    assert result["ok"] is True
    guest = db.scalar(select(Guest).where(Guest.name == "João"))
    assert guest.rsvp_status == "Confirmado"
    assert guest.table_name == "Mesa 5"


def test_update_guest_reports_when_guest_not_found() -> None:
    db, user = make_session_and_user()
    result = tools.update_guest(db, user, {"name": "Ninguém", "rsvp_status": "Confirmado"})
    assert result["ok"] is False


def test_remove_guest_archives_instead_of_deleting() -> None:
    db, user = make_session_and_user()
    tools.add_guest(db, user, {"name": "João"})

    result = tools.remove_guest(db, user, {"name": "João"})
    assert result["ok"] is True

    guest = db.scalar(select(Guest).where(Guest.name == "João"))
    assert guest is not None
    assert guest.is_archived is True

    # A second removal no longer finds it among the *active* guests.
    again = tools.remove_guest(db, user, {"name": "João"})
    assert again["ok"] is False


def test_add_and_update_and_remove_task() -> None:
    db, user = make_session_and_user()

    created = tools.add_task(db, user, {"title": "Reservar espaço", "priority": "Alta"})
    assert created["ok"] is True
    task = db.scalar(select(Task).where(Task.title == "Reservar espaço"))
    assert task.priority == "Alta"
    assert task.status == "Pendente"

    updated = tools.update_task_status(
        db, user, {"title": "Reservar espaço", "status": "Concluído"}
    )
    assert updated["ok"] is True
    assert db.scalar(select(Task).where(Task.title == "Reservar espaço")).status == "Concluído"

    invalid_status = tools.update_task_status(
        db, user, {"title": "Reservar espaço", "status": "Estado inventado"}
    )
    assert invalid_status["ok"] is False

    removed = tools.remove_task(db, user, {"title": "Reservar espaço"})
    assert removed["ok"] is True
    assert db.scalar(select(Task).where(Task.title == "Reservar espaço")).is_archived is True


def test_add_and_remove_vendor() -> None:
    db, user = make_session_and_user()

    created = tools.add_vendor(
        db, user, {"company": "Foto Bonita", "vendor_type": "Fotografia", "agreed_price": "1500"}
    )
    assert created["ok"] is True
    vendor = db.scalar(select(Vendor).where(Vendor.company == "Foto Bonita"))
    assert vendor.vendor_type == "Fotografia"
    assert vendor.agreed_price == 1500

    missing_type = tools.add_vendor(db, user, {"company": "Sem Tipo"})
    assert missing_type["ok"] is False

    removed = tools.remove_vendor(db, user, {"company": "Foto Bonita"})
    assert removed["ok"] is True
    assert db.scalar(select(Vendor).where(Vendor.company == "Foto Bonita")).is_archived is True


def test_fetch_webpage_rejects_non_http_and_internal_hosts() -> None:
    db, user = make_session_and_user()

    bad_scheme = tools.fetch_webpage(db, user, {"url": "ftp://example.com/file"})
    assert bad_scheme["ok"] is False

    internal = tools.fetch_webpage(db, user, {"url": "http://127.0.0.1/secret"})
    assert internal["ok"] is False

    localhost = tools.fetch_webpage(db, user, {"url": "http://localhost:8000/admin"})
    assert localhost["ok"] is False


def test_fetch_webpage_strips_html_and_bounds_length(monkeypatch) -> None:
    db, user = make_session_and_user()

    class FakeResponse:
        status_code = 200
        text = (
            "<html><head><style>body{color:red}</style></head>"
            "<body><p>Olá mundo</p></body></html>"
        )

    monkeypatch.setattr(tools.httpx, "get", lambda *args, **kwargs: FakeResponse())

    result = tools.fetch_webpage(db, user, {"url": "https://example.com"})
    assert result["ok"] is True
    assert "Olá mundo" in result["content"]
    assert "<p>" not in result["content"]
    assert "color:red" not in result["content"]
