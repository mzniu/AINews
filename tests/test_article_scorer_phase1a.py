"""Tests for Phase 1a industry scorer changes."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services.ingestion.article_scorer import (
    grade_from_total,
    load_scoring_config,
    score_article,
)
from src.utils.config import Config


def _cfg() -> dict:
    return load_scoring_config(Config.ROOT_DIR / "config" / "article_scoring.yaml")


def _dim(result, key: str):
    return next(d for d in result.dimensions if d.key == key)


def _positive_bonus_total(result) -> float:
    return sum(float(bonus["points"]) for bonus in result.bonuses if float(bonus["points"]) > 0)


def _accounted_total(result) -> float:
    dimension_total = sum(float(dimension.weighted) for dimension in result.dimensions)
    bonus_total = sum(float(bonus["points"]) for bonus in result.bonuses)
    penalty_total = sum(float(penalty["points"]) for penalty in result.penalties)
    return max(0.0, min(100.0, dimension_total + bonus_total + penalty_total))


def test_hot_radar_unmatched_scores_zero():
    result = score_article(
        title="OpenAI 发布新模型",
        summary="一次重要更新。",
        content_text="正文" * 50,
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=3,
        hot_radar_match=None,
        config=_cfg(),
    )
    assert _dim(result, "hot_radar").score == 0.0


def test_grade_from_total_defaults_missing_s_threshold_to_88():
    assert grade_from_total(87.9, {"profile": "test"}) == "A"
    assert grade_from_total(88, {"profile": "test"}) == "S"


def test_grade_from_total_defaults_partial_s_threshold_to_88():
    partial = {"grades": {"A": 70, "B": 55, "C": 40}}
    assert grade_from_total(87.9, partial) == "A"
    assert grade_from_total(88, partial) == "S"


def test_public_issue_exempts_off_topic_penalty():
    result = score_article(
        title="库克卸任苹果CEO特努斯接任",
        summary="Apple 宣布 Tim Cook 卸任，由特努斯接任 CEO。",
        content_text="苹果宣布管理层变动。",
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=3,
        config=_cfg(),
    )
    assert not any("非AI" in p["reason"] for p in result.penalties)
    assert result.grade != "D"


def test_insufficient_images_exempt_for_timely_money_story():
    result = score_article(
        title="曝DeepSeek前7个月收入4.75亿",
        summary="DeepSeek 前七个月收入 4.75 亿元。",
        content_text="人工智能" * 50,
        keywords=["AI", "DeepSeek", "大模型"],
        published_at=datetime.utcnow() - timedelta(hours=1),
        image_count=2,
        config=_cfg(),
    )
    assert not any(p["reason"].startswith("配图不足") for p in result.penalties)


def test_industry_scorer_no_hook_dimension():
    result = score_article(
        title="Meta核心研究员离职",
        summary="Meta AI 核心研究员宣布离职创业。",
        content_text="人工智能实验室核心研究员离职。",
        keywords=["AI", "Meta"],
        published_at=datetime.utcnow() - timedelta(hours=4),
        image_count=3,
        config=_cfg(),
    )
    keys = {d.key for d in result.dimensions}
    assert "hook" not in keys


def test_event_tension_tiered_not_auto_ten():
    result = score_article(
        title="某公司完成融资",
        summary="人工智能创业公司完成 A 轮融资。",
        content_text="AI 创业公司获得融资。",
        keywords=["AI", "融资"],
        published_at=datetime.utcnow() - timedelta(hours=4),
        image_count=3,
        config=_cfg(),
    )
    assert _dim(result, "event_tension").score <= 8.0


def test_many_event_signals_with_tier1_can_reach_ten():
    result = score_article(
        title="Meta裁员并收购AI团队",
        summary="Meta 宣布裁员，同时收购 AI 团队，估值引发关注。",
        content_text="Meta 裁员、收购、融资、IPO 传闻不断，业内震惊。",
        keywords=["AI", "Meta", "大模型"],
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=3,
        config=_cfg(),
    )
    assert _dim(result, "event_tension").score >= 8.0


def test_layoff_story_gets_highest_personnel_bonus_and_image_exempt():
    result = score_article(
        title="Meta叫停二轮AI换人裁员",
        summary="Meta 在大裁员前紧急叫停 AI 换人计划，员工爆料裁员比例达220%。",
        content_text="人工智能" * 80,
        keywords=["AI", "Meta", "大模型"],
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=0,
        config=_cfg(),
    )
    assert any(b["reason"] == "用工震荡" for b in result.bonuses)
    assert not any(b["reason"] == "裁员危机" for b in result.bonuses)
    assert not any(p["reason"].startswith("配图不足") for p in result.penalties)
    assert _dim(result, "data_signal").score >= 7.0


def test_financial_disclosure_bonus_for_deepseek_revenue():
    result = score_article(
        title="曝DeepSeek前7个月收入4.75亿",
        summary="DeepSeek 前七个月收入 4.75 亿元。",
        content_text="人工智能" * 50,
        keywords=["AI", "DeepSeek", "大模型"],
        published_at=datetime.utcnow() - timedelta(hours=1),
        image_count=2,
        config=_cfg(),
    )
    assert any(b["reason"] == "财务披露" for b in result.bonuses)
    assert _dim(result, "data_signal").score >= 7.0


@pytest.mark.parametrize(
    ("title", "summary", "keywords"),
    [
        (
            '00后清华博士生创业"神经接口"',
            "OpenAI 关注的博士创业项目。",
            ["AI", "创业", "博士", "大模型"],
        ),
        (
            "OpenAI资助天才少年博士",
            "OpenAI 宣布资助天才少年。",
            ["AI", "资助", "天才", "博士"],
        ),
        (
            "OpenAI红娘服务承诺退款结婚",
            "OpenAI 推出红娘服务，承诺未结婚退款。",
            ["AI", "红娘", "退款", "结婚"],
        ),
    ],
)
def test_identity_only_signals_are_not_industry_bonuses_or_s_grade(title, summary, keywords):
    result = score_article(
        title=f"OpenAI首发GPT-5 AI大模型完成融资收购：{title}",
        summary=summary,
        content_text=(summary + " 人工智能项目。") * 20,
        keywords=keywords + ["GPT-5", "融资", "收购"],
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=3,
        config=_cfg(),
    )
    removed_reasons = {"创业者故事", "人才计划", "消费创新"}
    assert removed_reasons.isdisjoint(bonus["reason"] for bonus in result.bonuses)
    assert result.grade == "A"


def test_founder_only_startup_signal_has_zero_positive_industry_bonus_points():
    result = score_article(
        title="OpenAI 00后博士创业AI大模型项目",
        summary="一位00后博士创办人工智能项目。",
        content_text="00后博士创业人工智能项目。" * 20,
        keywords=["AI", "博士", "创业", "大模型"],
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=3,
        config=_cfg(),
    )
    assert _positive_bonus_total(result) == 0


def test_open_training_bonus_for_live_model_training():
    result = score_article(
        title='535B大模型"直播"训练三个月：代码、数据、Loss全公开，吴恩达公开力挺',
        summary="开源大模型训练全程公开。",
        content_text="大模型直播训练三个月，Loss全公开，参数535B。" * 15,
        keywords=["AI", "大模型", "开源"],
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=3,
        config=_cfg(),
    )
    assert any(b["reason"] == "开放训练" for b in result.bonuses)


def test_workforce_shock_bonus_for_meta_layoff_story():
    result = score_article(
        title="Meta叫停二轮AI换人裁员",
        summary="Meta 在大裁员前紧急叫停，AI代码暴涨220%。",
        content_text="Meta 员工爆料裁员与 AI 换人计划。",
        keywords=["AI", "Meta", "裁员"],
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=0,
        config=_cfg(),
    )
    workforce_bonus = next(b for b in result.bonuses if b["reason"] == "用工震荡")
    assert workforce_bonus["points"] == 8
    assert result.grade == "A"


@pytest.mark.parametrize(
    ("title", "expected_reason", "group_reasons"),
    [
        (
            "Meta核心员工离职创业后遭裁员叫停，用工反增220%",
            "用工震荡",
            {"人事地震", "裁员危机", "用工震荡"},
        ),
        (
            "Meta被曝收入营收与估值",
            "财务披露",
            {"财务披露"},
        ),
        (
            "Meta高管发声回应535B万参数模型直播训练，Loss全公开开源",
            "开放训练",
            {"超级参数", "开放训练", "高管发声"},
        ),
    ],
)
def test_industry_narrative_groups_apply_only_highest_candidate(
    title, expected_reason, group_reasons
):
    result = score_article(
        title=title,
        summary=f"{title}，这是人工智能大模型的重要进展。",
        content_text=(title + " AI 大模型。") * 20,
        keywords=["AI", "Meta", "大模型", "开源"],
        published_at=datetime.utcnow() - timedelta(hours=2),
        image_count=3,
        config=_cfg(),
    )
    applied = [bonus for bonus in result.bonuses if bonus["reason"] in group_reasons]
    assert [bonus["reason"] for bonus in applied] == [expected_reason]
    assert sum(float(bonus["points"]) for bonus in applied) == float(applied[0]["points"])


class _TopRadarMatch:
    effective_rank = 1
    rank = 1
    board_id = "ai"
    board_name = "AI热榜"
    board_display = ""
    heat_label = "hot"
    match_method = "title"


def test_all_positive_industry_bonuses_share_configured_point_budget():
    cfg = _cfg()
    result = score_article(
        title="Meta员工离职创业后遭裁员叫停，用工反增220%，高管回应535B模型直播训练",
        summary="Meta 被曝收入营收和估值，AI大模型Loss全公开开源。",
        content_text=(
            "Meta 人工智能员工离职创业，裁员叫停，用工反增220%，"
            "高管发声回应，535B万参数大模型直播训练，Loss全公开开源，收入营收估值。"
        )
        * 12,
        keywords=["AI", "Meta", "大模型", "开源"],
        published_at=datetime.utcnow() - timedelta(hours=1),
        view_count=20_000,
        story_article_count=4,
        image_count=3,
        hot_radar_match=_TopRadarMatch(),
        config=cfg,
    )
    configured_cap = float(cfg["industry_bonus"]["max_total_points"])
    applied_total = _positive_bonus_total(result)
    assert applied_total == configured_cap
    assert applied_total <= configured_cap
    assert result.total == pytest.approx(_accounted_total(result))


def test_multiple_penalties_are_uncapped_while_positive_bonuses_remain_capped():
    cfg = _cfg()
    result = score_article(
        title="限时优惠扫码领取课程",
        summary="限时优惠，扫码领取课程，加微信了解详情。",
        content_text="限时优惠 扫码领取课程 加微信。" * 20,
        published_at=datetime.utcnow() - timedelta(hours=1),
        view_count=20_000,
        story_article_count=3,
        image_count=0,
        hot_radar_match=_TopRadarMatch(),
        config=cfg,
    )
    assert _positive_bonus_total(result) == float(
        cfg["industry_bonus"]["max_total_points"]
    )
    assert sorted(float(penalty["points"]) for penalty in result.penalties) == [
        -12.0,
        -8.0,
        -6.0,
    ]
    assert sum(float(penalty["points"]) for penalty in result.penalties) == -26
    assert result.total == pytest.approx(_accounted_total(result))
