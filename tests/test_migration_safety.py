from pathlib import Path
from textwrap import indent

import pytest

from scripts.check_migrations import MIGRATIONS_DIR, forbidden_calls


def test_project_migrations_are_data_preserving() -> None:
    violations = [
        violation
        for migration in MIGRATIONS_DIR.glob("*.py")
        for violation in forbidden_calls(migration)
    ]
    assert violations == []


@pytest.mark.parametrize(
    ("migration_body", "expected"),
    [
        ("op.drop_table('guests')", "drop_table"),
        ("op.drop_column('guests', 'name')", "drop_column"),
        ("op.rename_table('guests', 'old_guests')", "rename_table"),
        ("op.execute('TRUNCATE TABLE guests')", "raw SQL TRUNCATE"),
        ("op.execute(sa.text('DROP TABLE guests'))", "raw SQL DROP"),
        (
            "connection.execute(text('DELETE FROM guests WHERE id = 1'))",
            "raw SQL DELETE",
        ),
        (
            "statement = 'DELETE FROM guests'\nop.execute(statement)",
            "raw SQL DELETE",
        ),
        (
            "table = 'guests'\nop.execute(f'TRUNCATE TABLE {table}')",
            "raw SQL TRUNCATE",
        ),
    ],
)
def test_destructive_migration_operations_are_rejected(
    tmp_path: Path, migration_body: str, expected: str
) -> None:
    migration = tmp_path / "unsafe_migration.py"
    migration.write_text(
        "from alembic import op\nimport sqlalchemy as sa\n\n"
        "def upgrade():\n"
        f"{indent(migration_body, '    ')}\n",
        encoding="utf-8",
    )

    violations = forbidden_calls(migration)

    assert any(expected in violation for violation in violations)


def test_additive_and_data_copy_operations_are_allowed(tmp_path: Path) -> None:
    migration = tmp_path / "safe_migration.py"
    migration.write_text(
        "from alembic import op\nimport sqlalchemy as sa\n\n"
        "def upgrade():\n"
        "    op.add_column('guests', sa.Column('nickname', sa.String()))\n"
        "    op.create_index('ix_guests_nickname', 'guests', ['nickname'])\n"
        '    op.execute("UPDATE guests SET nickname = name WHERE nickname IS NULL")\n',
        encoding="utf-8",
    )

    assert forbidden_calls(migration) == []


def test_sql_keywords_in_comments_are_ignored(tmp_path: Path) -> None:
    migration = tmp_path / "documented_migration.py"
    migration.write_text(
        "from alembic import op\n\n"
        "def upgrade():\n"
        "    op.execute('-- Never DELETE FROM guests\\nSELECT 1')\n",
        encoding="utf-8",
    )

    assert forbidden_calls(migration) == []
