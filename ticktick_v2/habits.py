from datetime import datetime, timedelta
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict

from ticktick_v2.cookies_login import get_authenticated_ticktick_headers
from ticktick_v2.utils.logger import create_logger
from ticktick_v2.utils.time_utils import get_datetime_now_utc_millisecond
from ticktick_v2.web.api_request import post_request

log = create_logger("TickTick Habits")

STATUS_CODES = {0: "Not completed", 1: "Failed", 2: "Completed"}
_URL_HABITS = "https://api.ticktick.com/api/v2/habits"
_URL_BATCH_CHECKIN = "https://api.ticktick.com/api/v2/habitCheckins/batch"
_URL_QUERY_CHECKIN = "https://api.ticktick.com/api/v2/habitCheckins/query"

# TODO: dataclass for habit metadata


def _headers(headers: dict | None) -> dict:
    """Every function here takes an optional `headers` so a caller doing many
    requests can fetch it once with `get_authenticated_ticktick_headers()` and
    pass it in, instead of re-authenticating per call. If omitted, it's
    fetched fresh, which is cheap once cookies are cached on disk."""
    return headers if headers is not None else get_authenticated_ticktick_headers()


class TickTickHabitEntry(BaseModel):
    habit_id: str
    checkin_stamp: int
    goal: float | int
    value: float | int
    status: Literal[0, 1, 2, 3]
    id: str | None = None
    checkin_time: str | None = None
    op_time: str | None = None

    @classmethod
    def init(
            cls,
            habit_id: str,
            date_stamp: int,
            habit_goal: int,
            status: Literal[0, 1, 2, 3] | None = None,
            value: float | None = None,
    ) -> "TickTickHabitEntry":

        assert status is not None or value is not None, "You need to provide either status or value"

        if value is None:
            value = habit_goal if status == 2 else 0
        if status is None:
            status = 2 if value >= habit_goal else 0

        now = get_datetime_now_utc_millisecond()
        return cls(
            checkin_stamp=date_stamp,
            checkin_time=now,
            goal=habit_goal,
            habit_id=habit_id,
            op_time=now,
            status=status,
            value=value,
        )

    @staticmethod
    def to_camel(field_name: str) -> str:
        """
        Convert a snake_case field name into camelCase.
        E.g. 'checkin_stamp' -> 'checkinStamp'
        """
        parts = field_name.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:])

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow"
    )


def get_all_habits_metadata(headers: dict | None = None) -> tuple[dict, dict]:
    """Get the metadata of all habits, keyed by id, and a name -> id mapping.

    Pass the returned tuple back into `post_checkin`/`get_all_checkins` as
    `habits_metadata` to avoid re-fetching it on every call."""
    habit_data = requests.get(url=_URL_HABITS, headers=_headers(headers)).json()
    if "errorId" in habit_data:
        error_message = f"Error loading habits: {habit_data}"
        log.error(error_message)
        raise ValueError(error_message)

    habits_metadata = {habit["id"]: habit for habit in habit_data if 'id' in habit}
    habit_name_to_id_mapping = {habit["name"]: habit["id"] for habit in habit_data}
    return habits_metadata, habit_name_to_id_mapping


def _init_habit_entry(
        habit_name: str,
        date_stamp: int,
        habits_metadata: tuple[dict, dict],
        status: Literal[0, 1, 2] | None = None,
        value: float | None = None,
) -> TickTickHabitEntry:
    """Collect all data needed for a single habit checkin."""
    habits, habit_ids = habits_metadata
    habit_id = habit_ids[habit_name]
    habit_goal = int(habits[habit_id]["goal"])
    return TickTickHabitEntry.init(
        habit_id=habit_id,
        date_stamp=date_stamp,
        status=status,
        value=value,
        habit_goal=habit_goal,
    )


