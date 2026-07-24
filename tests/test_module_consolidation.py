from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.core import WorkspaceRecord
from app.routes.pages import MODULES, module_query


def test_kingdom_hall_includes_legacy_ceremony_records() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add_all(
            [
                WorkspaceRecord(module="kingdom-hall", title="Programa"),
                WorkspaceRecord(module="ceremony", title="Discurso"),
                WorkspaceRecord(module="reception", title="Jantar"),
            ]
        )
        db.commit()

        records = db.scalars(module_query(MODULES["kingdom-hall"], "")).all()

    assert {record.title for record in records} == {"Programa", "Discurso"}


def test_reception_includes_legacy_quinta_records() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add_all(
            [
                WorkspaceRecord(module="reception", title="Copo de Água"),
                WorkspaceRecord(module="quinta", title="Quinta visitada"),
                WorkspaceRecord(module="ceremony", title="Discurso"),
            ]
        )
        db.commit()

        records = db.scalars(module_query(MODULES["reception"], "")).all()

    assert {record.title for record in records} == {
        "Copo de Água",
        "Quinta visitada",
    }


def test_legacy_module_urls_share_the_canonical_configuration() -> None:
    assert MODULES["ceremony"] is MODULES["kingdom-hall"]
    assert MODULES["quinta"] is MODULES["reception"]
