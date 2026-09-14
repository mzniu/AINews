"""Cross-process Playwright browser lock."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from loguru import logger

from src.utils.config import Config

DEFAULT_LOCK_TIMEOUT_SEC = 120.0
DEFAULT_STALE_LOCK_SEC = 600.0

_process_browser_mutex = threading.Lock()


class BrowserLockTimeout(TimeoutError):
    pass


def _lock_path() -> Path:
    return Config.DATA_DIR / ".playwright.lock"


def _is_process_alive_win32(pid: int) -> bool:
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def _is_process_alive(pid: int) -> bool:
    """Check whether a PID still refers to a running process."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            return _is_process_alive_win32(pid)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, SystemError):
        return False
    else:
        return True


def _read_lock_info(lock_path: Path) -> dict | None:
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    if raw.isdigit():
        return {"pid": int(raw)}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def break_stale_browser_lock(*, stale_sec: float = DEFAULT_STALE_LOCK_SEC) -> bool:
    """Remove orphan lock file when owner process is gone or lock is too old."""
    lock_path = _lock_path()
    if not lock_path.exists():
        return False

    info = _read_lock_info(lock_path)
    pid = int((info or {}).get("pid") or 0)
    age_sec = max(0.0, time.time() - lock_path.stat().st_mtime)

    if pid and _is_process_alive(pid) and age_sec < stale_sec:
        return False

    try:
        lock_path.unlink(missing_ok=True)
        logger.warning(
            "Removed stale Playwright lock (pid=%s, age=%.0fs)",
            pid or "unknown",
            age_sec,
        )
        return True
    except OSError:
        return False


@contextmanager
def browser_lock(*, timeout_sec: float = DEFAULT_LOCK_TIMEOUT_SEC) -> Iterator[None]:
    """Serialize Playwright usage within this process and across worker processes."""
    if not _process_browser_mutex.acquire(timeout=timeout_sec):
        raise BrowserLockTimeout(
            f"无法在 {timeout_sec}s 内获取 Playwright 锁（本机另有发布/检测任务进行中）"
        )

    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_sec
    fd: int | None = None
    acquired_file_lock = False
    try:
        while time.time() < deadline:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                acquired_file_lock = True
                break
            except FileExistsError:
                break_stale_browser_lock()
                time.sleep(0.5)
        if not acquired_file_lock:
            holder = _read_lock_info(lock_path)
            pid = (holder or {}).get("pid")
            raise BrowserLockTimeout(
                f"无法在 {timeout_sec}s 内获取 Playwright 锁"
                + (f"（当前持有者 pid={pid}）" if pid else "")
            )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(json.dumps({"pid": os.getpid(), "started_at": time.time()}))
        try:
            yield
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        _process_browser_mutex.release()
