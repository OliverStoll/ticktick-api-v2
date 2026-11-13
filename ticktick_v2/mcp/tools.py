"""Tool implementations.

Kept separate from `server.py` so the tools can be built and exercised without
a transport: the MCP wiring only registers what is defined here.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from ticktick_v2 import events as ticktick_events
from ticktick_v2 import focus as ticktick_focus
from ticktick_v2 import habits as ticktick_habits
from ticktick_v2 import tasks as ticktick_tasks
from ticktick_v2.mcp.auth import LOGIN_HINT, AuthError, SessionCache
from ticktick_v2.mcp.config import McpSettings
from ticktick_v2.mcp.summaries import (
    checkin_summary,
    event_summary,
    focus_summary,
    habit_summary,
    project_summary,
    task_summary,
)
from ticktick_v2.tasks import TickTickTask

_PRIORITIES = {"none": 0, "low": 1, "medium": 3, "high": 5}
_TASK_STATES = {"active": 0, "completed": 2, "wont_do": -1}
_CHECKIN_STATES = {"not_completed": 0, "failed": 1, "completed": 2}


def _local_tz(settings: McpSettings) -> ZoneInfo | Any:
    if settings.timezone:
        return ZoneInfo(settings.timezone)
    return datetime.now().astimezone().tzinfo


def _parse_when(value: str | datetime | None, settings: McpSettings) -> tuple[datetime, bool] | None:
    """Parse a date or datetime, returning it with an all-day flag.

    A bare date counts as all-day, stored at 00:00 local time. A datetime
    without an offset is read as local time, which is what a user typing
    "2026-03-01T09:00" means.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value, False

    raw = value.strip()
    if not raw:
        return None

    parsed: datetime
    try:
        parsed = datetime.fromisoformat(raw)
        all_day = "T" not in raw
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(raw, pattern)
                all_day = " " not in raw
                break
            except ValueError:
                continue
        else:
            raise ValueError(
                f"Could not parse {value!r}. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM."
            ) from None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_local_tz(settings))
    return parsed, all_day


def _wire_datetime(value: datetime, settings: McpSettings) -> str:
    """Format a datetime the way the library does elsewhere: local wall time
    with a `+0000` suffix, which is what TickTick's `api/v2` expects."""
    localized = value.astimezone(_local_tz(settings))
    return localized.strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def _date_stamp(value: str | int | None) -> int:
    if value is None:
        return int(datetime.now().strftime("%Y%m%d"))
    if isinstance(value, int):
        return value
    raw = value.strip().replace("-", "")
    try:
        parsed = datetime.strptime(raw, "%Y%m%d")
    except ValueError as e:
        raise ValueError(f"Could not parse {value!r} as a date. Use YYYY-MM-DD.") from e
    return int(parsed.strftime("%Y%m%d"))


