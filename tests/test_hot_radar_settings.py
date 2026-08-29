"""Tests for hot radar settings merge/save."""
from __future__ import annotations

from services.ingestion.hot_radar_settings import (
    load_merged_hot_radar_config,
    public_hot_radar_settings,
    save_hot_radar_settings,
)


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
