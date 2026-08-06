from __future__ import annotations

from collections import Counter
from datetime import date

from app.services.assistant_tools import TASK_PRIORITIES
from app.services.checklist_seed import default_checklist_tasks

WEDDING_DATE = date(2027, 9, 4)


def test_default_checklist_has_the_expected_shape() -> None:
    tasks = default_checklist_tasks(WEDDING_DATE)

    assert len(tasks) == 419
    assert all(task["priority"] in TASK_PRIORITIES for task in tasks)
    assert all(task["title"] and task["category"] for task in tasks)
    assert all(task["due_date"] is not None for task in tasks)
    # Everything sits between the plan's start and the wedding day itself.
    assert all(date(2026, 8, 1) <= task["due_date"] <= WEDDING_DATE for task in tasks)


def test_default_checklist_has_no_duplicate_title_within_the_same_chapter() -> None:
    tasks = default_checklist_tasks(WEDDING_DATE)
    keys = Counter((task["title"], task["category"], task["due_date"]) for task in tasks)
    duplicates = {key: count for key, count in keys.items() if count > 1}
    assert duplicates == {}


def test_default_checklist_reuses_the_same_wedding_date_for_the_final_chapter() -> None:
    tasks = default_checklist_tasks(WEDDING_DATE)
    wedding_day_tasks = [task for task in tasks if task["due_date"] == WEDDING_DATE]
    assert len(wedding_day_tasks) == 42
    assert {task["category"] for task in wedding_day_tasks} == {
        "Preparação",
        "Cerimónia",
        "Quinta",
        "Depois do casamento",
    }
