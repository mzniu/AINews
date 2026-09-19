"""Tests for hot radar settings merge/save."""
from __future__ import annotations

import pytest

from services.ingestion.hot_radar_settings import (
    load_hot_radar_local,
    load_merged_hot_radar_config,
    public_hot_radar_settings,
    save_hot_radar_settings,
)


@pytest.fixture(autouse=True)
def _disable_effective_hot_radar_overlay(monkeypatch):
    monkeypatch.setenv("AINEWS_DISABLE_EFFECTIVE_CONFIG", "1")


def test_save_hot_radar_settings_persists_key_and_boards(tmp_path, monkeypatch):
    base_path = tmp_path / "hot_radar.yaml"
    local_path = tmp_path / "hot_radar.local.yaml"
    base_path.write_text(
        """
enabled: true
provider: tophub
boards:
  - id: board_a
    hashid: hashA
    name: A
    display: 榜1
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)

    saved = save_hot_radar_settings(
        {
            "enabled": True,
            "refresh_cron": "0 7 * * *",
            "access_key": "secret-key-123456",
            "boards": [
                {
                    "id": "board_a",
                    "hashid": "hashA",
                    "name": "A",
                    "display": "榜1",
                    "enabled": False,
                }
            ],
        }
    )
    assert saved["refresh_cron"] == "0 7 * * *"
    assert saved["has_access_key"] is True

    merged = load_merged_hot_radar_config()
    assert merged["access_key"] == "secret-key-123456"
    assert merged["boards"][0]["enabled"] is False

    public = public_hot_radar_settings()
    assert public["access_key_masked"].endswith("3456")
    assert "secret-key-123456" not in public["access_key_masked"]


def test_save_hot_radar_settings_persists_discovery_toggle(tmp_path, monkeypatch):
    base_path = tmp_path / "hot_radar.yaml"
    local_path = tmp_path / "hot_radar.local.yaml"
    base_path.write_text(
        """
enabled: true
discovery:
  enabled: true
  max_rank: 10
  max_urls_per_refresh: 5
boards: []
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)

    saved = save_hot_radar_settings(
        {
            "discovery": {
                "enabled": False,
                "max_rank": 8,
                "max_urls_per_refresh": 2,
            }
        }
    )
    assert saved["discovery"]["enabled"] is False
    assert saved["discovery"]["max_rank"] == 8

    merged = load_merged_hot_radar_config()
    assert merged["discovery"]["enabled"] is False
    assert merged["discovery"]["max_urls_per_refresh"] == 2


def test_save_discovery_preserves_selected_by_industry(tmp_path, monkeypatch):
    base_path = tmp_path / "hot_radar.yaml"
    local_path = tmp_path / "hot_radar.local.yaml"
    base_path.write_text("enabled: true\nboards: []\n", encoding="utf-8")
    local_path.write_text(
        """
access_key: keep-me-key-1234
selected_by_industry:
  finance/macro:
    - id: sina_ai
      enabled: true
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", "tech/ai")

    save_hot_radar_settings(
        {
            "discovery": {
                "enabled": False,
                "max_rank": 8,
                "max_urls_per_refresh": 2,
            }
        }
    )
    saved_local = load_hot_radar_local()
    assert saved_local["access_key"] == "keep-me-key-1234"
    assert saved_local["selected_by_industry"]["finance/macro"][0]["id"] == "sina_ai"


def test_save_boards_writes_selected_and_upserts_new_catalog_row(tmp_path, monkeypatch):
    base_path = tmp_path / "hot_radar.yaml"
    local_path = tmp_path / "hot_radar.local.yaml"
    base_path.write_text(
        """
enabled: true
boards:
  - id: sina_ai
    hashid: MZd77QpdrO
    name: 新浪热榜
    display: AI榜
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    local_path.write_text(
        """
selected_by_industry:
  finance/macro:
    - id: sina_ai
      enabled: true
boards:
  - id: keepCustom01
    hashid: keepCustom01
    name: 自定义
    display: 保留
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_BASE_PATH", base_path)
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", "tech/ai")

    saved = save_hot_radar_settings(
        {
            "boards": [
                {
                    "hashid": "MZd77QpdrO",
                    "name": "不要覆盖全局名称",
                    "display": "不要覆盖",
                    "enabled": True,
                },
                {
                    "hashid": "WnBe01o371",
                    "name": "微信",
                    "display": "24h热文榜",
                    "enabled": False,
                },
            ]
        }
    )
    local = load_hot_radar_local()
    catalog_ids = {b["id"] for b in local.get("boards") or []}
    assert "keepCustom01" in catalog_ids
    assert "WnBe01o371" in catalog_ids
    assert "sina_ai" not in catalog_ids
    wechat = next(b for b in local["boards"] if b["id"] == "WnBe01o371")
    assert wechat["name"] == "微信"
    sina_selected = local["selected_by_industry"]["tech/ai"]
    assert sina_selected[0]["id"] == "sina_ai"
    assert sina_selected[1]["id"] == "WnBe01o371"
    assert sina_selected[1]["enabled"] is False
    assert local["selected_by_industry"]["finance/macro"][0]["id"] == "sina_ai"
    assert saved["selection_source"] == "user"
    assert saved["boards"][0]["id"] == "sina_ai"
    assert saved["boards"][0]["name"] == "新浪热榜"
