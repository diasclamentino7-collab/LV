from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.core import User, WorkspaceRecord
from app.models.moodboard import MoodboardItem
from app.models.planning import BudgetCategory, Expense, Guest, LegalDocument, Payment, Task, Vendor
from app.services import assistant_tools as tools
from app.services.record_deletion import is_tombstoned
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

    updated = tools.update_task(
        db, user, {"title": "Reservar espaço", "status": "Concluído", "assignee": "Leonor"}
    )
    assert updated["ok"] is True
    task = db.scalar(select(Task).where(Task.title == "Reservar espaço"))
    assert task.status == "Concluído"
    assert task.assignee == "Leonor"

    invalid_status = tools.update_task(
        db, user, {"title": "Reservar espaço", "status": "Estado inventado"}
    )
    assert invalid_status["ok"] is False

    removed = tools.remove_task(db, user, {"title": "Reservar espaço"})
    assert removed["ok"] is True
    assert db.scalar(select(Task).where(Task.title == "Reservar espaço")).is_archived is True


def test_update_vendor_changes_fields() -> None:
    db, user = make_session_and_user()
    tools.add_vendor(db, user, {"company": "Foto Bonita", "vendor_type": "Fotografia"})

    result = tools.update_vendor(
        db, user, {"company": "Foto Bonita", "phone": "912345678", "agreed_price": "2000"}
    )
    assert result["ok"] is True
    vendor = db.scalar(select(Vendor).where(Vendor.company == "Foto Bonita"))
    assert vendor.phone == "912345678"
    assert vendor.agreed_price == 2000

    missing = tools.update_vendor(db, user, {"company": "Não Existe"})
    assert missing["ok"] is False


def test_legal_document_add_update_remove() -> None:
    db, user = make_session_and_user()

    created = tools.add_legal_document(db, user, {"title": "Certidão de nascimento"})
    assert created["ok"] is True
    document = db.scalar(
        select(LegalDocument).where(LegalDocument.title == "Certidão de nascimento")
    )
    assert document.status == "Pendente"

    updated = tools.update_legal_document(
        db, user, {"title": "Certidão de nascimento", "status": "Concluído", "responsible": "Vítor"}
    )
    assert updated["ok"] is True
    document = db.scalar(
        select(LegalDocument).where(LegalDocument.title == "Certidão de nascimento")
    )
    assert document.status == "Concluído"
    assert document.responsible == "Vítor"

    removed = tools.remove_legal_document(db, user, {"title": "Certidão de nascimento"})
    assert removed["ok"] is True
    assert (
        db.scalar(
            select(LegalDocument).where(LegalDocument.title == "Certidão de nascimento")
        ).is_archived
        is True
    )


def test_budget_category_add_update_remove_and_duplicate_rejected() -> None:
    db, user = make_session_and_user()

    created = tools.add_budget_category(db, user, {"name": "Catering", "planned_limit": "5000"})
    assert created["ok"] is True

    duplicate = tools.add_budget_category(db, user, {"name": "Catering"})
    assert duplicate["ok"] is False

    updated = tools.update_budget_category(
        db, user, {"name": "Catering", "new_name": "Catering e Bar", "planned_limit": "6000"}
    )
    assert updated["ok"] is True
    category = db.scalar(select(BudgetCategory).where(BudgetCategory.name == "Catering e Bar"))
    assert category is not None
    assert category.planned_limit == 6000

    removed = tools.remove_budget_category(db, user, {"name": "Catering e Bar"})
    assert removed["ok"] is True
    assert (
        db.scalar(select(BudgetCategory).where(BudgetCategory.name == "Catering e Bar")).is_archived
        is True
    )


def test_expense_requires_an_existing_category_and_can_be_updated_and_removed() -> None:
    db, user = make_session_and_user()

    missing_category = tools.add_expense(
        db, user, {"description": "Flores", "category": "Não Existe", "amount": "100"}
    )
    assert missing_category["ok"] is False

    tools.add_budget_category(db, user, {"name": "Decoração"})
    created = tools.add_expense(
        db, user, {"description": "Flores", "category": "Decoração", "amount": "250"}
    )
    assert created["ok"] is True
    expense = db.scalar(select(Expense).where(Expense.description == "Flores"))
    assert expense.amount == 250
    assert expense.status == "Pendente"

    updated = tools.update_expense(
        db, user, {"description": "Flores", "status": "Confirmada", "amount": "300"}
    )
    assert updated["ok"] is True
    expense = db.scalar(select(Expense).where(Expense.description == "Flores"))
    assert expense.status == "Confirmada"
    assert expense.amount == 300

    removed = tools.remove_expense(db, user, {"description": "Flores"})
    assert removed["ok"] is True
    assert db.scalar(select(Expense).where(Expense.description == "Flores")).is_archived is True


