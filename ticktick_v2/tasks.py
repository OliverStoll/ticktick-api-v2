import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import secrets
import warnings

import requests
from requests import Response
from pydantic import BaseModel, ConfigDict, Field

from ticktick_v2.cookies_login import get_authenticated_ticktick_headers
from ticktick_v2.utils.logger import create_logger


def current_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def get_today_due_date() -> str:
    return datetime.today().strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def format_datetime_custom(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def generate_id() -> str:
    return secrets.token_hex(12)


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
                self.log.warning(f"Unknown frequency: {freq_str}. Returning None.")
                return None
        if not value_str.isdigit():
            self.log.warning(f"Invalid value in repeat flag: {value_str}. Returning None.")
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


class TicktickTaskHandler:
    log = create_logger("TickTick Task Handler")
    url_get_tasks = "https://api.ticktick.com/api/v2/batch/check/0"
    url_get_projects = "https://api.ticktick.com/api/v2/projects"
    url_create_task = "https://api.ticktick.com/api/v2/batch/task"

    def __init__(
        self,
        return_pydantic: bool = True,
        always_raise_exceptions: bool = False,
        cookies_path: str | None = None,
        username_env: str = "TICKTICK_EMAIL",
        password_env: str = "TICKTICK_PASSWORD",
        headless: bool = True,
        undetected: bool = False,
        download_driver: bool = False,
    ):
        self.headers = get_authenticated_ticktick_headers(
            cookies_path=cookies_path,
            username_env=username_env,
            password_env=password_env,
            headless=headless,
            undetected=undetected,
            download_driver=download_driver,
        )
        self.raise_exceptions = always_raise_exceptions
        self.return_pydantic = return_pydantic
        self.projects: dict[str, TickTickProject] | None = None

    def create_task(self, task: TickTickTask) -> Response:
        payload = {"add": [task.model_dump(mode="json", by_alias=True, exclude_unset=False)]}
        json_payload = json.dumps(payload)
        response = requests.post(self.url_create_task, data=json_payload, headers=self.headers)
        return response

    def complete_task(self, task_id: str, project_id: str):
        task = {
            "id": task_id,
            "projectId": project_id,
            "status": 2,
        }
        payload = {"update": [task]}
        json_payload = json.dumps(payload)
        response = requests.post(self.url_create_task, data=json_payload, headers=self.headers)
        return response

    def change_task_status(self, task_id: str, project_id: str, status: int):
        task = {
            "id": task_id,
            "projectId": project_id,
            "status": status,
        }
        payload = {"update": [task]}
        json_payload = json.dumps(payload)
        response = requests.post(self.url_create_task, data=json_payload, headers=self.headers)
        return response

    def update_task(self, task: TickTickTask):
        """
        Update a task in TickTick. The task must have an id and project_id set.
        """
        if not task.id or not task.project_id:
            raise ValueError("Task must have an id and project_id to be updated.")

        task_data = task.model_dump(mode="json", by_alias=True, exclude_unset=False)
        payload = {"update": [task_data]}
        json_payload = json.dumps(payload)
        response = requests.post(self.url_create_task, data=json_payload, headers=self.headers)
        return response

    def get_all_tasks(self) -> list[TickTickTask] | None:
        """
        Get all TickTick tasks

        Returns:
            List of TickTickTask pydantic BaseModel objects, or dicts
        """

        warnings.warn(
            "get_all_tasks is deprecated. Use get_active_tasks instead.", DeprecationWarning
        )

        response = requests.get(url=self.url_get_tasks, headers=self.headers).json()
        tasks_data = response.get("syncTaskBean", {}).get("update", None)
        if tasks_data is None:
            self.log_or_raise_error("Getting Tasks failed")
            return None

        tasks = [TickTickTask(**task_data) for task_data in tasks_data]
        tasks = self.add_project_properties_to_tasks(tasks)
        return tasks

    def get_active_tasks(self) -> list[TickTickTask] | None:
        """
        Get all TickTick tasks

        Returns:
            List of TickTickTask pydantic BaseModel objects, or dicts
        """
        response = requests.get(url=self.url_get_tasks, headers=self.headers).json()
        tasks_data = response.get("syncTaskBean", {}).get("update", None)
        if tasks_data is None:
            self.log_or_raise_error("Getting Tasks failed")
            return None

        tasks = [TickTickTask(**task_data) for task_data in tasks_data]
        tasks = self.add_project_properties_to_tasks(tasks)
        return tasks

    def get_abandoned_tasks(self) -> list[TickTickTask] | None:
        """
        Get all TickTick tasks with status -1 (wont do)

        Returns:
            List of TickTickTask pydantic BaseModel objects, or dicts
        """
        url = "https://api.ticktick.com/api/v2/project/all/closed?status=Abandoned"
        tasks_data = requests.get(url=url, headers=self.headers).json()
        if tasks_data is None:
            self.log_or_raise_error("Getting Wont-Do Tasks failed")
            return None

        wont_do_tasks = [TickTickTask(**task) for task in tasks_data if task["status"] == -1]
        return wont_do_tasks

    def get_all_projects(self) -> dict[str, TickTickProject] | None:
        response = requests.get(url=self.url_get_projects, headers=self.headers).json()
        if response is None:
            self.log_or_raise_error("Getting Projects failed")
            return None

        projects = [TickTickProject(**project_data) for project_data in response]
        projects_map = {project.id: project for project in projects}
        self.projects = projects_map

        return projects_map

    def add_project_properties_to_tasks(self, tasks: list[TickTickTask]) -> list[TickTickTask]:
        if not self.projects:
            return tasks

        for task in tasks:
            try:
                if "inbox" in task.project_id:
                    task.project_name = "INBOX"
                    task.show_in_all = True
                    task.project_muted = False
                else:
                    project = self.projects[task.project_id]
                    task.project_name = project.name
                    task.show_in_all = project.in_all
                    task.project_muted = project.muted
            except Exception as e:
                self.log.warning(f"Project of task {task.title} not found: {str(e)}")

        return tasks

    def log_or_raise_error(self, error_msg: str) -> None:
        if self.raise_exceptions:
            raise ValueError(error_msg)
        else:
            self.log.error(error_msg)


if __name__ == "__main__":
    handler = TicktickTaskHandler(headless=False)
    task_ = TickTickTask(
        title="TESTABNSDF", project_id="6864f1ae8f08304bcb05ecba", due_date=get_today_due_date()
    )
    projects_ = handler.get_all_projects()
    tasks_ = handler.get_active_tasks()
    if not tasks_:
        raise ValueError("No active tasks found. Please create a task first.")
    recurring_tasks = [t for t in tasks_ if t.is_recurring]
    recurr_task = recurring_tasks[0]
    recurr_task.mark_recurring_complete()

    ab_tasks = handler.get_abandoned_tasks()

    resp1 = handler.create_task(task=task_)
    task_.status = -1
    resp2 = handler.update_task(task=task_)
    resp2 = handler.complete_task(task_id=task_.id, project_id=task_.project_id)
