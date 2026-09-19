"""M0b: hot radar respects effective pack board enablement."""
from __future__ import annotations

import pytest
import yaml

from services.industry.config_loader import (
    build_effective_config,
    refresh_effective_cache,
    write_effective_cache,
)
from services.industry.constants import DEFAULT_INDUSTRY_ID
from services.ingestion.hot_radar_settings import (
    enabled_boards,
    load_merged_hot_radar_config,
    public_hot_radar_settings,
    save_hot_radar_settings,
)


def _seed_effective(tmp_path, monkeypatch: pytest.MonkeyPatch, industry_id: str = DEFAULT_INDUSTRY_ID):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", industry_id)
    write_effective_cache(
        industry_id,
        build_effective_config(industry_id),
        manifest_hash="test",
    )
    return get_data_dir


def test_enabled_boards_follow_effective_pack(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _seed_effective(tmp_path, monkeypatch)
    boards = enabled_boards()
    board_ids = {b["id"] for b in boards}
    assert "sina_ai" in board_ids
    assert "kr36_ai" in board_ids
    assert len(board_ids) == 7


def test_selected_boards_override_pack_add(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _seed_effective(tmp_path, monkeypatch)
    local_path = tmp_path / "hot_radar.local.yaml"
    local_path.write_text(
        yaml.dump(
            {
                "selected_by_industry": {
                    DEFAULT_INDUSTRY_ID: [{"id": "ithome_ai", "enabled": True}],
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)

    cfg = load_merged_hot_radar_config()
    assert {b["id"] for b in enabled_boards(cfg)} == {"ithome_ai"}

    refresh_effective_cache(DEFAULT_INDUSTRY_ID)
    cfg_after = load_merged_hot_radar_config()
    assert {b["id"] for b in enabled_boards(cfg_after)} == {"ithome_ai"}


def test_empty_selected_does_not_fall_back_to_pack(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _seed_effective(tmp_path, monkeypatch)
    local_path = tmp_path / "hot_radar.local.yaml"
    local_path.write_text(
        yaml.dump({"selected_by_industry": {DEFAULT_INDUSTRY_ID: []}}, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    cfg = load_merged_hot_radar_config()
    assert enabled_boards(cfg) == []
    public = public_hot_radar_settings()
    assert public["boards"] == []
    assert public["selection_source"] == "user"


def test_selected_disabled_board_stays_in_public_not_enabled(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _seed_effective(tmp_path, monkeypatch)
    local_path = tmp_path / "hot_radar.local.yaml"
    local_path.write_text(
        yaml.dump(
            {
                "selected_by_industry": {
                    DEFAULT_INDUSTRY_ID: [{"id": "sina_ai", "enabled": False}],
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    cfg = load_merged_hot_radar_config()
    assert enabled_boards(cfg) == []
    public = public_hot_radar_settings()
    assert public["boards"][0]["id"] == "sina_ai"
    assert public["boards"][0]["enabled"] is False


def test_selected_new_board_not_in_pack_add_is_enabled(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _seed_effective(tmp_path, monkeypatch)
    local_path = tmp_path / "hot_radar.local.yaml"
    local_path.write_text(
        yaml.dump(
            {
                "boards": [
                    {
                        "id": "WnBe01o371",
                        "hashid": "WnBe01o371",
                        "name": "微信",
                        "display": "24h热文榜",
                    }
                ],
                "selected_by_industry": {
                    DEFAULT_INDUSTRY_ID: [{"id": "WnBe01o371", "enabled": True}],
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        build_effective_config(DEFAULT_INDUSTRY_ID),
        manifest_hash="test",
    )
    cfg = load_merged_hot_radar_config()
    ids = {b["id"] for b in enabled_boards(cfg)}
    assert ids == {"WnBe01o371"}


def test_public_without_selected_shows_pack_add_subset(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _seed_effective(tmp_path, monkeypatch, "finance/macro")
    local_path = tmp_path / "hot_radar.local.yaml"
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    public = public_hot_radar_settings()
    assert public["selection_source"] == "pack"
    assert public["active_industry_id"] == "finance/macro"
    assert {b["id"] for b in public["boards"]} == {"sina_ai"}


def test_save_roundtrip_maps_hashid_and_sets_selection_source_user(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    local_path = tmp_path / "hot_radar.local.yaml"
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    _seed_effective(tmp_path, monkeypatch)
    saved = save_hot_radar_settings(
        {
            "boards": [
                {
                    "hashid": "47o8762eMm",
                    "name": "IT之家",
                    "display": "AI",
                    "enabled": True,
                }
            ]
        }
    )
    assert saved["selection_source"] == "user"
    assert saved["boards"][0]["id"] == "ithome_ai"
    assert {b["id"] for b in enabled_boards()} == {"ithome_ai"}


def test_save_does_not_drop_other_industry_selected(tmp_path, monkeypatch: pytest.MonkeyPatch):
    local_path = tmp_path / "hot_radar.local.yaml"
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    _seed_effective(tmp_path, monkeypatch)
    local_path.write_text(
        yaml.dump(
            {
                "selected_by_industry": {
                    "finance/macro": [{"id": "sina_ai", "enabled": True}],
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    save_hot_radar_settings(
        {
            "boards": [
                {
                    "id": "ithome_ai",
                    "hashid": "47o8762eMm",
                    "name": "IT之家",
                    "display": "AI",
                    "enabled": True,
                }
            ]
        }
    )
    saved_local = yaml.safe_load(local_path.read_text(encoding="utf-8"))
    assert saved_local["selected_by_industry"]["finance/macro"][0]["id"] == "sina_ai"
    assert saved_local["selected_by_industry"][DEFAULT_INDUSTRY_ID][0]["id"] == "ithome_ai"


def test_switch_back_does_not_restore_removed_pack_board(tmp_path, monkeypatch: pytest.MonkeyPatch):
    local_path = tmp_path / "hot_radar.local.yaml"
    monkeypatch.setattr("services.ingestion.hot_radar_settings.HOT_RADAR_LOCAL_PATH", local_path)
    _seed_effective(tmp_path, monkeypatch)
    local_path.write_text(
        yaml.dump(
            {
                "selected_by_industry": {
                    DEFAULT_INDUSTRY_ID: [{"id": "ithome_ai", "enabled": True}],
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    assert {b["id"] for b in enabled_boards()} == {"ithome_ai"}

    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", "finance/macro")
    refresh_effective_cache("finance/macro")
    assert public_hot_radar_settings()["active_industry_id"] == "finance/macro"

    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)
    refresh_effective_cache(DEFAULT_INDUSTRY_ID)
    ids = {b["id"] for b in enabled_boards()}
    assert ids == {"ithome_ai"}
    assert "sina_ai" not in ids
