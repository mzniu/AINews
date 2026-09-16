from datetime import datetime, timezone

from src.utils.beijing_time import as_beijing_wallclock, format_beijing_datetime, beijing_now_iso


def test_format_beijing_datetime_from_utc_naive():
    text = format_beijing_datetime(datetime(2026, 8, 6, 23, 44, 5))
    assert text == "2026-08-07 07:44:05"


def test_format_beijing_datetime_from_utc_aware():
    text = format_beijing_datetime(datetime(2026, 8, 6, 23, 44, 5, tzinfo=timezone.utc))
    assert text == "2026-08-07 07:44:05"


def test_as_beijing_wallclock_does_not_shift_naive_clock():
    marked = as_beijing_wallclock(datetime(2026, 8, 11, 21, 57, 46))
    assert marked is not None
    assert marked.isoformat() == "2026-08-11T21:57:46+08:00"


def test_beijing_now_iso_has_offset():
    iso = beijing_now_iso()
    assert "+08:00" in iso
