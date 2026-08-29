from datetime import datetime, timezone

from services.publishing.job_logging import format_log_message, format_log_timestamp


def test_format_log_timestamp_has_date_and_time():
    text = format_log_timestamp(datetime(2026, 8, 6, 23, 44, 5, tzinfo=timezone.utc))
    assert text == "2026-08-07 07:44:05"


def test_format_log_message_prefixes_timestamp():
    when = datetime(2026, 8, 6, 23, 44, 5, tzinfo=timezone.utc)
    assert format_log_message("开始发布", when=when) == "2026-08-07 07:44:05 | 开始发布"


def test_format_log_message_does_not_double_prefix():
    when = datetime(2026, 8, 6, 23, 44, 5, tzinfo=timezone.utc)
    prefixed = "2026-08-07 07:44:05 | 发布成功"
    assert format_log_message(prefixed, when=when) == prefixed
