"""Tests for enhanced hot radar URL/title matching (phase 1)."""
from __future__ import annotations

from services.ingestion.hot_radar_matching import (
    extract_url_keys,
    match_urls,
    normalize_netloc,
    score_title_pair,
)


def test_normalize_netloc_strips_mobile_and_www():
    assert normalize_netloc("m.ithome.com") == "ithome.com"
    assert normalize_netloc("www.36kr.com") == "36kr.com"


def test_extract_url_keys_ithome_across_hosts():
    keys_a = extract_url_keys("https://m.ithome.com/html/992565.htm")
    keys_b = extract_url_keys("https://www.ithome.com/0/992/565.htm")
    assert keys_a & keys_b


def test_extract_url_keys_36kr():
    left = extract_url_keys("https://www.36kr.com/p/3948502822550665")
    right = extract_url_keys("https://36kr.com/p/3948502822550665?utm_source=foo")
    assert left & right


def test_match_urls_exact_and_id():
    matched, method, confidence = match_urls(
        "https://www.ithome.com/0/992/565.htm",
        "https://m.ithome.com/html/992565.htm",
    )
    assert matched is True
    assert method == "url_id"
    assert confidence >= 0.95

    matched2, method2, confidence2 = match_urls(
        "https://www.36kr.com/p/123",
        "https://www.36kr.com/p/123",
    )
    assert matched2 is True
    assert method2 == "url_exact"
    assert confidence2 == 1.0


def test_score_title_pair_exact_and_contains():
    cfg = {"title_exact": 1.0, "title_contains": 0.88, "title_similarity_threshold": 0.72}
    conf, method = score_title_pair(
        "OpenAI 发布 GPT-5 模型",
        "OpenAI 发布 GPT-5 模型",
        entity_names=["OpenAI"],
        config=cfg,
    )
    assert method == "title_exact"
    assert conf == 1.0

    conf2, method2 = score_title_pair(
        "OpenAI 发布 GPT-5 模型，性能大幅提升",
        "OpenAI 发布 GPT-5 模型",
        entity_names=["OpenAI"],
        config=cfg,
    )
    assert method2 == "title_contains"
    assert conf2 >= 0.88


def test_score_title_pair_entity_overlap_boost():
    cfg = {
        "title_similarity_threshold": 0.72,
        "entity_overlap_min": 2,
        "entity_overlap_boost": 0.12,
    }
    conf, method = score_title_pair(
        "OpenAI 与 Google 宣布新合作",
        "Google 和 OpenAI 达成合作",
        entity_names=["OpenAI", "Google", "Microsoft"],
        config=cfg,
    )
    assert method in {"title_similarity", "entity_overlap"}
    assert conf >= 0.72


def test_entity_overlap_does_not_match_when_only_hot_title_has_entities():
    """Regression: hot title mentioning 字节+腾讯 must not match unrelated article title."""
    cfg = {
        "title_similarity_threshold": 0.72,
        "entity_overlap_min": 2,
        "entity_overlap_boost": 0.12,
        "entity_overlap_floor": 0.65,
    }
    conf, method = score_title_pair(
        "采集，从一条腕带开始",
        "消息称字节豆包最快下周发布对标腾讯 WorkBuddy 办公类 AI 产品",
        entity_names=["字节", "腾讯", "Meta", "阿里", "Google", "OpenAI"],
        config=cfg,
    )
    assert method == ""
    assert conf < 0.72
