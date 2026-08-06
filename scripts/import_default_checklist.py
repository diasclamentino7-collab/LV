"""One-off import of the couple's original 13-month wedding checklist.

Only ever reaches a database this machine's ``LV_DATABASE_URL`` points at
(the local dev SQLite file by default). To import into a deployed
environment (e.g. the production Postgres database), use the "Importar o
plano completo" button on the checklist page instead, logged in on that
deployment — see ``app.services.checklist_seed.import_default_checklist``,
which both this script and that button call.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import User
from app.services.checklist_seed import import_default_checklist


def main() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.name == "Vitor")) or db.scalar(select(User))
        created = import_default_checklist(db, user)
        print(f"Imported {created} tasks.")


if __name__ == "__main__":
    main()
