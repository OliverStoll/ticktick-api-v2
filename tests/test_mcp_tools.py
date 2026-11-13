from datetime import datetime

import pytest

from ticktick_v2.mcp import tools as mcp_tools
from ticktick_v2.mcp.config import McpSettings
from ticktick_v2.mcp.tools import TickTickTools, _date_stamp, _parse_when
from ticktick_v2.tasks import TickTickTask


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {"ok": True}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


class FakeSession:
    def __init__(self):
        self.invalidated = 0

    def headers(self):
        return {"Cookie": "session"}

    def invalidate(self):
        self.invalidated += 1

    def status(self, check_network=False):
        from ticktick_v2.mcp.auth import LoginStatus

        return LoginStatus(
            cookies_path=McpSettings().cookies_path,
            cookies_present=True,
            cookies_valid=True if check_network else None,
            cookie_age_days=0.5,
            auto_login=False,
            credentials_present=True,
        )


def build_tools(**overrides):
    settings = McpSettings(**overrides)
    session = FakeSession()
    return TickTickTools(settings, session=session), session


def test_parse_when_bare_date_is_all_day():
    tools, _ = build_tools()
    parsed = _parse_when("2026-03-01", tools.settings)
    assert parsed is not None
    value, all_day = parsed
    assert all_day is True
    assert (value.year, value.month, value.day) == (2026, 3, 1)


def test_parse_when_datetime_is_timed():
    tools, _ = build_tools()
    parsed = _parse_when("2026-03-01T09:30", tools.settings)
    assert parsed is not None
    value, all_day = parsed
    assert all_day is False
    assert value.hour == 9 and value.minute == 30


def test_parse_when_keeps_aware_offsets():
    tools, _ = build_tools()
    parsed = _parse_when("2026-03-01T09:30:00+02:00", tools.settings)
    assert parsed is not None
    assert parsed[0].utcoffset().total_seconds() == 7200


def test_parse_when_rejects_nonsense():
    tools, _ = build_tools()
    with pytest.raises(ValueError, match="Could not parse"):
        _parse_when("next tuesday", tools.settings)


def test_date_stamp_accepts_iso_and_int():
    assert _date_stamp("2026-03-01") == 20260301
    assert _date_stamp(20260301) == 20260301
    assert _date_stamp(None) == int(datetime.now().strftime("%Y%m%d"))


def test_list_tasks_filters_by_project_name(monkeypatch):
    tools, _ = build_tools()
    tasks = [
        TickTickTask(title="milk", project_id="p1", project_name="Groceries"),
        TickTickTask(title="report", project_id="p2", project_name="Work"),
    ]
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_active_tasks", lambda **_: tasks)
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_all_projects", lambda **_: {})

    result = tools.list_tasks(project="groceries")
    assert result["count"] == 1
    assert result["tasks"][0]["title"] == "milk"


def test_list_tasks_respects_limit(monkeypatch):
    tools, _ = build_tools()
    tasks = [TickTickTask(title=f"t{i}", project_id="p1") for i in range(5)]
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_active_tasks", lambda **_: tasks)
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_all_projects", lambda **_: {})

    result = tools.list_tasks(limit=2)
    assert result["count"] == 5
    assert result["returned"] == 2


def test_list_tasks_rejects_unknown_status(monkeypatch):
    tools, _ = build_tools()
    with pytest.raises(ValueError, match="status must be"):
        tools.list_tasks(status="done")


def test_create_task_sends_parsed_due_date(monkeypatch):
    tools, _ = build_tools()
    captured = {}

    def fake_create_task(task, headers=None):
        captured["task"] = task
        return FakeResponse(200, {"id2etag": {task.id: "etag"}})

    monkeypatch.setattr(mcp_tools.ticktick_tasks, "create_task", fake_create_task)
    result = tools.create_task(title="Buy milk", due="2026-03-01", priority="high")

    task = captured["task"]
    assert task.title == "Buy milk"
    assert task.priority == 5
    assert task.is_all_day is True
    assert task.due_date.day == 1
    assert result["ok"] is True
    assert result["task_id"] == task.id


