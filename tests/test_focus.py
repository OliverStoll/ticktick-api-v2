from ticktick_v2.focus import TickTickFocusTime


def test_focus_time_computes_duration_from_start_end():
    focus = TickTickFocusTime(
        id="f1",
        type=1,
        startTime="2026-01-01T09:00:00+00:00",
        endTime="2026-01-01T10:30:00+00:00",
        status=1,
        pauseDuration=0,
    )
    assert focus.total_duration == 90


def test_focus_time_parses_string_datetimes():
    focus = TickTickFocusTime(
        id="f1",
        type=0,
        startTime="2026-01-01T09:00:00+00:00",
        endTime="2026-01-01T09:25:00+00:00",
        status=1,
        pauseDuration=0,
    )
    assert focus.start_time.year == 2026
    assert focus.start_time.month == 1


def test_focus_time_camelcase_alias():
    focus = TickTickFocusTime(
        id="f1",
        type=1,
        startTime="2026-01-01T09:00:00+00:00",
        endTime="2026-01-01T09:25:00+00:00",
        status=1,
        pauseDuration=5,
    )
    dumped = focus.model_dump(by_alias=True)
    assert dumped["pauseDuration"] == 5
    assert dumped["totalDuration"] == 25
