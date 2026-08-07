import sys

from src.utils.uvicorn_workers import effective_uvicorn_workers


def test_effective_workers_caps_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("UVICORN_WORKERS", "4")
    assert effective_uvicorn_workers() == 1


def test_effective_workers_respects_env_on_unix(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("UVICORN_WORKERS", "2")
    assert effective_uvicorn_workers() == 2
