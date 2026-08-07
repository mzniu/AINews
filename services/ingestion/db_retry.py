"""SQLite lock retry helpers for ingestion."""
from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

from sqlalchemy.exc import OperationalError

T = TypeVar("T")

_WRITE_LOCK = threading.RLock()


def is_sqlite_locked(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database is busy" in message


def run_with_sqlite_retry(
    action: Callable[[], T],
    *,
    attempts: int = 12,
    base_delay: float = 0.2,
) -> T:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return action()
        except OperationalError as exc:
            if not is_sqlite_locked(exc):
                raise
            last_exc = exc
            time.sleep(base_delay * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def serialized_sqlite_write(
    action: Callable[[], T],
    *,
    attempts: int = 12,
    base_delay: float = 0.2,
) -> T:
    """Serialize SQLite writes within this process to reduce lock contention."""
    with _WRITE_LOCK:
        return run_with_sqlite_retry(action, attempts=attempts, base_delay=base_delay)
