import os

from services.publishing.worker import get_publish_worker_mode


def test_default_mode_is_embedded(monkeypatch):
    monkeypatch.delenv("PUBLISH_WORKER_MODE", raising=False)
    assert get_publish_worker_mode() == "embedded"


def test_separate_mode(monkeypatch):
    monkeypatch.setenv("PUBLISH_WORKER_MODE", "separate")
    assert get_publish_worker_mode() == "separate"


def test_invalid_mode_falls_back_to_embedded(monkeypatch):
    monkeypatch.setenv("PUBLISH_WORKER_MODE", "invalid")
    assert get_publish_worker_mode() == "embedded"
