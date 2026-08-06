from __future__ import annotations

import re
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.auth as auth_routes
import app.routes.pages as page_routes
from app.db.base import Base
from app.main import app
from app.models.core import ProjectSettings, User
from app.models.planning import Task
from app.services.checklist import checklist_snapshot
from app.services.security import hash_password


def csrf_from(response) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


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


def add_task(db, user, *, title, category, priority, due_date, status="Pendente") -> Task:
    task = Task(
        title=title,
        category=category,
        priority=priority,
        due_date=due_date,
        status=status,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(task)
    db.commit()
    return task


def test_checklist_snapshot_groups_by_month_and_category() -> None:
    db, user = make_session_and_user()
    add_task(
        db,
        user,
        title="Reservar quinta",
        category="Quinta",
        priority="Alta",
        due_date=date(2026, 8, 31),
    )
    add_task(
        db,
        user,
        title="Escolher flores",
        category="Decoração",
        priority="Média",
        due_date=date(2026, 8, 31),
    )
    add_task(
        db,
        user,
        title="Confirmar catering",
        category="Quinta",
        priority="Alta",
        due_date=date(2026, 9, 30),
        status="Concluído",
    )

    snapshot = checklist_snapshot(db)
    assert snapshot["total"] == 3
    assert snapshot["completed"] == 1
    assert len(snapshot["chapters"]) == 2

    august = snapshot["chapters"][0]
    assert august["title"] == "Agosto de 2026"
    assert {c["name"] for c in august["categories"]} == {"Quinta", "Decoração"}

    september = snapshot["chapters"][1]
    assert september["title"] == "Setembro de 2026"
    assert september["completed"] == 1
    assert september["percent"] == 100


def test_checklist_snapshot_gives_the_wedding_day_its_own_chapter() -> None:
    db, user = make_session_and_user()
    wedding_date = date(2027, 9, 4)
    add_task(
        db, user, title="Cortar o bolo", category="Quinta", priority="Alta", due_date=wedding_date
    )
    add_task(
        db,
        user,
        title="Assinar contrato",
        category="Quinta",
        priority="Alta",
        due_date=date(2026, 10, 31),
    )

    snapshot = checklist_snapshot(db, wedding_date=wedding_date)
    milestone_chapters = [c for c in snapshot["chapters"] if c["is_milestone"]]
    assert len(milestone_chapters) == 1
    assert "Dia do casamento" in milestone_chapters[0]["title"]
    assert milestone_chapters[0]["total"] == 1

    # October must not also contain the wedding-day task.
    october = next(c for c in snapshot["chapters"] if c["title"] == "Outubro de 2026")
    assert october["total"] == 1


def test_checklist_snapshot_puts_undated_tasks_in_a_trailing_chapter() -> None:
    db, user = make_session_and_user()
    add_task(db, user, title="Ideia solta", category="Geral", priority="Baixa", due_date=None)
    add_task(
        db,
        user,
        title="Tarefa com data",
        category="Geral",
        priority="Alta",
        due_date=date(2026, 8, 31),
    )

    snapshot = checklist_snapshot(db)
    assert snapshot["chapters"][-1]["title"] == "Sem mês definido"
    assert snapshot["chapters"][-1]["total"] == 1


def test_checklist_snapshot_search_filters_by_title_category_and_assignee() -> None:
    db, user = make_session_and_user()
    add_task(
        db,
        user,
        title="Reservar quinta",
        category="Quinta",
        priority="Alta",
        due_date=date(2026, 8, 31),
    )
    add_task(
        db,
        user,
        title="Escolher DJ",
        category="Música",
        priority="Média",
        due_date=date(2027, 1, 31),
    )

    snapshot = checklist_snapshot(db, search="quinta")
    assert snapshot["total"] == 1
    assert snapshot["chapters"][0]["categories"][0]["tasks"][0].title == "Reservar quinta"


def test_checklist_snapshot_ignores_archived_tasks() -> None:
    db, user = make_session_and_user()
    task = add_task(
        db,
        user,
        title="Tarefa arquivada",
        category="Geral",
        priority="Alta",
        due_date=date(2026, 8, 31),
    )
    task.is_archived = True
    db.commit()

    snapshot = checklist_snapshot(db)
    assert snapshot["total"] == 0
    assert snapshot["chapters"] == []


def test_checklist_page_renders_chapters_and_archived_view(monkeypatch) -> None:
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
                wedding_date=datetime(2027, 9, 4, 10, 0, tzinfo=UTC),
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.add(
            Task(
                title="Reservar quinta",
                category="Quinta",
                priority="Alta",
                due_date=date(2026, 8, 31),
                status="Pendente",
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )
        db.commit()
        user_id = user.id

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

        page = client.get("/checklist")
        assert page.status_code == 200
        assert "Agosto de 2026" in page.text
        assert "Quinta" in page.text
        assert 'data-priority="alta"' in page.text
        assert "checklist.css" in page.text

        archive = client.post(
            "/checklist/1/archive",
            data={"csrf_token": csrf_from(page)},
            follow_redirects=False,
        )
        assert archive.status_code == 303

        archived_page = client.get("/checklist?archived=true")
        assert archived_page.status_code == 200
        assert "Reservar quinta" in archived_page.text
        assert "Apagar definitivamente" in archived_page.text

    with Session(engine) as db:
        task = db.get(Task, 1)
        assert task.is_archived is True
