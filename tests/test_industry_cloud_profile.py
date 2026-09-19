"""M0c cloud active-industry stub."""
from __future__ import annotations

import pytest

from services.industry.cloud_profile import put_cloud_active_industry


def test_put_cloud_active_industry_local_when_no_base(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AINEWS_CLOUD_API_BASE", raising=False)
    result = put_cloud_active_industry("tech/ai")
    assert result["source"] == "local"
    assert result["synced"] is False


def test_put_cloud_active_industry_uses_explicit_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AINEWS_CLOUD_API_BASE", "https://cloud.example")
    monkeypatch.delenv("AINEWS_CLOUD_ACCESS_TOKEN", raising=False)
    captured: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"active_industry_id":"tech/ai"}'

    def fake_urlopen(request, timeout=10.0):
        captured["auth"] = request.headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = put_cloud_active_industry("tech/ai", access_token="session-token")
    assert captured["auth"] == "Bearer session-token"
    assert result.get("synced") is True
