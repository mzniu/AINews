"""Tests for viral potential scoring (Phase 1a)."""
from __future__ import annotations

from datetime import datetime, timedelta

from services.ingestion.viral_scorer import (
    _grade_from_viral_total,
    evaluate_hook_gate,
    load_scoring_config,
    load_viral_scoring_config,
    score_viral_potential,
)


def _cfg() -> dict:
    return load_viral_scoring_config()


def _root_cfg() -> dict:
    return load_scoring_config()


def test_hook_gate_passes_with_subject_number_conflict():
    result = evaluate_hook_gate(
        title="突发？Meta核心研究员离职",
        summary="Meta AI 核心研究员宣布离职创业。",
        cfg=_cfg(),
        prominence_score=8.5,
    )
    assert result.subject is True
    assert result.conflict is True
    assert result.passed is True


def test_hook_gate_fails_without_enough_dimensions():
    result = evaluate_hook_gate(
        title="某公司内部工具更新",
        summary="一次小版本修复。",
        cfg=_cfg(),
        prominence_score=2.0,
    )
    assert result.passed is False


def test_money_shock_scores_high_social_currency():
    result = score_viral_potential(
        title="突发？Cursor被600亿买走",
        summary="Cursor 被收购，交易金额约 600 亿美元。",
        content_text="",
        prominence_score=9.0,
        config=_cfg(),
    )
    social = next(m for m in result.motives if m.key == "social_currency")
    assert social.score >= 8.0
    assert result.total >= 50


def test_personnel_story_scores_emotional_and_identity():
    result = score_viral_potential(
        title="宇树科技1万到2万资助天才少年",
        summary="王兴兴寻找下一个王兴兴，资助天才少年。",
        content_text="",
        prominence_score=9.0,
        config=_cfg(),
    )
    identity = next(m for m in result.motives if m.key == "identity")
    assert identity.score >= 6.0


def test_hook_gate_does_not_cap_grade():
    """hook_gate feeds publish_tier only; viral grade must follow total thresholds."""
    root = _root_cfg()
    result = score_viral_potential(
        title="某公司内部工具更新",
        summary="一次小版本修复。",
        content_text="",
        prominence_score=2.0,
        config=root,
    )
    viral_cfg = load_viral_scoring_config(root)
    assert result.hook_gate.passed is False
    assert result.grade == _grade_from_viral_total(result.total, viral_cfg)


def test_combo_bonuses_for_viral_hits():
    root = _root_cfg()
    layoff = score_viral_potential(
        title="小扎连夜喊停：不让AI换人裁员，Meta员工却在裁员前48小时收到裁员通知",
        summary="Meta 在大裁员前紧急叫停 AI 换人计划，员工爆料裁员比例达220%。",
        content_text="",
        prominence_score=8.5,
        config=root,
    )
    assert layoff.grade == "S"
    assert any(b["reason"] == "裁员震荡" for b in layoff.bonuses)

    consumer = score_viral_potential(
        title="徐新投1500万AI红娘",
        summary="三年不结婚就退款的 AI 红娘获融资。",
        content_text="",
        prominence_score=8.5,
        config=root,
    )
    assert consumer.grade == "S"
    social = next(m for m in consumer.motives if m.key == "social_currency")
    assert social.score >= 8.0


def test_public_issue_with_tier1_scores_high():
    result = score_viral_potential(
        title="库克卸任苹果CEO特努斯接任",
        summary="Apple 宣布 CEO 更替。",
        content_text="",
        prominence_score=8.5,
        config=_cfg(),
    )
    public_issue = next(m for m in result.motives if m.key == "public_issue")
    assert public_issue.score >= 6.0


def test_hot_radar_entry_bonus():
    class _Match:
        rank = 7
        effective_rank = 7

    result = score_viral_potential(
        title="Meta叫停二轮AI换人裁员",
        summary="Meta 在大裁员前紧急叫停 AI 换人计划。",
        content_text="",
        prominence_score=8.5,
        hot_radar_match=_Match(),
        config=_cfg(),
    )
    assert any(b["reason"] == "热榜入场" for b in result.bonuses)


def test_platform_fit_includes_wechat_for_emotional_story():
    result = score_viral_potential(
        title="徐新投1500万AI红娘",
        summary="三年不结婚就退款的 AI 红娘获融资。",
        content_text="",
        prominence_score=8.5,
        config=_cfg(),
    )
    assert "wechat_channels" in result.platform_fit
