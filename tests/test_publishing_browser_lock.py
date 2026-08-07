import os
from unittest.mock import patch

import pytest

from services.publishing.browser_lock import (
    BrowserLockTimeout,
    break_stale_browser_lock,
    browser_lock,
)


def test_browser_lock_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.publishing.browser_lock.Config",
        type("C", (), {"ROOT_DIR": tmp_path})(),
    )
    with browser_lock(timeout_sec=2):
        assert (tmp_path / "data" / ".playwright.lock").exists()
    assert not (tmp_path / "data" / ".playwright.lock").exists()


def test_break_stale_browser_lock_removes_orphan(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.publishing.browser_lock.Config",
        type("C", (), {"ROOT_DIR": tmp_path})(),
    )
    lock_path = tmp_path / "data" / ".playwright.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text('{"pid": 999999999}', encoding="utf-8")
    assert break_stale_browser_lock(stale_sec=600) is True
    assert not lock_path.exists()


def test_browser_lock_recovers_stale_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.publishing.browser_lock.Config",
        type("C", (), {"ROOT_DIR": tmp_path})(),
    )
    lock_path = tmp_path / "data" / ".playwright.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(f'{{"pid": {os.getpid()}}}', encoding="utf-8")

    with patch("services.publishing.browser_lock._is_process_alive", return_value=False):
        with browser_lock(timeout_sec=2):
            pass

    assert not lock_path.exists()


def test_browser_lock_timeout_when_held(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.publishing.browser_lock.Config",
        type("C", (), {"ROOT_DIR": tmp_path})(),
    )
    lock_path = tmp_path / "data" / ".playwright.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(f'{{"pid": {os.getpid()}}}', encoding="utf-8")

    with patch("services.publishing.browser_lock._is_process_alive", return_value=True):
        with pytest.raises(BrowserLockTimeout):
            with browser_lock(timeout_sec=0.6):
                pass
