"""TDD tests for M0b IndustryConfigLoader and effective config cache."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from services.industry.config_loader import (
    apply_catalog_ref_ops,
    build_effective_config,
    effective_cache_path,
    load_effective_cache,
    merge_pack_layers,
    merge_scoring_pack_overrides,
    write_effective_cache,
)
from services.industry.constants import DEFAULT_INDUSTRY_ID


def test_merge_scoring_pack_overrides_replaces_keywords_block():
    base = {
        "keywords": {"tier_s": ["old"], "tier_a": ["a"]},
        "weights": {"relevance": 0.2},
    }
    pack = {
        "keywords": {"tier_s": ["大模型", "Agent"]},
        "weights": {"hot_radar": 0.06},
    }
    merged = merge_scoring_pack_overrides(base, pack)
    assert merged["keywords"] == {"tier_s": ["大模型", "Agent"]}
    assert merged["weights"] == {"relevance": 0.2, "hot_radar": 0.06}


def test_apply_catalog_ref_ops_enables_only_pack_add_refs():
    catalog = [
        {"id": "kr36_ai", "enabled": True},
        {"id": "qbitai", "enabled": True},
        {"id": "leiphone_ai", "enabled": True},
    ]
    spec = {
        "add": [{"ref": "kr36_ai"}, {"ref": "qbitai", "enabled": False}],
        "remove": [],
        "patch": [{"ref": "qbitai", "schedule_cron": "15 * * * *"}],
    }
    rows = apply_catalog_ref_ops(catalog, spec, id_key="id")
    by_id = {row["id"]: row for row in rows}
    assert by_id["kr36_ai"]["enabled"] is True
    assert by_id["qbitai"]["enabled"] is False
    assert by_id["qbitai"]["schedule_cron"] == "15 * * * *"
    assert by_id["leiphone_ai"]["enabled"] is False


def test_merge_pack_layers_deep_merges_l1_then_l2():
    l1 = {"scoring": {"overrides": {"weights": {"relevance": 0.15}}}}
    l2 = {"scoring": {"overrides": {"keywords": {"tier_s": ["AI"]}}}}
    merged = merge_pack_layers(l1, l2)
    assert merged["scoring"]["overrides"]["weights"]["relevance"] == 0.15
    assert merged["scoring"]["overrides"]["keywords"]["tier_s"] == ["AI"]


def test_build_effective_config_tech_ai_uses_bundled_pack_keywords(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()

    effective = build_effective_config(DEFAULT_INDUSTRY_ID)
    relevance = (effective.get("scoring") or {}).get("ai_relevance_keywords") or []
    assert "大模型" in relevance
    assert effective["industry_id"] == DEFAULT_INDUSTRY_ID
    assert effective["ingestion"]["sources"]


def test_effective_cache_round_trip(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()

    payload = {"industry_id": "tech/ai", "scoring": {"profile": "flash_news"}}
    write_effective_cache("tech/ai", payload, manifest_hash="abc")
    path = effective_cache_path("tech/ai")
    assert path.is_file()
    loaded = load_effective_cache("tech/ai")
    assert loaded is not None
    assert loaded["industry_id"] == "tech/ai"
    assert loaded["manifest_hash"] == "abc"


def test_effective_pack_keywords_boost_relevance_score(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        build_effective_config(DEFAULT_INDUSTRY_ID),
        manifest_hash="pack",
    )
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)

    from services.ingestion.article_scorer import score_article

    result = score_article(
        title="行业动态：DeepSeek 发布新 Agent 框架",
        summary="",
        content_text="",
    )
    relevance = next(d for d in result.dimensions if d.key == "relevance")
    assert relevance.score >= 5.0


def test_build_effective_ignores_stale_effective_cache_overlay(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        {
            "industry_id": DEFAULT_INDUSTRY_ID,
            "scoring": {"industry_bonus": {"max_total_points": 1}},
        },
        manifest_hash="stale",
    )
    fresh = build_effective_config(DEFAULT_INDUSTRY_ID)
    assert fresh["scoring"]["industry_bonus"]["max_total_points"] == 8


def test_load_merged_scoring_config_applies_effective_cache(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()

    scoring_override = {
        "industry_bonus": {"max_total_points": 99},
        "keywords": {"tier_s": ["pack-only-kw"]},
    }
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        {"industry_id": DEFAULT_INDUSTRY_ID, "scoring": scoring_override},
        manifest_hash="test",
    )
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)

    from services.ingestion.scoring_settings import load_merged_scoring_config

    merged = load_merged_scoring_config()
    assert merged["industry_bonus"]["max_total_points"] == 99
    assert merged["keywords"]["tier_s"] == ["pack-only-kw"]
