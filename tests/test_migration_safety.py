from scripts.check_migrations import MIGRATIONS_DIR, forbidden_calls


def test_migrations_do_not_drop_tables_or_columns() -> None:
    violations = [
        violation
        for migration in MIGRATIONS_DIR.glob("*.py")
        for violation in forbidden_calls(migration)
    ]
    assert violations == []
