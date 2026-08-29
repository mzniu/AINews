"""Tests for flash-news article scoring."""
from datetime import datetime, timedelta

from services.ingestion.article_scorer import load_scoring_config, score_article
from src.utils.config import Config


def _base_scoring_config():
    return load_scoring_config(Config.ROOT_DIR / "config" / "article_scoring.yaml")


def _dimension(result, key: str):
    return next(d for d in result.dimensions if d.key == key)


def test_high_profile_open_source_article_scores_high():
    cfg = _base_scoring_config()
    result = score_article(
        title="5050亿参数！余承东开源盘古新模型 openPangu-2.0-Pro",
        summary="华为开源基于昇腾 NPU 训练的盘古 MoE 模型，总参数 5050 亿。",
        content_text="openPangu-2.0-Pro 正式开源，支持 512K 上下文。",
        keywords=["AI", "华为", "盘古大模型"],
        published_at=datetime.utcnow() - timedelta(hours=6),
        view_count=8706,
        image_count=3,
        config=cfg,
    )
    assert result.total >= 68
    assert result.grade in ("S", "A")
    assert any(d.key == "prominence" and d.score >= 8 for d in result.dimensions)


def test_generic_article_scores_lower():
    cfg = _base_scoring_config()
    result = score_article(
        title="某小公司发布内部工具更新",
        summary="一次小版本修复。",
        content_text="修复若干 bug。",
        published_at=datetime.utcnow() - timedelta(days=30),
        config=cfg,
    )
    assert result.total < 55
    assert result.grade in ("C", "D", "B")


def test_insufficient_images_penalty():
    cfg = _base_scoring_config()
    base_kwargs = dict(
        title="OpenAI 发布新模型",
        summary="一次重要更新。",
        content_text="正文内容" * 50,
        published_at=datetime.utcnow() - timedelta(hours=12),
        config=cfg,
    )
    with_enough = score_article(**base_kwargs, image_count=3)
    with_few = score_article(**base_kwargs, image_count=2)
    with_none = score_article(**base_kwargs, image_count=0)

    assert with_few.total < with_enough.total
    assert with_none.total < with_few.total
    assert any(p["reason"].startswith("配图不足") for p in with_few.penalties)
    assert any(p["reason"].startswith("配图不足") for p in with_none.penalties)
    assert not any(p["reason"].startswith("配图不足") for p in with_enough.penalties)


def test_personnel_exit_scores_high_event_tension():
    result = score_article(
        title="Meta核心研究员离职",
        summary="Meta AI 核心研究员宣布离职创业。",
        content_text="人工智能实验室核心研究员离职，业内关注人才流动。",
        keywords=["AI", "Meta"],
        published_at=datetime.utcnow() - timedelta(hours=4),
        image_count=3,
        config=_base_scoring_config(),
    )
    tension = _dimension(result, "event_tension")
    assert tension.score >= 7.5
    assert any("离职" in s for s in tension.signals)


def test_model_download_rank_scores_low_event_tension():
    result = score_article(
        title="Qwen3.8-27B登顶HF榜下载破百万",
        summary="开源大模型下载量突破百万。",
        content_text="通义千问开源模型在 HuggingFace 下载破百万。",
        keywords=["AI", "大模型", "开源"],
        published_at=datetime.utcnow() - timedelta(hours=4),
        image_count=3,
        config=_base_scoring_config(),
    )
    tension = _dimension(result, "event_tension")
    assert tension.score < 5


def test_high_tension_personnel_story_reaches_s():
    result = score_article(
        title="突发 Meta核心研究员离职",
        summary="Meta AI 核心研究员宣布离职创业，人工智能圈震动。",
        content_text="Meta 核心 AI 研究员离职创业。OpenAI 与 DeepSeek 同期也有人事传闻。",
        keywords=["AI", "Meta", "大模型"],
        published_at=datetime.utcnow() - timedelta(hours=3),
        view_count=8000,
        story_article_count=2,
        image_count=3,
        config=_base_scoring_config(),
    )
    assert _dimension(result, "event_tension").score >= 7.5
    assert result.grade == "S"
    assert result.total >= 85


def test_relevance_uses_summary_not_just_title():
    result = score_article(
        title="协和医生解22年猜想",
        summary="协和神经外科医生用ChatGPT 5.6自主跑16小时，证明了折磨数学界22年的Crouzeix猜想。",
        content_text="",
        published_at=datetime.utcnow() - timedelta(hours=3),
        image_count=3,
        config=_base_scoring_config(),
    )
    assert _dimension(result, "relevance").score >= 5
    assert not any("非AI" in p["reason"] for p in result.penalties)


def test_off_topic_non_ai_story_is_penalized_off_s():
    result = score_article(
        title="绝了？液态玻璃登安卓",
        summary="荣耀MagicOS11公开安卓液态玻璃设计底座，锁屏组件可随壁纸流动。",
        content_text="荣耀在品鉴会上展示琉光架构与蜂鸟架构，强调通透视觉和流畅手感，属于系统皮肤改版。",
        published_at=datetime.utcnow() - timedelta(hours=3),
        view_count=9000,
        image_count=3,
        config=_base_scoring_config(),
    )
    assert any("非AI" in p["reason"] for p in result.penalties)
    assert result.grade != "S"
