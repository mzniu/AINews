"""Tests for cover image picker."""
from __future__ import annotations

import json

import pytest
from PIL import Image

from services.ingestion.cover_picker import pick_best_cover_image
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import (
    ArticleImage,
    ImageRelevanceEvaluation,
    IngestedArticle,
    IngestionSource,
    Story,
    StoryAsset,
)


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "test_cover_picker.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    session = factory()
    yield session
    session.close()


@pytest.fixture
def article_with_evaluations(db_session, tmp_path):
    source = IngestionSource(
        id="test_src",
        slug="test",
        display_name="Test",
        adapter_class="test",
        enabled=True,
    )
    db_session.add(source)
    db_session.flush()
    db_session.add(Story(id="story1", canonical_title="同题", article_count=2))
    article = IngestedArticle(
        id="art_cover",
        source_id="test_src",
        canonical_url="https://example.com/cover",
        title="测试封面",
        status="ingested",
    )
    db_session.add(article)
    db_session.flush()
    img_path = tmp_path / "article.jpg"
    Image.new("RGB", (1080, 1440), color="red").save(img_path)
    story_path = tmp_path / "story.jpg"
    Image.new("RGB", (1080, 1440), color="blue").save(story_path)

    article_img = ArticleImage(
        id="img1",
        article_id="art_cover",
        original_url="https://cdn.example.com/a.jpg",
        local_path=str(img_path),
        download_status="ok",
        sort_order=0,
    )
    db_session.add(article_img)
    db_session.add(
        StoryAsset(
            id="sa1",
            story_id="story1",
            asset_type="image",
            source_article_id="other",
            payload_json=json.dumps(
                {
                    "original_url": "https://cdn.example.com/story.jpg",
                    "local_path": str(story_path),
                    "download_status": "ok",
                }
            ),
            sort_order=0,
        )
    )
    db_session.add(
        ImageRelevanceEvaluation(
            article_id="art_cover",
            source_type="article_image",
            source_id="img1",
            original_url="https://cdn.example.com/a.jpg",
            local_path=str(img_path),
            relevance_score=70,
            relevance_grade="B",
            relevance_rank=2,
            breakdown_json=json.dumps(
                {"dimensions": {"cover_fit": {"score": 60}}}
            ),
        )
    )
    db_session.add(
        ImageRelevanceEvaluation(
            article_id="art_cover",
            source_type="story_asset",
            source_id="sa1",
            original_url="https://cdn.example.com/story.jpg",
            local_path=None,
            relevance_score=90,
            relevance_grade="A",
            relevance_rank=1,
            breakdown_json=json.dumps(
                {"dimensions": {"cover_fit": {"score": 95}}}
            ),
        )
    )
    db_session.commit()
    return article


def test_pick_best_cover_image_resolves_story_asset_from_payload(db_session, article_with_evaluations):
    picked = pick_best_cover_image(db_session, "art_cover")
    assert picked is not None
    assert picked["source_type"] == "story_asset"
    assert picked["source_id"] == "sa1"
    assert picked["cover_fit_score"] == 95
    assert picked["local_path"].endswith("story.jpg")


def test_pick_best_cover_image_uses_evaluation_local_path(db_session, article_with_evaluations, tmp_path):
    eval_only = tmp_path / "eval_only.jpg"
    Image.new("RGB", (1080, 1440), color="green").save(eval_only)
    row = (
        db_session.query(ImageRelevanceEvaluation)
        .filter_by(article_id="art_cover", source_type="story_asset")
        .one()
    )
    row.local_path = str(eval_only)
    db_session.commit()

    picked = pick_best_cover_image(db_session, "art_cover")
    assert picked is not None
    assert picked["local_path"] == str(eval_only)
