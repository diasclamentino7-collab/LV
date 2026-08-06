"""Read model for the checklist page: tasks grouped into monthly "chapters".

Chapters are derived entirely from ``Task.due_date`` — no schema change was
needed. Monthly chapters group by (year, month); a task due exactly on the
wedding date gets pulled into its own "Dia do casamento" chapter instead of
a same-titled monthly bucket; tasks with no due date land in a trailing
"Sem mês definido" chapter so nothing silently disappears from the view.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.planning import Task
from app.services.record_deletion import not_tombstoned

MONTH_NAMES_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

CHAPTER_SUBTITLES: dict[tuple[int, int], str] = {
    (2026, 8): "Bases do casamento",
    (2026, 9): "Salão do Reino e pesquisa de quintas",
    (2026, 10): "Visitar e reservar a quinta",
    (2026, 11): "Fotografia, vídeo e discurso",
    (2026, 12): "Estilo e comunicação inicial",
    (2027, 1): "Vestido, música e beleza",
    (2027, 2): "Fato, flores, convites e lua de mel",
    (2027, 3): "Processo civil, alianças e logística",
    (2027, 4): "Convites, menu e cerimónia",
    (2027, 5): "Vestuário, bolo e personalização",
    (2027, 6): "Confirmações e escolhas finais",
    (2027, 7): "Plano de mesas e organização detalhada",
    (2027, 8): "Confirmações finais",
}

COMPLETED_STATUS = "Concluído"


def _month_title(year: int, month: int) -> str:
    return f"{MONTH_NAMES_PT[month - 1].capitalize()} de {year}"


def _chapter_progress(tasks: list[Task]) -> tuple[int, int, int]:
    total = len(tasks)
    completed = sum(1 for task in tasks if task.status == COMPLETED_STATUS)
    percent = round(completed / total * 100) if total else 0
    return total, completed, percent


def _build_chapter(
    title: str, subtitle: str, tasks: list[Task], *, is_milestone: bool = False
) -> dict[str, Any]:
    categories: OrderedDict[str, list[Task]] = OrderedDict()
    for task in tasks:
        categories.setdefault(task.category or "Geral", []).append(task)
    total, completed, percent = _chapter_progress(tasks)
    return {
        "title": title,
        "subtitle": subtitle,
        "is_milestone": is_milestone,
        "total": total,
        "completed": completed,
        "percent": percent,
        "categories": [{"name": name, "tasks": items} for name, items in categories.items()],
    }


def checklist_snapshot(
    db: Session,
    *,
    wedding_date: date | None = None,
    search: str = "",
) -> dict[str, Any]:
    conditions = [Task.is_archived.is_(False), not_tombstoned(Task)]
    normalized_search = search.strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        conditions.append(
            or_(
                Task.title.ilike(pattern),
                Task.category.ilike(pattern),
                Task.tags.ilike(pattern),
                Task.assignee.ilike(pattern),
            )
        )
    tasks = db.scalars(
        select(Task).where(*conditions).order_by(Task.due_date.is_(None), Task.due_date, Task.id)
    ).all()

    wedding_day_tasks: list[Task] = []
    monthly: OrderedDict[tuple[int, int], list[Task]] = OrderedDict()
    unscheduled: list[Task] = []

    for task in tasks:
        if wedding_date is not None and task.due_date == wedding_date:
            wedding_day_tasks.append(task)
        elif task.due_date is None:
            unscheduled.append(task)
        else:
            key = (task.due_date.year, task.due_date.month)
            monthly.setdefault(key, []).append(task)

    chapters = [
        _build_chapter(_month_title(year, mo), CHAPTER_SUBTITLES.get((year, mo), ""), month_tasks)
        for (year, mo), month_tasks in monthly.items()
    ]
    if wedding_day_tasks:
        wd = wedding_date
        label = f"Dia do casamento — {wd.day} de {MONTH_NAMES_PT[wd.month - 1]} de {wd.year}"
        chapters.append(_build_chapter(label, "", wedding_day_tasks, is_milestone=True))
    if unscheduled:
        chapters.append(
            _build_chapter("Sem mês definido", "Tarefas sem data associada", unscheduled)
        )

    # Expand only the chapter that most needs attention (the first one not
    # fully done) by default; a long plan otherwise renders every task open
    # at once, which is both overwhelming and — with hundreds of tasks —
    # slow to paint.
    first_incomplete = next((c for c in chapters if c["percent"] < 100), None)
    opened = False
    for chapter in chapters:
        chapter["is_open"] = chapter is first_incomplete
        opened = opened or chapter["is_open"]
    if not opened and chapters:
        chapters[-1]["is_open"] = True

    total, completed, percent = _chapter_progress(list(tasks))
    return {
        "chapters": chapters,
        "total": total,
        "completed": completed,
        "percent": percent,
    }
