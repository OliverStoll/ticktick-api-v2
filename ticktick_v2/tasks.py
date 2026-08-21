import json
import secrets
import warnings
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from pydantic import BaseModel, ConfigDict, Field

from ticktick_v2.cookies_login import get_authenticated_ticktick_headers
from ticktick_v2.utils.logger import create_logger

log = create_logger("TickTick Tasks")

_URL_GET_TASKS = "https://api.ticktick.com/api/v2/batch/check/0"
_URL_GET_PROJECTS = "https://api.ticktick.com/api/v2/projects"
_URL_CREATE_TASK = "https://api.ticktick.com/api/v2/batch/task"
_URL_ABANDONED_TASKS = "https://api.ticktick.com/api/v2/project/all/closed?status=Abandoned"


def current_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def get_today_due_date() -> str:
    return datetime.today().strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def format_datetime_custom(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def generate_id() -> str:
    return secrets.token_hex(12)


def _headers(headers: dict | None) -> dict:
    """Every function here takes an optional `headers` so a caller doing many
    requests can fetch it once with `get_authenticated_ticktick_headers()` and
    pass it in, instead of re-authenticating per call. If omitted, it's
    fetched fresh, which is cheap once cookies are cached on disk."""
    return headers if headers is not None else get_authenticated_ticktick_headers()


class TickTickTask(BaseModel):
    id: str = Field(default_factory=generate_id)
    title: str
    project_id: str
    status: int = 0  # -1: wont do, 0: acitve, 1: ?, 2: done
    priority: int = 0
    progress: int = 0
    deleted: int = 0
    # dates
    created_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    start_date: datetime | None = None
    due_date: datetime | None = None
    # recurrence
    repeat_first_date: datetime | None = None
    repeat_flag: str | None = None
    repeat_task_id: str | None = None
    repeat_from: str | None = None  # 1: "repeat from completion date", 2: "repeat from due date"
    # metadata
    creator: int | None = None
    sort_order: int = -3298534883327
    items: list = []
    tags: list = []
    ex_date: list = []
    reminders: list = []
    kind: str | None = None
    show_in_all: bool | None = None
    project_muted: bool | None = None
    column_id: str | None = None
    is_all_day: bool | None = None
    content: str | None = ""
    assignee: str | None = None
    is_floating: bool = False
    time_zone: str = "Europe/Berlin"
    project_name: str | None = None  # manually set after fetching projects

    @property
    def is_active(self) -> bool:
        """
        Check if the task is currently active based on its start date.
        """
        if not self.start_date:
            return False
        timezone_name = self.time_zone or "Europe/Berlin"
        now = datetime.now(tz=ZoneInfo(timezone_name))
        return now >= self.start_date

    @property
    def start_due_date_delta(self) -> timedelta | None:
        """
        Calculate the difference between start date and due date.
        Returns None if either date is not set.
        """
        if not self.start_date or not self.due_date:
            return None
        return self.due_date - self.start_date

    @property
    def is_recurring(self) -> bool:
        """
        Check if the task is recurring based on its repeat flag.
        """
        return self.repeat_flag is not None and self.repeat_flag != "None"

    @property
    def repeat_days(self) -> int | None:
        """
        Get the frequency of the recurrence if it is recurring.
        """
        if not self.repeat_flag:
            return None
        value_str = self.repeat_flag.split("INTERVAL=")[1].split(";")[0]
        freq_str = self.repeat_flag.split("FREQ=")[1].split(";")[0]
        match freq_str:
            case "DAILY":
                freq_days = 1
            case "WEEKLY":
                freq_days = 7
            case "MONTHLY":
                freq_days = 30
            case "YEARLY":
                freq_days = 365
            case _:
                log.warning(f"Unknown frequency: {freq_str}. Returning None.")
                return None
        if not value_str.isdigit():
            log.warning(f"Invalid value in repeat flag: {value_str}. Returning None.")
            return None
        return freq_days * int(value_str)

    @property
    def next_recurring_due_date(self) -> datetime | None:
        """
        Get the next recurring date for the task if it is recurring.
        """
        if not self.is_recurring or not self.repeat_from or not self.repeat_days:
            return None

        today = datetime.now(tz=ZoneInfo(self.time_zone)).today()
        if self.repeat_from == "1":  # Repeat from completion date
            return today + timedelta(days=self.repeat_days)
        elif self.repeat_from == "2":  # Repeat from due date
            if self.due_date:
                return self.due_date + timedelta(days=self.repeat_days)
            else:
                return None
        else:
            return None

    def mark_recurring_complete(self):
        """
        Modify Task if the task is a complete recurring task.
        """
        if not self.is_recurring or not self.next_recurring_due_date:
            return

        delta = self.start_due_date_delta
        self.due_date = self.next_recurring_due_date
        self.start_date = self.due_date - delta
        self.status = 0  # Reset status to active
        self.repeat_first_date = self.start_date

    @staticmethod
    def to_camel(field_name: str) -> str:
        """
        Convert a snake_case field name into camelCase.
        E.g. 'checkin_stamp' -> 'checkinStamp'
        """
        parts = field_name.split("_")
        return parts[0] + "".join(word.capitalize() for word in parts[1:])

    model_config = ConfigDict(
        alias_generator=to_camel,
        json_encoders={datetime: format_datetime_custom},
        populate_by_name=True,
        extra="allow",
    )


class TickTickProject(BaseModel):
    id: str
    name: str
    is_owner: bool
    in_all: bool
    group_id: str | None
    muted: bool

    @staticmethod
    def to_camel(field_name: str) -> str:
        """
        Convert a snake_case field name into camelCase.
        E.g. 'checkin_stamp' -> 'checkinStamp'
        """
        parts = field_name.split("_")
        return parts[0] + "".join(word.capitalize() for word in parts[1:])

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")


def create_task(task: TickTickTask, headers: dict | None = None) -> requests.Response:
    payload = {"add": [task.model_dump(mode="json", by_alias=True, exclude_unset=False)]}
    return requests.post(_URL_CREATE_TASK, data=json.dumps(payload), headers=_headers(headers))


def complete_task(task_id: str, project_id: str, headers: dict | None = None) -> requests.Response:
    return change_task_status(task_id, project_id, status=2, headers=headers)


def change_task_status(
    task_id: str, project_id: str, status: int, headers: dict | None = None
) -> requests.Response:
    task = {"id": task_id, "projectId": project_id, "status": status}
    payload = {"update": [task]}
    return requests.post(_URL_CREATE_TASK, data=json.dumps(payload), headers=_headers(headers))


def update_task(task: TickTickTask, headers: dict | None = None) -> requests.Response:
    """Update a task in TickTick. The task must have an id and project_id set."""
    if not task.id or not task.project_id:
        raise ValueError("Task must have an id and project_id to be updated.")

    task_data = task.model_dump(mode="json", by_alias=True, exclude_unset=False)
    payload = {"update": [task_data]}
    return requests.post(_URL_CREATE_TASK, data=json.dumps(payload), headers=_headers(headers))


def get_all_tasks(
    headers: dict | None = None, raise_exception: bool = False
) -> list[TickTickTask] | None:
    """Deprecated: use `get_active_tasks` instead."""
    warnings.warn(
        "get_all_tasks is deprecated. Use get_active_tasks instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_active_tasks(headers=headers, raise_exception=raise_exception)


def get_active_tasks(
    headers: dict | None = None, raise_exception: bool = False
) -> list[TickTickTask] | None:
    """Get all active TickTick tasks."""
    response = requests.get(url=_URL_GET_TASKS, headers=_headers(headers)).json()
    tasks_data = response.get("syncTaskBean", {}).get("update", None)
    if tasks_data is None:
        _log_or_raise("Getting Tasks failed", raise_exception)
        return None
    return [TickTickTask(**task_data) for task_data in tasks_data]


def get_abandoned_tasks(
    headers: dict | None = None, raise_exception: bool = False
) -> list[TickTickTask] | None:
    """Get all TickTick tasks with status -1 (wont do)."""
    tasks_data = requests.get(url=_URL_ABANDONED_TASKS, headers=_headers(headers)).json()
    if tasks_data is None:
        _log_or_raise("Getting Wont-Do Tasks failed", raise_exception)
        return None
    return [TickTickTask(**task) for task in tasks_data if task["status"] == -1]


def get_all_projects(
    headers: dict | None = None, raise_exception: bool = False
) -> dict[str, TickTickProject] | None:
    response = requests.get(url=_URL_GET_PROJECTS, headers=_headers(headers)).json()
    if response is None:
        _log_or_raise("Getting Projects failed", raise_exception)
        return None
    projects = [TickTickProject(**project_data) for project_data in response]
    return {project.id: project for project in projects}


def add_project_properties_to_tasks(
    tasks: list[TickTickTask], projects: dict[str, TickTickProject]
) -> list[TickTickTask]:
    """Fill in `project_name`/`show_in_all`/`project_muted` on each task from
    a `projects` map, as returned by `get_all_projects()`."""
    for task in tasks:
        try:
            if "inbox" in task.project_id:
                task.project_name = "INBOX"
                task.show_in_all = True
                task.project_muted = False
            else:
                project = projects[task.project_id]
                task.project_name = project.name
                task.show_in_all = project.in_all
                task.project_muted = project.muted
        except Exception as e:
            log.warning(f"Project of task {task.title} not found: {e!s}")
    return tasks


def _log_or_raise(error_msg: str, raise_exception: bool) -> None:
    if raise_exception:
        raise ValueError(error_msg)
    log.error(error_msg)


if __name__ == "__main__":
    auth = get_authenticated_ticktick_headers(headless=False)
    task_ = TickTickTask(
        title="TESTABNSDF", project_id="6864f1ae8f08304bcb05ecba", due_date=get_today_due_date()
    )
    projects_ = get_all_projects(headers=auth)
    tasks_ = get_active_tasks(headers=auth)
    if not tasks_:
        raise ValueError("No active tasks found. Please create a task first.")
    recurring_tasks = [t for t in tasks_ if t.is_recurring]
    recurr_task = recurring_tasks[0]
    recurr_task.mark_recurring_complete()

    ab_tasks = get_abandoned_tasks(headers=auth)

    resp1 = create_task(task=task_, headers=auth)
    task_.status = -1
    resp2 = update_task(task=task_, headers=auth)
    resp2 = complete_task(task_id=task_.id, project_id=task_.project_id, headers=auth)
