"""Create timestamped recoverable SQLite snapshots.

For PostgreSQL, invoke `pg_dump` from the host scheduler using LV_DATABASE_URL
and store the resulting dump in the same backup location.
"""

from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite:///"):
        print("PostgreSQL backup: schedule pg_dump in the production host.")
        return 0
    source = Path(settings.database_url.removeprefix("sqlite:///"))
    if not source.exists():
        print("Database file not found; no backup created.")
        return 1
    settings.backups_path.mkdir(parents=True, exist_ok=True)
    target = settings.backups_path / f"lv-wedding-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.db"
    copy2(source, target)
    print(f"Backup created: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
