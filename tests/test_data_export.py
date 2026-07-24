from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.core import User, WorkspaceRecord
from app.services.data_export import build_data_export


def test_data_export_contains_planning_data_without_password_hashes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(User(name="Leonor", password_hash="never-export-this"))
        db.add(WorkspaceRecord(module="communication", title="Escolher flores"))
        db.commit()

        export = build_data_export(db)

    assert export["format"] == "lv-wedding-planner-export"
    assert export["tables"]["workspace_records"][0]["title"] == "Escolher flores"
    assert export["tables"]["users"][0]["name"] == "Leonor"
    assert "password_hash" not in export["tables"]["users"][0]
    assert "session_version" not in export["tables"]["users"][0]
    assert "failed_login_attempts" not in export["tables"]["users"][0]
    assert "locked_until" not in export["tables"]["users"][0]
