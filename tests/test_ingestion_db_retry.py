"""SQLite retry helper tests."""
import pytest
from sqlalchemy.exc import OperationalError

from services.ingestion.db_retry import is_sqlite_locked, run_with_sqlite_retry


def test_is_sqlite_locked():
    assert is_sqlite_locked(OperationalError("database is locked", {}, None))
    assert is_sqlite_locked(OperationalError("database is busy", {}, None))
    assert not is_sqlite_locked(OperationalError("no such table", {}, None))


def test_run_with_sqlite_retry_recovers():
    calls = {"count": 0}

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OperationalError("database is locked", {}, None)
        return "ok"

    assert run_with_sqlite_retry(flaky, attempts=3, base_delay=0) == "ok"
    assert calls["count"] == 2
