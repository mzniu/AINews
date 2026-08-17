"""Tests for chronicle card keyword picking."""
from __future__ import annotations

from services.ingestion.render_keyword import pick_card_keyword


def test_skips_generic_first_tag_and_uses_specific():
    assert pick_card_keyword(tags="#人工智能 #大模型 #小牛说") == "大模型"
    assert pick_card_keyword(tags="#AI前沿 #大模型") == "大模型"


def test_skips_brand_tags():
    assert pick_card_keyword(tags="#小牛说 #小牛聊AI #Agent") == "Agent"


def test_falls_back_to_article_keywords():
    assert pick_card_keyword(tags="#人工智能", keywords=["OpenAI", "GPT"]) == "OpenAI"


def test_falls_back_to_highlight_then_theme():
    assert pick_card_keyword(tags="", keywords=[], highlight_keywords=["点火"]) == "点火"
    assert pick_card_keyword(tags="#人工智能", keywords=["AI"], theme="财经") == "财经"


def test_generic_theme_uses_fallback():
    assert pick_card_keyword(tags="#人工智能", keywords=["AI"], theme="AI") == "快讯"


def test_strips_hash_and_truncates_to_eight_chars():
    assert pick_card_keyword(tags="#超长关键词一二三四五六") == "超长关键词一二三"
