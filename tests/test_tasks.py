from datetime import datetime, timezone

from ticktick_v2.tasks import (
    TickTickTask,
    current_utc_iso,
    format_datetime_custom,
    generate_id,
    get_today_due_date,
)


def test_generate_id_is_hex_and_stable_length():
    ids = {generate_id() for _ in range(50)}
    assert len(ids) == 50, "ids should be unique"
    for task_id in ids:
        assert len(task_id) == 24
        int(task_id, 16)  # raises if not valid hex


def test_current_utc_iso_format():
    value = current_utc_iso()
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.000+0000")
    assert parsed.tzinfo is None  # naive, matches the TickTick wire format


def test_get_today_due_date_is_today():
    value = get_today_due_date()
    assert value.startswith(datetime.today().strftime("%Y-%m-%d"))


def test_format_datetime_custom_converts_to_utc():
    dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert format_datetime_custom(dt) == "2026-01-01T12:00:00.000+0000"


def test_task_default_id_and_title_required():
    task = TickTickTask(title="Buy milk", project_id="inbox123")
    assert task.title == "Buy milk"
    assert len(task.id) == 24
    assert task.status == 0


def test_task_camelcase_alias_round_trip():
    task = TickTickTask(title="Buy milk", project_id="inbox123")
    dumped = task.model_dump(by_alias=True)
    assert "projectId" in dumped
    assert "project_id" not in dumped


def test_repeat_days_for_known_frequencies():
    weekly = TickTickTask(
        title="t", project_id="p", repeat_flag="RRULE:FREQ=WEEKLY;INTERVAL=2"
    )
    assert weekly.repeat_days == 14


def test_repeat_days_returns_none_for_unknown_frequency_without_crashing():
    # regression test: this used to raise AttributeError because the model
    # called `self.log`, a logger that only exists on the handler class, not
    # on the pydantic model itself
    odd = TickTickTask(title="t", project_id="p", repeat_flag="RRULE:FREQ=HOURLY;INTERVAL=1")
    assert odd.repeat_days is None
