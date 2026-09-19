"""M0c: industry onboarding and active L2 selection APIs."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web_server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    monkeypatch.delenv("AINES_DEV_MODE", raising=False)
    monkeypatch.delenv("AINEWS_ACTIVE_INDUSTRY_ID", raising=False)
    return TestClient(app)


def test_me_industry_reports_needs_onboarding_without_profile(client):
    response = client.get("/api/me/industry")
    assert response.status_code == 200
    body = response.json()
    assert body["needs_onboarding"] is True
    assert body["active_industry_id"] is None


def test_put_me_industry_activates_l2_and_completes_onboarding(client):
    response = client.put(
        "/api/me/industry",
        json={"active_industry_id": "finance/macro"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["active_industry_id"] == "finance/macro"
    assert body["display_name"] == "宏观财经"
    assert body["needs_onboarding"] is False
    assert body["pack_version"] == "1.0.0"

    again = client.get("/api/me/industry")
    assert again.json()["needs_onboarding"] is False


def test_put_me_industry_rejects_unknown_l2(client):
    response = client.put(
        "/api/me/industry",
        json={"active_industry_id": "unknown/field"},
    )
    assert response.status_code == 400


def test_dev_mode_skips_onboarding_requirement(client, monkeypatch):
    monkeypatch.setenv("AINES_DEV_MODE", "1")
    response = client.get("/api/me/industry")
    assert response.status_code == 200
    assert response.json()["needs_onboarding"] is False
    assert response.json()["active_industry_id"] == "tech/ai"
