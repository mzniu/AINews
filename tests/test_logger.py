"""日志路径解析测试"""

import os
from pathlib import Path

from src.utils.logger import _resolve_log_path


def test_resolve_log_path_uses_pid_on_windows(monkeypatch):
    monkeypatch.setattr(os, "getpid", lambda: 4242)
    monkeypatch.setattr("src.utils.logger.sys.platform", "win32")
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    assert Path(_resolve_log_path("data/logs/ainews.log")) == Path("data/logs/ainews.4242.log")


def test_resolve_log_path_explicit_pid_placeholder(monkeypatch):
    monkeypatch.setattr(os, "getpid", lambda: 99)
    assert _resolve_log_path("data/logs/run.{pid}.log") == "data/logs/run.99.log"