class TickTickTools:
    def __init__(self, settings: McpSettings, session: SessionCache | None = None) -> None:
        self.settings = settings
        self.session = session or SessionCache(settings)

    # -- plumbing -------------------------------------------------------

    def _headers(self) -> dict:
        return self.session.headers()

    def _result(self, response: requests.Response, **extra: Any) -> dict:
        payload: dict[str, Any] = {"ok": response.ok, "status_code": response.status_code, **extra}
        if response.status_code in (401, 403):
            self.session.invalidate()
            payload["hint"] = "TickTick rejected the session. " + LOGIN_HINT
        try:
            body = response.json()
        except ValueError:
            body = None
        if body is not None:
            payload["response"] = body
        return payload

    def _all_tasks(self, headers: dict) -> list[TickTickTask]:
        active = ticktick_tasks.get_active_tasks(headers=headers, raise_exception=True) or []
        projects = ticktick_tasks.get_all_projects(headers=headers) or {}
        return ticktick_tasks.add_project_properties_to_tasks(active, projects)

    def _find_task(self, task_id: str, headers: dict) -> TickTickTask:
        for task in self._all_tasks(headers):
            if task.id == task_id:
                return task
        abandoned = ticktick_tasks.get_abandoned_tasks(headers=headers) or []
        for task in abandoned:
            if task.id == task_id:
                return task
        raise ValueError(f"No task with id {task_id!r}. Use list_tasks to find the id.")

    # -- tasks ----------------------------------------------------------

    def list_tasks(
        self,
        status: str = "active",
        project: str | None = None,
        include_content: bool = True,
        limit: int = 100,
    ) -> dict:
        """List TickTick tasks, optionally filtered by project.

        status: "active" (open tasks), "abandoned" (marked won't do), or "all".
        project: project name or id; omit for every list, including the inbox.
        """
        if status not in {"active", "abandoned", "all"}:
            raise ValueError('status must be "active", "abandoned" or "all"')
        headers = self._headers()
        tasks: list[TickTickTask] = []
        if status in {"active", "all"}:
            tasks.extend(self._all_tasks(headers))
        if status in {"abandoned", "all"}:
            abandoned = ticktick_tasks.get_abandoned_tasks(headers=headers) or []
            projects = ticktick_tasks.get_all_projects(headers=headers) or {}
            tasks.extend(ticktick_tasks.add_project_properties_to_tasks(abandoned, projects))

        if project:
            needle = project.lower()
            tasks = [
                task
                for task in tasks
                if needle in {(task.project_name or "").lower(), task.project_id.lower()}
            ]

        summaries = [task_summary(task, include_content=include_content) for task in tasks[:limit]]
        return {"count": len(tasks), "returned": len(summaries), "tasks": summaries}

    def get_task(self, task_id: str, include_content: bool = True) -> dict:
        """Get one task by id, including content and recurrence details."""
        task = self._find_task(task_id, self._headers())
        summary = task_summary(task, include_content=include_content)
        summary["repeat_from"] = task.repeat_from
        summary["is_all_day"] = task.is_all_day
        return {"task": summary}

    def create_task(
        self,
        title: str,
        project_id: str = "inbox",
        content: str | None = None,
        due: str | None = None,
        start: str | None = None,
        priority: str = "none",
        tags: list[str] | None = None,
    ) -> dict:
        """Create a task.

        due/start: "YYYY-MM-DD" for an all-day task, "YYYY-MM-DDTHH:MM" for a timed one.
        priority: "none", "low", "medium" or "high".
        project_id: a project id from list_projects, or "inbox".
        """
        priority_value = _PRIORITIES.get(priority.lower(), None)
        if priority_value is None:
            raise ValueError('priority must be "none", "low", "medium" or "high"')

        task = TickTickTask(title=title, project_id=project_id)
        if content:
            task.content = content
        if tags:
            task.tags = tags
        task.priority = priority_value

        parsed_due = _parse_when(due, self.settings)
        if parsed_due:
            task.due_date = parsed_due[0]
            task.is_all_day = parsed_due[1]
        parsed_start = _parse_when(start, self.settings)
        if parsed_start:
            task.start_date = parsed_start[0]

        response = ticktick_tasks.create_task(task=task, headers=self._headers())
        return self._result(response, task_id=task.id, title=task.title)

    def update_task(
        self,
        task_id: str,
        project_id: str | None = None,
        title: str | None = None,
        content: str | None = None,
        due: str | None = None,
        start: str | None = None,
        priority: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
    ) -> dict:
        """Change fields on an existing task. Only the fields you pass are sent,
        the rest are read back from the current task first."""
        headers = self._headers()
        task = self._find_task(task_id, headers)
        if project_id:
            task.project_id = project_id

        changes: dict[str, Any] = {}
        if title is not None:
            changes["title"] = title
        if content is not None:
            changes["content"] = content
        if tags is not None:
            changes["tags"] = tags
        if priority is not None:
            if priority.lower() not in _PRIORITIES:
                raise ValueError('priority must be "none", "low", "medium" or "high"')
            changes["priority"] = _PRIORITIES[priority.lower()]
        if status is not None:
            if status.lower() not in _TASK_STATES:
                raise ValueError('status must be "active", "completed" or "wont_do"')
            changes["status"] = _TASK_STATES[status.lower()]

        parsed_due = _parse_when(due, self.settings)
        if parsed_due:
            changes["due_date"] = parsed_due[0]
            changes["is_all_day"] = parsed_due[1]
        parsed_start = _parse_when(start, self.settings)
        if parsed_start:
            changes["start_date"] = parsed_start[0]

        updated = task.model_copy(update=changes)
        response = ticktick_tasks.update_task(updated, headers=headers)
        return self._result(response, task_id=task_id)

    def complete_task(self, task_id: str, project_id: str) -> dict:
        """Mark a task complete."""
        response = ticktick_tasks.complete_task(
            task_id=task_id, project_id=project_id, headers=self._headers()
        )
        return self._result(response, task_id=task_id)

    def set_task_status(self, task_id: str, project_id: str, status: str) -> dict:
        """Set a task's status: "active", "completed" or "wont_do"."""
        if status.lower() not in _TASK_STATES:
            raise ValueError('status must be "active", "completed" or "wont_do"')
        response = ticktick_tasks.change_task_status(
            task_id=task_id,
            project_id=project_id,
            status=_TASK_STATES[status.lower()],
            headers=self._headers(),
        )
        return self._result(response, task_id=task_id)

    def delete_task(self, task_id: str, project_id: str) -> dict:
        """Delete a task permanently."""
        response = ticktick_tasks.delete_task(
            task_id=task_id, project_id=project_id, headers=self._headers()
        )
        return self._result(response, task_id=task_id)

    def list_projects(self) -> dict:
        """List projects (lists) with their ids, for use as create_task's project_id."""
        projects = ticktick_tasks.get_all_projects(headers=self._headers(), raise_exception=True) or {}
        return {"count": len(projects), "projects": [project_summary(p) for p in projects.values()]}

    # -- habits ---------------------------------------------------------

    def list_habits(self) -> dict:
        """List habits with their ids and daily goals."""
        metadata, _ = ticktick_habits.get_all_habits_metadata(self._headers())
        return {"count": len(metadata), "habits": [habit_summary(h) for h in metadata.values()]}

    def list_habit_checkins(
        self,
        after: str | int = "1970-01-01",
        habit_names: list[str] | None = None,
        limit: int = 31,
    ) -> dict:
        """List habit check-ins after a date, newest last.

        after: "YYYY-MM-DD" or a YYYYMMDD integer.
        habit_names: restrict to some habits; omit for all of them.
        limit: maximum entries returned per habit.
        """
        headers = self._headers()
        metadata, name_to_id = ticktick_habits.get_all_habits_metadata(headers)
        checkins = ticktick_habits.get_all_checkins(
            after_stamp=_date_stamp(after),
            habit_names=habit_names,
            headers=headers,
            habits_metadata=(metadata, name_to_id),
            raise_exception=True,
        ) or {}

        by_name: dict[str, list[dict]] = {}
        for habit_id, entries in checkins.items():
            name = metadata.get(habit_id, {}).get("name", habit_id)
            by_name[name] = [checkin_summary(entry, habit_name=name) for entry in entries[-limit:]]
        return {"habits": len(by_name), "checkins": by_name}

    def check_in_habit(
        self,
        habit_name: str,
        date: str | None = None,
        status: str = "completed",
        value: float | None = None,
    ) -> dict:
        """Record a habit check-in, replacing an existing one for that day.

        status: "completed", "failed" or "not_completed".
        value: units done, for habits with a goal above 1.
        date: "YYYY-MM-DD"; defaults to today.
        """
        if status.lower() not in _CHECKIN_STATES:
            raise ValueError('status must be "completed", "failed" or "not_completed"')
        headers = self._headers()
        metadata = ticktick_habits.get_all_habits_metadata(headers)
        if habit_name not in metadata[1]:
            known = ", ".join(sorted(metadata[1])) or "none"
            raise ValueError(f"Unknown habit {habit_name!r}. Known habits: {known}")

        stamp = _date_stamp(date)
        ticktick_habits.post_checkin(
            habit_name=habit_name,
            date_stamp=stamp,
            status=_CHECKIN_STATES[status.lower()],
            value=value,
            headers=headers,
            habits_metadata=metadata,
            raise_exception=True,
        )
        return {"ok": True, "habit_name": habit_name, "date_stamp": stamp, "status": status}

    # -- focus ----------------------------------------------------------

    def list_focus_sessions(self, days: int = 30, limit: int = 50) -> dict:
        """List completed focus/pomodoro sessions from the last `days` days."""
        sessions = ticktick_focus.get_all_focus_times(
            days_offset=days, headers=self._headers(), raise_exception=True
        ) or []
        ordered = sessions[-limit:]
        total = sum(session.total_duration or 0 for session in ordered)
        return {
            "count": len(ordered),
            "total_minutes": total,
            "sessions": [focus_summary(session) for session in ordered],
        }

    def get_active_focus(self) -> dict:
        """Report the focus session running right now, if any."""
        headers = self._headers()
        data = ticktick_focus.get_active_focus_data(headers=headers)
        if not data:
            return {"active": False, "minutes": 0}
        minutes = ticktick_focus.get_active_focus_time(
            headers=headers, timezone_name=self.settings.timezone or "UTC"
        )
        return {
            "active": True,
            "minutes": round(minutes, 1),
            "start": data.get("startTime"),
            "status": data.get("status"),
        }

    def add_focus_record(self, start: str, end: str, note: str = "") -> dict:
        """Backfill a completed focus session.

        start/end: "YYYY-MM-DDTHH:MM" (or a full ISO datetime with offset).
        """
        parsed_start = _parse_when(start, self.settings)
        parsed_end = _parse_when(end, self.settings)
        if not parsed_start or not parsed_end:
            raise ValueError("start and end are required")
        if parsed_end[0] <= parsed_start[0]:
            raise ValueError("end must be after start")
        record_id = ticktick_focus.add_focus_record(
            start=parsed_start[0], end=parsed_end[0], note=note, headers=self._headers()
        )
        minutes = (parsed_end[0] - parsed_start[0]).total_seconds() / 60
        return {"ok": True, "record_id": record_id, "minutes": round(minutes, 1)}

    # -- calendar events -------------------------------------------------

    def list_events(self, calendar_names: list[str] | None = None, only_active: bool = False) -> dict:
        """List calendar events, optionally only those happening right now."""
        events = ticktick_events.get_all_events(
            calendar_names=calendar_names, only_active=only_active, headers=self._headers()
        )
        return {"count": len(events), "events": [event_summary(event) for event in events]}

    # -- diagnostics -----------------------------------------------------

    def get_login_status(self, check_network: bool = False) -> dict:
        """Report whether the server has a usable TickTick session.

        check_network: also test the cookies against TickTick (one request).
        """
        status = self.session.status(check_network=check_network)
        return {
            "cookies_path": str(status.cookies_path),
            "cookies_present": status.cookies_present,
            "cookies_valid": status.cookies_valid,
            "cookie_age_days": status.cookie_age_days,
            "auto_login": status.auto_login,
            "credentials_present": status.credentials_present,
            "tool_profile": self.settings.tool_profile,
            "hint": LOGIN_HINT if not status.cookies_present else None,
        }


__all__ = ["AuthError", "TickTickTools", "_date_stamp", "_parse_when", "_wire_datetime"]
