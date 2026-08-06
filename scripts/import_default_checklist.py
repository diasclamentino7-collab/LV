"""One-off import of the couple's original 13-month wedding checklist.

Safe to re-run: skips any (title, category, due_date) already present, so
nothing gets duplicated on a second run. Also sets the wedding date in the
project settings to 4 September 2027 if it isn't configured yet, since the
whole checklist (and the checklist page's "Dia do casamento" chapter) is
built around that date.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import ProjectSettings, User
from app.models.planning import Task
from app.services.activity import record_activity
from app.services.checklist_seed import default_checklist_tasks

WEDDING_DATE = datetime(2027, 9, 4, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))


def main() -> None:
    with SessionLocal() as db:
        settings = db.scalar(select(ProjectSettings))
        if settings is None:
            settings = ProjectSettings()
            db.add(settings)
        if settings.wedding_date is None:
            settings.wedding_date = WEDDING_DATE

        user = db.scalar(select(User).where(User.name == "Vitor")) or db.scalar(select(User))
        existing = {(t.title, t.category, t.due_date) for t in db.scalars(select(Task)).all()}

        seed = default_checklist_tasks(WEDDING_DATE.date())
        created = 0
        for item in seed:
            key = (item["title"], item["category"], item["due_date"])
            if key in existing:
                continue
            db.add(
                Task(
                    title=item["title"],
                    category=item["category"],
                    priority=item["priority"],
                    due_date=item["due_date"],
                    status="Pendente",
                    created_by_id=user.id if user else None,
                    updated_by_id=user.id if user else None,
                )
            )
            created += 1

        if created:
            record_activity(
                db,
                user.id if user else None,
                "criou",
                f"importou a checklist completa do casamento ({created} tarefas)",
                "checklist",
            )
        db.commit()
        print(f"Imported {created} tasks (skipped {len(seed) - created} already present).")


if __name__ == "__main__":
    main()
