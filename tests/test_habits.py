import pytest

from ticktick_v2.habits import TickTickHabitEntry


def test_init_from_status_completed_fills_value_with_goal():
    entry = TickTickHabitEntry.init(
        habit_id="habit123", date_stamp=20260101, habit_goal=4, status=2
    )
    assert entry.value == 4
    assert entry.status == 2


def test_init_from_status_not_completed_zeros_value():
    entry = TickTickHabitEntry.init(
        habit_id="habit123", date_stamp=20260101, habit_goal=4, status=0
    )
    assert entry.value == 0


def test_init_from_value_derives_completed_status():
    entry = TickTickHabitEntry.init(
        habit_id="habit123", date_stamp=20260101, habit_goal=4, value=4
    )
    assert entry.status == 2


def test_init_from_value_below_goal_derives_not_completed():
    entry = TickTickHabitEntry.init(
        habit_id="habit123", date_stamp=20260101, habit_goal=4, value=1
    )
    assert entry.status == 0


def test_init_requires_status_or_value():
    with pytest.raises(AssertionError):
        TickTickHabitEntry.init(habit_id="habit123", date_stamp=20260101, habit_goal=4)


def test_entry_camelcase_alias():
    entry = TickTickHabitEntry.init(
        habit_id="habit123", date_stamp=20260101, habit_goal=4, status=2
    )
    dumped = entry.model_dump(by_alias=True)
    assert dumped["habitId"] == "habit123"
    assert dumped["checkinStamp"] == 20260101