def test_payment_requires_an_existing_category_and_can_be_updated_and_removed() -> None:
    db, user = make_session_and_user()
    tools.add_budget_category(db, user, {"name": "Fotografia"})

    created = tools.add_payment(
        db, user, {"category": "Fotografia", "amount": "500", "reference": "sinal-foto"}
    )
    assert created["ok"] is True
    payment = db.scalar(select(Payment).where(Payment.reference == "sinal-foto"))
    assert payment.amount == 500
    assert payment.status == "Pago"

    updated = tools.update_payment(
        db, user, {"reference": "sinal-foto", "status": "Pendente", "amount": "550"}
    )
    assert updated["ok"] is True
    payment = db.scalar(select(Payment).where(Payment.reference == "sinal-foto"))
    assert payment.status == "Pendente"
    assert payment.amount == 550

    removed = tools.remove_payment(db, user, {"reference": "sinal-foto"})
    assert removed["ok"] is True
    assert db.scalar(select(Payment).where(Payment.reference == "sinal-foto")).is_archived is True


def test_communication_note_add_update_remove() -> None:
    db, user = make_session_and_user()

    created = tools.add_communication_note(
        db, user, {"title": "Falar com o DJ", "category": "Lembrete"}
    )
    assert created["ok"] is True
    record = db.scalar(
        select(WorkspaceRecord).where(
            WorkspaceRecord.module == "communication", WorkspaceRecord.title == "Falar com o DJ"
        )
    )
    assert record.category == "Lembrete"
    assert record.status == "Lembrete"

    updated = tools.update_communication_note(
        db, user, {"title": "Falar com o DJ", "category": "Decisão", "responsible": "Leonor"}
    )
    assert updated["ok"] is True
    record = db.scalar(
        select(WorkspaceRecord).where(
            WorkspaceRecord.module == "communication", WorkspaceRecord.title == "Falar com o DJ"
        )
    )
    assert record.category == "Decisão"
    assert record.status == "Decisão"
    assert record.responsible == "Leonor"

    removed = tools.remove_communication_note(db, user, {"title": "Falar com o DJ"})
    assert removed["ok"] is True
    assert (
        db.scalar(
            select(WorkspaceRecord).where(
                WorkspaceRecord.module == "communication", WorkspaceRecord.title == "Falar com o DJ"
            )
        ).is_archived
        is True
    )


def test_add_moodboard_item_creates_a_default_collection_and_placement() -> None:
    db, user = make_session_and_user()

    rejected = tools.add_moodboard_item(db, user, {"title": "Vestido", "image_url": "not-a-url"})
    assert rejected["ok"] is False

    created = tools.add_moodboard_item(
        db, user, {"title": "Vestido", "image_url": "https://example.com/vestido.jpg"}
    )
    assert created["ok"] is True
    item = db.scalar(select(MoodboardItem).where(MoodboardItem.title == "Vestido"))
    assert item is not None
    assert item.collection_id is not None

    removed = tools.remove_moodboard_item(db, user, {"title": "Vestido"})
    assert removed["ok"] is True
    assert (
        db.scalar(select(MoodboardItem).where(MoodboardItem.title == "Vestido")).is_archived is True
    )


def test_permanently_delete_record_requires_confirm_and_prior_archival() -> None:
    db, user = make_session_and_user()
    tools.add_guest(db, user, {"name": "João"})

    still_active = tools.permanently_delete_record(
        db, user, {"module": "guest", "identifier": "João", "confirm": "APAGAR"}
    )
    assert still_active["ok"] is False

    tools.remove_guest(db, user, {"name": "João"})

    wrong_confirm = tools.permanently_delete_record(
        db, user, {"module": "guest", "identifier": "João", "confirm": "sim"}
    )
    assert wrong_confirm["ok"] is False
    guest = db.scalar(select(Guest).where(Guest.name == "João"))
    assert guest is not None

    deleted = tools.permanently_delete_record(
        db, user, {"module": "guest", "identifier": "João", "confirm": "APAGAR"}
    )
    assert deleted["ok"] is True
    guest = db.scalar(select(Guest).where(Guest.name == "João"))
    assert guest is not None  # the row itself is never dropped
    assert is_tombstoned(db, Guest, guest.id) is True

    already_gone = tools.permanently_delete_record(
        db, user, {"module": "guest", "identifier": "João", "confirm": "APAGAR"}
    )
    assert already_gone["ok"] is False


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
            "<html><head><style>body{color:red}</style></head><body><p>Olá mundo</p></body></html>"
        )

    monkeypatch.setattr(tools.httpx, "get", lambda *args, **kwargs: FakeResponse())

    result = tools.fetch_webpage(db, user, {"url": "https://example.com"})
    assert result["ok"] is True
    assert "Olá mundo" in result["content"]
    assert "<p>" not in result["content"]
    assert "color:red" not in result["content"]
