"""Tests for flash-news article scoring."""
from datetime import datetime, timedelta

from services.ingestion.article_scorer import load_scoring_config, score_article


def test_high_profile_open_source_article_scores_high():
    cfg = load_scoring_config()
    result = score_article(
        title="5050亿参数！余承东开源盘古新模型 openPangu-2.0-Pro",
        summary="华为开源基于昇腾 NPU 训练的盘古 MoE 模型，总参数 5050 亿。",
        content_text="openPangu-2.0-Pro 正式开源，支持 512K 上下文。",
        keywords=["AI", "华为", "盘古大模型"],
        published_at=datetime.utcnow() - timedelta(hours=6),
        view_count=8706,
        config=cfg,
    )
    assert result.total >= 70
    assert result.grade in ("S", "A")
    assert any(d.key == "prominence" and d.score >= 8 for d in result.dimensions)


def test_generic_article_scores_lower():
    cfg = load_scoring_config()
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
    cfg = load_scoring_config()
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
