"""Compact, JSON-safe views of the library's pydantic models.

The library models mirror TickTick's wire format, which is wide: a task carries
about 30 fields, most of them empty. Feeding that to a model burns context for
no signal, so tools answer with these summaries and keep the raw payload behind
an explicit flag.
"""

from datetime import datetime

from ticktick_v2.events import TicktickEvent
from ticktick_v2.focus import TickTickFocusTime
from ticktick_v2.habits import STATUS_CODES, TickTickHabitEntry
from ticktick_v2.tasks import TickTickProject, TickTickTask

TASK_STATUS_NAMES = {-1: "wont_do", 0: "active", 1: "unknown", 2: "completed"}
_PRIORITY_NAMES = {0: "none", 1: "low", 3: "medium", 5: "high"}

_CONTENT_LIMIT = 500


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat(timespec="minutes")


def _shorten(content: str | None, limit: int = _CONTENT_LIMIT) -> str | None:
    if not content:
        return None
    if len(content) <= limit:
        return content
    return content[: limit - 1] + "…"


def task_summary(task: TickTickTask, include_content: bool = True) -> dict:
    summary = {
        "id": task.id,
        "title": task.title,
        "project_id": task.project_id,
        "project_name": task.project_name,
        "status": TASK_STATUS_NAMES.get(task.status, task.status),
        "priority": _PRIORITY_NAMES.get(task.priority, task.priority),
        "due": _iso(task.due_date),
        "start": _iso(task.start_date),
        "is_recurring": task.is_recurring,
        "repeat_flag": task.repeat_flag,
        "tags": task.tags,
    }
    if include_content:
        summary["content"] = _shorten(task.content)
    return summary


def project_summary(project: TickTickProject) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "is_owner": project.is_owner,
        "in_all": project.in_all,
        "muted": project.muted,
        "group_id": project.group_id,
    }


def habit_summary(habit: dict) -> dict:
    """`get_all_habits_metadata` hands back raw dicts, so pick out what is known."""
    wanted = ("id", "name", "goal", "unit", "type", "repeatRule", "status", "archived")
    summary = {key: habit.get(key) for key in wanted}
    return {key: value for key, value in summary.items() if value is not None}


def checkin_summary(entry: TickTickHabitEntry, habit_name: str | None = None) -> dict:
    summary = {
        "habit_id": entry.habit_id,
        "date_stamp": entry.checkin_stamp,
        "status": STATUS_CODES.get(entry.status, entry.status),
        "value": entry.value,
        "goal": entry.goal,
    }
    if habit_name is not None:
        summary["habit_name"] = habit_name
    return summary


def focus_summary(session: TickTickFocusTime) -> dict:
    return {
        "id": session.id,
        "start": _iso(session.start_time),
        "end": _iso(session.end_time),
        "duration_minutes": session.total_duration,
        "status": session.status,
    }


def event_summary(event: TicktickEvent) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "start": _iso(event.start_time),
        "end": _iso(event.end_time),
        "duration_minutes": event.duration_minutes,
        "calendar_id": event.calendar_id,
        "calendar_name": event.calendar_name,
        "is_all_day": event.is_all_day,
        "content": _shorten(event.content, limit=200),
    }