def post_checkin(
        habit_name: str,
        date_stamp: int,
        status: int | None = None,
        value: float | None = None,
        headers: dict | None = None,
        habits_metadata: tuple[dict, dict] | None = None,
        raise_exception: bool = False,
     ) -> None:
    """Post a single habit checkin to the TickTick API.

    Args:
        habit_name: Name of the habit to check in
        date_stamp: Date of the check-in, in the format YYYYMMDD
        status: Status of the check-in. 0: Not completed, 1: Failed, 2: Completed
        value: The value amount to check in. for habits who require multiple units
        headers: Auth headers; fetched fresh if omitted
        habits_metadata: Result of `get_all_habits_metadata()`; fetched fresh if omitted
        raise_exception: Flag to raise exception in case of an error
    """
    headers = _headers(headers)
    habits_metadata = habits_metadata or get_all_habits_metadata(headers)
    checkin_entry = _init_habit_entry(habit_name, date_stamp, habits_metadata, status, value)
    log.debug(f"Checking {habit_name} on {date_stamp} as {status}: {value}/{checkin_entry.goal}")

    # create payload depending on if a checkin for that day already exists
    existing_checkin_entry = get_checkin(checkin_entry.habit_id, date_stamp, headers=headers)
    payload: dict[str, list[dict[str, str | int]]] = {"add": [], "update": [], "delete": []}

    if existing_checkin_entry:
        checkin_entry.id = existing_checkin_entry.id
        payload["update"].append(checkin_entry.model_dump(by_alias=True))
    else:
        payload["add"].append(checkin_entry.model_dump(by_alias=True))

    response = post_request(url=_URL_BATCH_CHECKIN, payload=payload, headers=headers)
    if not response and raise_exception:
        raise ValueError(f"Error posting Habit Checkin: {response}")


def get_checkin(
        habit_id: str,
        date_stamp: int,
        headers: dict | None = None,
        raise_exception: bool = False,
) -> TickTickHabitEntry | None:
    """
    Retrieve a single checkin entry for a habit on a specific date, or None if not found
    """
    date = datetime.strptime(str(date_stamp), "%Y%m%d")
    after_stamp = int((date - timedelta(days=1)).strftime("%Y%m%d"))
    payload = {"habitIds": [habit_id], "afterStamp": after_stamp}
    response = post_request(url=_URL_QUERY_CHECKIN, payload=payload, headers=_headers(headers))

    if response is None or response.get('checkins', None) is None:
        error_msg = f"No or malformed response from TickTick API for get_checkin: {response}"
        log.error(error_msg)
        if raise_exception:
            raise ValueError(error_msg)
        return None

    all_entries = response.get('checkins', {})
    habit_entries = all_entries.get(habit_id, [])
    for entry in habit_entries:
        if entry.get("checkinStamp", -1) == int(date_stamp):
            return TickTickHabitEntry(**entry)

    return None


def get_all_checkins(
        after_stamp: int = 19700101,
        habit_names: list[str] | str | None = None,
        headers: dict | None = None,
        habits_metadata: tuple[dict, dict] | None = None,
        raise_exception: bool = False,
) -> dict[str, list[TickTickHabitEntry]] | None:
    """Get all checkins of all habits (or those provided), after a specific date stamp."""
    headers = _headers(headers)
    habits, habit_ids = habits_metadata or get_all_habits_metadata(headers)

    if not habit_names:
        habits_ids = list(habit_ids.values())
    else:
        habit_names = [habit_names] if isinstance(habit_names, str) else habit_names
        habits_ids = [habit_ids[habit] for habit in habit_names]

    payload = {"habitIds": habits_ids, "afterStamp": after_stamp}
    response = post_request(url=_URL_QUERY_CHECKIN, payload=payload, headers=headers)

    if response is None or response.get('checkins', None) is None:
        error_msg = f"No or malformed response from TickTick API for get_all_checkins: {response}"
        log.error(error_msg)
        if raise_exception:
            raise ValueError(error_msg)
        return None

    all_habits_entries = response.get("checkins", {})
    all_habits_entries_parsed = {}
    for habit_id, habits_entries in all_habits_entries.items():
        habit_name = habits[habit_id]["name"]
        habits_entries_objs = [
            TickTickHabitEntry(**entry, habitName=habit_name) for entry in habits_entries
        ]
        all_habits_entries_parsed[habit_id] = habits_entries_objs

    return all_habits_entries_parsed


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    auth = get_authenticated_ticktick_headers()
    single_checkin = get_checkin(habit_id='64f08ac16fc6ff16c2d1f3eb', date_stamp=20250520, headers=auth)
    checkins = get_all_checkins(after_stamp=20220101, headers=auth)
    print(checkins)
