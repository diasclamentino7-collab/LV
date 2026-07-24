from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import PROJECT_ROOT, get_settings


def test_existing_tombstone_releases_category_name_without_losing_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "deleted-category-upgrade.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("LV_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(PROJECT_ROOT / "alembic.ini"))

    try:
        command.upgrade(config, "20260724_0013")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO budget_categories (
                        id, name, planned_limit, is_archived
                    ) VALUES (
                        41, '123', 500, 1
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO record_tombstones (
                        entity_type, entity_id, module, snapshot_json
                    ) VALUES (
                        'budget_categories', 41, 'budget',
                        '{"id": 41, "name": "123", "planned_limit": "500"}'
                    )
                    """
                )
            )

        command.upgrade(config, "head")
        with engine.begin() as connection:
            preserved = connection.execute(
                text(
                    """
                    SELECT name, planned_limit, is_archived
                    FROM budget_categories
                    WHERE id = 41
                    """
                )
            ).one()
            snapshot = connection.execute(
                text(
                    """
                    SELECT snapshot_json
                    FROM record_tombstones
                    WHERE entity_type = 'budget_categories' AND entity_id = 41
                    """
                )
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO budget_categories (name, planned_limit, is_archived)
                    VALUES ('123', 750, 0)
                    """
                )
            )
            active_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM budget_categories
                    WHERE name = '123' AND is_archived = 0
                    """
                )
            ).scalar_one()
    finally:
        get_settings.cache_clear()

    assert preserved.name.startswith("__lv_deleted_budget_categories_41")
    assert preserved.planned_limit == 500
    assert preserved.is_archived
    assert '"name": "123"' in snapshot
    assert active_count == 1
