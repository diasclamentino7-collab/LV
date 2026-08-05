from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.core import ProjectSettings, User
from app.models.planning import BudgetCategory, Guest, LegalDocument, Task, Vendor
from app.services.assistant_context import build_context_snapshot
from app.services.security import hash_password


def test_snapshot_includes_planning_data_but_excludes_guest_contact_details() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        user = User(name="Vítor", password_hash=hash_password("password123"))
        db.add(user)
        db.flush()

        settings = ProjectSettings(
            id=1,
            partner_one_name="Vítor",
            partner_two_name="Leonor",
            total_budget="10000",
            currency="EUR",
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(settings)

        db.add(
            Guest(
                name="Maria Silva",
                rsvp_status="Confirmado",
                side="Noiva",
                table_name="Mesa 3",
                dietary_requirements="Vegetariana",
                phone="912345678",
                email="maria@example.pt",
                address="Rua Principal, 12",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.add(
            Task(
                title="Reservar espaço",
                status="Concluído",
                assignee="Vítor",
                priority="Alta",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.add(
            Vendor(
                vendor_type="Fotografia",
                company="Foto Bonita",
                contact_name="Ana",
                phone="913000000",
                agreed_price="1500",
                notes="Pagamento em duas prestações",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.add(
            BudgetCategory(
                name="Fotografia",
                planned_limit="1500",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.add(
            LegalDocument(
                document_type="Certidão",
                title="Certidão de nascimento",
                status="Pendente",
                responsible="Leonor",
                notes="Número de documento: 123456789",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.commit()
        db.refresh(settings)

        snapshot = build_context_snapshot(db, settings)

    # Included: the couple's own planning data.
    assert "Maria Silva" in snapshot
    assert "Confirmado" in snapshot
    assert "Mesa 3" in snapshot
    assert "Vegetariana" in snapshot
    assert "Reservar espaço" in snapshot
    assert "Foto Bonita" in snapshot
    assert "Pagamento em duas prestações" in snapshot
    assert "Certidão de nascimento" in snapshot

    # Excluded: third-party contact details and legal document specifics.
    assert "912345678" not in snapshot
    assert "913000000" not in snapshot
    assert "maria@example.pt" not in snapshot
    assert "Rua Principal, 12" not in snapshot
    assert "123456789" not in snapshot
