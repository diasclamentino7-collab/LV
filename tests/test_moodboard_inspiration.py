import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.auth as auth_routes
import app.routes.moodboard as moodboard_routes
from app.db.base import Base
from app.main import app
from app.models.core import Activity, User
from app.models.moodboard import (
    MoodboardBoard,
    MoodboardCollection,
    MoodboardInspirationPlacement,
    MoodboardItem,
)
from app.services.security import hash_password


def csrf_from(page: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert match
    return match.group(1)


def moodboard_client(monkeypatch) -> tuple[TestClient, sessionmaker, int]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)
    monkeypatch.setattr(moodboard_routes, "SessionLocal", test_session)
    monkeypatch.setattr(auth_routes, "SessionLocal", test_session)
    monkeypatch.setattr(templating_module, "SessionLocal", test_session)

    with Session(engine) as db:
        user = User(name="Vítor", password_hash=hash_password("password123"))
        db.add(user)
        db.flush()
        board = MoodboardBoard(
            name="O nosso casamento",
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(board)
        db.flush()
        collection = MoodboardCollection(
            board_id=board.id,
            name="Flores",
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(collection)
        db.flush()
        db.add_all(
            [
                MoodboardItem(
                    collection_id=collection.id,
                    title="Rosas antigas",
                    image_url="https://example.com/rosas.jpg",
                    position=1,
                    created_by_id=user.id,
                    updated_by_id=user.id,
                ),
                MoodboardItem(
                    collection_id=collection.id,
                    title="Mesa romântica",
                    image_url="https://example.com/mesa.jpg",
                    position=2,
                    created_by_id=user.id,
                    updated_by_id=user.id,
                ),
            ]
        )
        db.commit()
        user_id = user.id
    return TestClient(app), test_session, user_id


def login(client: TestClient, user_id: int) -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "user_id": user_id,
            "password": "password123",
            "csrf_token": csrf_from(page.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_inspiration_table_persists_bounded_positions_and_favorites(monkeypatch) -> None:
    client, test_session, user_id = moodboard_client(monkeypatch)
    with client:
        login(client, user_id)
        page = client.get("/moodboard?view=table")
        assert page.status_code == 200
        assert "Mesa de Inspiração" in page.text
        assert "data-inspiration-table" in page.text
        token = csrf_from(page.text)

        with test_session() as db:
            items = list(db.scalars(select(MoodboardItem).order_by(MoodboardItem.position)).all())
            placements = list(db.scalars(select(MoodboardInspirationPlacement)).all())
            assert len(placements) == 2
            first_item_id = items[0].id

        rejected = client.post(
            f"/moodboard/{first_item_id}/placement",
            data={
                "x_percent": "10",
                "y_percent": "10",
                "rotation_degrees": "0",
                "layer": "1",
            },
        )
        assert rejected.status_code == 403

        saved = client.post(
            f"/moodboard/{first_item_id}/placement",
            data={
                "csrf_token": token,
                "x_percent": "999",
                "y_percent": "-50",
                "rotation_degrees": "42",
                "layer": "999999",
            },
            headers={"X-Requested-With": "lv-moodboard"},
        )
        assert saved.status_code == 200
        assert saved.json() == {
            "ok": True,
            "x": 82.0,
            "y": 0.0,
            "rotation": 6.0,
            "layer": 10000,
        }

        favorite = client.post(
            f"/moodboard/{first_item_id}/favorite",
            data={
                "csrf_token": token,
                "return_view": "table",
            },
            headers={"X-Requested-With": "lv-moodboard"},
        )
        assert favorite.status_code == 200
        assert favorite.json() == {"ok": True, "favorite": True}

        with test_session() as db:
            placement = db.scalar(
                select(MoodboardInspirationPlacement).where(
                    MoodboardInspirationPlacement.item_id == first_item_id
                )
            )
            item = db.get(MoodboardItem, first_item_id)
            assert placement is not None
            assert (placement.x_percent, placement.y_percent) == (82.0, 0.0)
            assert placement.updated_by_id == user_id
            assert item is not None and item.is_favorite
            assert db.scalar(
                select(Activity).where(
                    Activity.module == "moodboard",
                    Activity.action_type == "organizou",
                )
            )


def test_concurrent_first_placement_keeps_both_writes_instead_of_500(monkeypatch) -> None:
    client, test_session, user_id = moodboard_client(monkeypatch)
    with client:
        login(client, user_id)
        page = client.get("/moodboard")
        token = csrf_from(page.text)

        with test_session() as db:
            item = db.scalars(select(MoodboardItem).order_by(MoodboardItem.id)).first()
            item_id = item.id
            # Simulate this item never having been placed yet (the state two
            # collaborators would both see if they open the board for the
            # very first time at the same moment).
            db.query(MoodboardInspirationPlacement).filter_by(item_id=item_id).delete()
            db.commit()

        original_default_placement = moodboard_routes.default_placement

        def racing_default_placement(index, owner_id, placement_item_id):
            if placement_item_id == item_id:
                # A second collaborator's request wins the race and commits
                # its own placement row first, from a separate session.
                with test_session() as other_db:
                    other_db.add(original_default_placement(0, owner_id, placement_item_id))
                    other_db.commit()
            return original_default_placement(index, owner_id, placement_item_id)

        monkeypatch.setattr(moodboard_routes, "default_placement", racing_default_placement)

        response = client.post(
            f"/moodboard/{item_id}/placement",
            data={
                "csrf_token": token,
                "x_percent": "40",
                "y_percent": "30",
                "rotation_degrees": "5",
                "layer": "3",
            },
            headers={"X-Requested-With": "lv-moodboard"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True

        with test_session() as db:
            placements = db.scalars(
                select(MoodboardInspirationPlacement).where(
                    MoodboardInspirationPlacement.item_id == item_id
                )
            ).all()
            # The unique constraint keeps exactly one row, and it must carry
            # this request's move rather than silently losing it to a 500.
            assert len(placements) == 1
            assert (placements[0].x_percent, placements[0].y_percent) == (40.0, 30.0)


def test_accessible_reorder_keeps_items_and_changes_custom_order(monkeypatch) -> None:
    client, test_session, user_id = moodboard_client(monkeypatch)
    with client:
        login(client, user_id)
        page = client.get("/moodboard")
        token = csrf_from(page.text)
        with test_session() as db:
            items = list(db.scalars(select(MoodboardItem).order_by(MoodboardItem.position)).all())
            second_item_id = items[1].id

        response = client.post(
            f"/moodboard/{second_item_id}/reorder",
            data={
                "csrf_token": token,
                "direction": "previous",
                "return_view": "gallery",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "message=reordered" in response.headers["location"]

        with test_session() as db:
            items = list(db.scalars(select(MoodboardItem).order_by(MoodboardItem.position)).all())
            assert [item.id for item in items][0] == second_item_id
            assert len(items) == 2


def test_filtered_first_visit_keeps_the_global_table_position(monkeypatch) -> None:
    client, test_session, user_id = moodboard_client(monkeypatch)
    with test_session() as db:
        items = list(db.scalars(select(MoodboardItem).order_by(MoodboardItem.position)).all())
        items[1].is_favorite = True
        second_item_id = items[1].id
        db.commit()

    with client:
        login(client, user_id)
        page = client.get("/moodboard?view=table&favorites=true")
        assert page.status_code == 200

        with test_session() as db:
            placements = list(db.scalars(select(MoodboardInspirationPlacement)).all())

    assert len(placements) == 1
    assert placements[0].item_id == second_item_id
    assert placements[0].x_percent == 28.0
