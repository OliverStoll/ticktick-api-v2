from datetime import datetime

from ticktick_v2.events import TicktickEvent
from ticktick_v2.focus import TickTickFocusTime
from ticktick_v2.habits import TickTickHabitEntry
from ticktick_v2.mcp.summaries import (
    checkin_summary,
    event_summary,
    focus_summary,
    habit_summary,
    project_summary,
    task_summary,
)
from ticktick_v2.tasks import TickTickProject, TickTickTask


def test_task_summary_names_status_and_priority():
    task = TickTickTask(title="Buy milk", project_id="p1", status=0, priority=5)
    summary = task_summary(task)
    assert summary["status"] == "active"
    assert summary["priority"] == "high"
    assert summary["title"] == "Buy milk"
    assert summary["id"] == task.id


def test_task_summary_maps_done_and_wont_do():
    assert task_summary(TickTickTask(title="t", project_id="p", status=2))["status"] == "completed"
    assert task_summary(TickTickTask(title="t", project_id="p", status=-1))["status"] == "wont_do"


def test_task_summary_drops_content_on_request():
    task = TickTickTask(title="t", project_id="p", content="long notes")
    assert task_summary(task, include_content=False).get("content") is None
    assert task_summary(task)["content"] == "long notes"


def test_task_summary_truncates_long_content():
    task = TickTickTask(title="t", project_id="p", content="x" * 900)
    summary = task_summary(task)
    assert len(summary["content"]) == 500
    assert summary["content"].endswith("…")


def test_task_summary_formats_due_date():
    task = TickTickTask(
        title="t", project_id="p", due_date=datetime(2026, 3, 1, 9, 30)
    )
    assert task_summary(task)["due"] == "2026-03-01T09:30"


def test_project_summary_keeps_list_flags():
    project = TickTickProject(
        id="p1", name="Groceries", is_owner=True, in_all=False, group_id=None, muted=True
    )
    assert project_summary(project) == {
        "id": "p1",
        "name": "Groceries",
        "is_owner": True,
        "in_all": False,
        "muted": True,
        "group_id": None,
    }


def test_habit_summary_keeps_known_keys_only():
    summary = habit_summary({"id": "h1", "name": "Meditate", "goal": 1, "unknown": "x"})
    assert summary == {"id": "h1", "name": "Meditate", "goal": 1}


def test_checkin_summary_names_status():
    entry = TickTickHabitEntry(
        habit_id="h1", checkin_stamp=20260301, goal=1, value=1, status=2
    )
    summary = checkin_summary(entry, habit_name="Meditate")
    assert summary["status"] == "Completed"
    assert summary["date_stamp"] == 20260301
    assert summary["habit_name"] == "Meditate"


def test_focus_summary_reports_duration():
    session = TickTickFocusTime(
        id="f1",
        type=0,
        start_time="2026-03-01T09:00:00+01:00",
        end_time="2026-03-01T10:30:00+01:00",
        status=1,
        pause_duration=0,
    )
    summary = focus_summary(session)
    assert summary["duration_minutes"] == 90
    assert summary["id"] == "f1"


def test_event_summary_includes_calendar_and_duration():
    event = TicktickEvent(
        id="e1",
        title="Standup",
        dueStart="2026-03-01T09:00:00+01:00",
        dueEnd="2026-03-01T09:15:00+01:00",
        calendarId="c1",
        calendarName="Work",
        isAllDay=False,
        content="daily",
    )
    summary = event_summary(event)
    assert summary["duration_minutes"] == 15
    assert summary["calendar_name"] == "Work"
    assert summary["is_all_day"] is False
