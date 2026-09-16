"""Beijing (Asia/Shanghai) time helpers for display and API payloads."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def to_beijing(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return ensure_aware(dt).astimezone(BEIJING_TZ)


def format_beijing_datetime(dt: datetime | None, *, with_seconds: bool = True) -> str:
    if dt is None:
        return ""
    moment = to_beijing(dt)
    assert moment is not None
    if with_seconds:
        return moment.strftime("%Y-%m-%d %H:%M:%S")
    return moment.strftime("%Y-%m-%d %H:%M")


def as_beijing_wallclock(dt: datetime | None) -> datetime | None:
    """Mark naive datetimes that already store Beijing wall time (e.g. crawler published_at)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BEIJING_TZ)
    return dt.astimezone(BEIJING_TZ)


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def beijing_now_iso() -> str:
    return beijing_now().isoformat(timespec="seconds")