def test_create_task_rejects_unknown_priority():
    tools, _ = build_tools()
    with pytest.raises(ValueError, match="priority must be"):
        tools.create_task(title="t", priority="urgent")


def test_update_task_only_changes_given_fields(monkeypatch):
    tools, _ = build_tools()
    existing = TickTickTask(title="old", project_id="p1", content="keep me", priority=0)
    captured = {}

    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_active_tasks", lambda **_: [existing])
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_all_projects", lambda **_: {})

    def fake_update_task(task, headers=None):
        captured["task"] = task
        return FakeResponse()

    monkeypatch.setattr(mcp_tools.ticktick_tasks, "update_task", fake_update_task)
    tools.update_task(task_id=existing.id, title="new")

    assert captured["task"].title == "new"
    assert captured["task"].content == "keep me"
    assert captured["task"].project_id == "p1"


def test_find_task_reports_unknown_id(monkeypatch):
    tools, _ = build_tools()
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_active_tasks", lambda **_: [])
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_all_projects", lambda **_: {})
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_abandoned_tasks", lambda **_: [])

    with pytest.raises(ValueError, match="No task with id"):
        tools.get_task(task_id="deadbeef")


def test_find_task_falls_back_to_abandoned(monkeypatch):
    tools, _ = build_tools()
    abandoned = TickTickTask(title="dropped", project_id="p1", status=-1)
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_active_tasks", lambda **_: [])
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_all_projects", lambda **_: {})
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_abandoned_tasks", lambda **_: [abandoned])

    result = tools.get_task(task_id=abandoned.id)
    assert result["task"]["status"] == "wont_do"


def test_check_in_habit_rejects_unknown_habit(monkeypatch):
    tools, _ = build_tools()
    monkeypatch.setattr(
        mcp_tools.ticktick_habits, "get_all_habits_metadata", lambda *_: ({}, {"Meditate": "h1"})
    )
    with pytest.raises(ValueError, match="Unknown habit"):
        tools.check_in_habit(habit_name="Run")


def test_check_in_habit_posts_with_mapped_status(monkeypatch):
    tools, _ = build_tools()
    captured = {}
    monkeypatch.setattr(
        mcp_tools.ticktick_habits, "get_all_habits_metadata", lambda *_: ({}, {"Meditate": "h1"})
    )

    def fake_post_checkin(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(mcp_tools.ticktick_habits, "post_checkin", fake_post_checkin)
    result = tools.check_in_habit(habit_name="Meditate", date="2026-03-01", status="failed")

    assert captured["status"] == 1
    assert captured["date_stamp"] == 20260301
    assert result["ok"] is True


def test_add_focus_record_rejects_backwards_range():
    tools, _ = build_tools()
    with pytest.raises(ValueError, match="end must be after start"):
        tools.add_focus_record(start="2026-03-01T10:00", end="2026-03-01T09:00")


def test_auth_rejection_invalidates_the_session(monkeypatch):
    tools, session = build_tools()
    existing = TickTickTask(title="t", project_id="p1")
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_active_tasks", lambda **_: [existing])
    monkeypatch.setattr(mcp_tools.ticktick_tasks, "get_all_projects", lambda **_: {})
    monkeypatch.setattr(
        mcp_tools.ticktick_tasks, "complete_task", lambda **_: FakeResponse(401, {"error": "auth"})
    )

    result = tools.complete_task(task_id=existing.id, project_id="p1")
    assert result["ok"] is False
    assert "hint" in result
    assert session.invalidated == 1


def test_get_login_status_reports_cookie_file():
    tools, _ = build_tools()
    status = tools.get_login_status()
    assert status["cookies_present"] is True
    assert status["tool_profile"] == "full"
    assert status["hint"] is None
