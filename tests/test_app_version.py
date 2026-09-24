from __future__ import annotations

import os

from src.app_version import get_app_version


def test_get_app_version_prefers_env(monkeypatch):
    monkeypatch.setenv("AINEWS_APP_VERSION", "9.9.9")
    assert get_app_version() == "9.9.9"
