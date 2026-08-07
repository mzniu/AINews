"""Tests for image relevance score service (DB integration, story images, cache)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from services.ingestion.image_score_service import score_article_images
from src.db.engine import init_db, get_session_factory
from src.db.models.ingestion import (
    ArticleImage,
    ImageRelevanceEvaluation,
    IngestedArticle,
    IngestionSource,
    Story,
    StoryAsset,
)


def _fake_vl_batch(**_kwargs):
    """Deterministic VL stub for tests."""
    images = _kwargs.get("images") or []
    out = []
    for idx, (source_id, _path) in enumerate(images):
        score = 9 - (idx % 3)
        out.append(
            {
                "source_id": source_id,
                "dimensions": {
                    "topic_relevance": {"score": score, "signals": ["test"]},
                    "info_value": {"score": score, "signals": []},
                    "visual_quality": {"score": score, "signals": []},
                    "flash_fit": {"score": score, "signals": []},
                    "compliance": {"score": score, "signals": []},
                },
                "penalties": [],
                "caption": f"caption-{source_id}",
                "verdict": "ok",
                "reject": False,
            }
        )
    return out


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_image_score.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    session = factory()
    yield session
    session.close()


@pytest.fixture
def article_with_images(db_session, tmp_path):
    source = IngestionSource(
        id="test_src",
        slug="test",
        display_name="Test",
        adapter_class="test",
        enabled=True,
    )
    db_session.add(source)
    db_session.flush()
    article = IngestedArticle(
        id="art1",
        source_id="test_src",
        canonical_url="https://example.com/a1",
        title="DeepSeek 发布新模型",
        summary="重要 AI 快讯",
        content_text="正文内容",
        keywords_json='["AI","DeepSeek"]',
    )
    db_session.add(article)
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    for i in range(3):
        p = img_dir / f"img_{i:03d}.jpg"
        Image.new("RGB", (800, 600), color=(i * 40, 100, 150)).save(p)
        db_session.add(
            ArticleImage(
                id=f"img{i}",
                article_id="art1",
                original_url=f"https://cdn.example.com/img{i}.jpg",
                local_path=str(p),
                sort_order=i,
                download_status="ok",
                origin="cover" if i == 0 else "article_body",
            )
        )
    db_session.commit()
    return article


def test_score_article_images_persists_evaluations(db_session, article_with_images, monkeypatch):
    monkeypatch.setattr(
        "services.ingestion.image_score_service.score_images_batch",
        _fake_vl_batch,
    )
    result = score_article_images(db_session, "art1", force=True)
    assert result["success"] is True
    assert result["scored_count"] == 3
    rows = (
        db_session.query(ImageRelevanceEvaluation)
        .filter_by(article_id="art1")
        .order_by(ImageRelevanceEvaluation.relevance_rank)
        .all()
    )
    assert len(rows) == 3
    assert rows[0].relevance_rank == 1
    assert rows[0].relevance_score is not None
    assert rows[0].relevance_grade in ("A", "B", "C", "D")


def test_score_article_images_uses_cache_when_not_forced(
    db_session, article_with_images, monkeypatch
):
    calls = {"n": 0}

    def counting_vl(**kwargs):
        calls["n"] += 1
        return _fake_vl_batch(**kwargs)

    monkeypatch.setattr(
        "services.ingestion.image_score_service.score_images_batch",
        counting_vl,
    )
    score_article_images(db_session, "art1", force=True)
    first_run_calls = calls["n"]
    assert first_run_calls >= 1
    result = score_article_images(db_session, "art1", force=False)
    assert calls["n"] == first_run_calls
    assert result["from_cache"] is True


def test_score_article_images_includes_story_assets(db_session, article_with_images, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.ingestion.image_score_service.score_images_batch",
        _fake_vl_batch,
    )
    story = Story(id="story1", canonical_title="同题", article_count=2)
    db_session.add(story)
    article_with_images.story_id = "story1"
    other_img = tmp_path / "story_img.jpg"
    Image.new("RGB", (640, 480), color="blue").save(other_img)
    db_session.add(
        StoryAsset(
            id="sa1",
            story_id="story1",
            asset_type="image",
            source_article_id="other_art",
            payload_json=json.dumps(
                {
                    "original_url": "https://cdn.example.com/story.jpg",
                    "local_path": str(other_img),
                    "download_status": "ok",
                }
            ),
            sort_order=0,
        )
    )
    db_session.commit()

    result = score_article_images(db_session, "art1", force=True, include_story_images=True)
    assert result["scored_count"] == 4
    types = {row.source_type for row in db_session.query(ImageRelevanceEvaluation).filter_by(article_id="art1")}
    assert "story_asset" in types
    assert "article_image" in types


def test_score_article_images_raises_when_article_missing(db_session):
    with pytest.raises(ValueError, match="Article not found"):
        score_article_images(db_session, "missing")
