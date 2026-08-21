import datetime as dt
import os
from zoneinfo import ZoneInfo

import requests
from pydantic import BaseModel, ConfigDict, Field

from ticktick_v2.cookies_login import get_authenticated_ticktick_headers
from ticktick_v2.utils.logger import create_logger


class TicktickEvent(BaseModel):
    id: str = Field(..., description="Unique identifier for the event")
    title: str = Field(..., description="Title of the event")
    start_time: dt.datetime = Field(..., description="Start time of the event", alias='dueStart')
    end_time: dt.datetime = Field(..., description="End time of the event", alias='dueEnd')
    calendar_id: str = Field(..., description="ID of the calendar containing the event")
    calendar_name: str = Field(..., description="Name of the calendar containing the event")
    is_all_day: bool = Field(False, description="Indicates if the event is an all-day event")
    content: str | None = Field(None, description="Content or description of the event")

    @property
    def duration_minutes(self) -> int | None:
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            return int(duration.total_seconds() // 60)
        return None

    @property
    def is_active(self) -> bool:
        """
        Check if the event is currently active based on the current time.
        """
        timezone_name = os.getenv('TIMEZONE_NAME', 'Europe/Berlin')
        now = dt.datetime.now(tz=ZoneInfo(timezone_name))
        return self.start_time <= now <= self.end_time

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




class TicktickEventHandler:
    log = create_logger('TickTick Focus Handler')

    def __init__(
            self,
            cookies_path: str | None = None,
            always_raise_exceptions: bool = False,
            headless: bool = True,
            undetected: bool = False,
            download_driver: bool = False,
            username_env: str = 'TICKTICK_EMAIL',
            password_env: str = 'TICKTICK_PASSWORD',
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

    def get_all_events(self, calendar_names: list[str] | None = None, only_active: bool = False) -> list[TicktickEvent]:
        url = "https://api.ticktick.com/api/v2/calendar/bind/events/all"

        response = requests.get(url, headers=self.headers)
        response_data = response.json()
        all_calendars = response_data.get('events', [])
        all_events = []
        for calendar in all_calendars:
            if calendar_names and calendar['name'] not in calendar_names:
                continue

            for event in calendar.get('events', []):
                event['calendarId'] = calendar['id']
                event['calendarName'] = calendar['name']
                event_obj = TicktickEvent(**event)
                if only_active and not event_obj.is_active:
                    continue
                all_events.append(event_obj)

        return all_events



if __name__ == '__main__':
    all_events = TicktickEventHandler().get_all_events(only_active=True)