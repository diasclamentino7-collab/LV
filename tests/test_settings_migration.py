from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import PROJECT_ROOT, get_settings


def test_advanced_settings_migration_preserves_existing_values(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "settings-upgrade.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("LV_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(PROJECT_ROOT / "alembic.ini"))

    try:
        command.upgrade(config, "20260724_0007")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (id, name, password_hash, is_active)
                    VALUES (1, 'Vítor', 'hash-preservado', 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO project_settings (
                        id, project_name, primary_color, secondary_color,
                        logo_path, wedding_date, total_budget, currency, language
                    ) VALUES (
                        1, 'Projeto preservado', '#D88BA7', '#F8DCE8',
                        '', '2026-09-14 15:30:00', '25000.00', 'EUR', 'pt-PT'
                    )
                    """
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT project_name, total_budget, wedding_date,
                           accent_color, motion_preference, settings_version
                    FROM project_settings
                    WHERE id = 1
                    """
                )
            ).one()
            user = connection.execute(
                text(
                    """
                    SELECT name, password_hash, is_active, session_version,
                           failed_login_attempts, locked_until
                    FROM users
                    WHERE id = 1
                    """
                )
            ).one()
    finally:
        get_settings.cache_clear()

    assert row.project_name == "Projeto preservado"
    assert row.total_budget == "25000.00"
    assert row.wedding_date.startswith("2026-09-14")
    assert row.accent_color == "#C9A46A"
    assert row.motion_preference == "full"
    assert row.settings_version == 1
    assert user.name == "Vítor"
    assert user.password_hash == "hash-preservado"
    assert user.is_active
    assert user.session_version == 1
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
