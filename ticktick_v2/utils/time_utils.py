from datetime import datetime, timedelta, timezone


def get_datetime_now_utc_millisecond() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + ".000+0000"


def get_timestamp_from_offset(days_offset: int) -> int:
    """ Returns the unit-time timestamp of now minus the offset"""
    offset_date = datetime.now() - timedelta(days=days_offset)
    return int(offset_date.timestamp())