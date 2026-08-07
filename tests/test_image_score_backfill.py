"""Tests for image score backfill helper."""
from __future__ import annotations

import pytest
from PIL import Image

from services.ingestion.image_score_backfill import backfill_image_scores
from src.db.engine import init_db, get_session_factory
from src.db.models.ingestion import ArticleImage, IngestedArticle, IngestionSource


def _fake_vl(**kwargs):
    images = kwargs.get("images") or []
    return [
        {
            "source_id": sid,
            "dimensions": {
                "topic_relevance": {"score": 8, "signals": []},
                "info_value": {"score": 8, "signals": []},
                "visual_quality": {"score": 8, "signals": []},
                "flash_fit": {"score": 8, "signals": []},
                "compliance": {"score": 8, "signals": []},
            },
            "penalties": [],
            "caption": "ok",
            "verdict": "ok",
            "reject": False,
        }
        for sid, _ in images
    ]


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "backfill.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    session = factory()
    yield session
    session.close()


@pytest.fixture
def two_articles(db_session, tmp_path):
    db_session.add(
        IngestionSource(
            id="src_bf",
            slug="bf",
            display_name="BF",
            adapter_class="t",
            enabled=True,
        )
    )
    db_session.flush()
    for idx in range(2):
        aid = f"art_bf_{idx}"
        db_session.add(
            IngestedArticle(
                id=aid,
                source_id="src_bf",
                canonical_url=f"https://example.com/{idx}",
                title=f"Article {idx}",
            )
        )
        p = tmp_path / f"{idx}.jpg"
        Image.new("RGB", (800, 600), color=(idx * 50, 100, 150)).save(p)
        db_session.add(
            ArticleImage(
                id=f"img_bf_{idx}",
                article_id=aid,
                original_url=f"https://cdn.example.com/{idx}.jpg",
                local_path=str(p),
                sort_order=0,
                download_status="ok",
            )
        )
    db_session.commit()


def test_backfill_scores_only_articles_with_images(db_session, two_articles, monkeypatch):
    monkeypatch.setattr(
        "services.ingestion.image_score_service.score_images_batch",
        _fake_vl,
    )
    results = backfill_image_scores(
        db_session,
        source_id="src_bf",
        limit=10,
        force=True,
    )
    assert results["processed"] == 2
    assert results["scored"] == 2
    assert results["skipped"] == 0


def test_backfill_skips_when_cached(db_session, two_articles, monkeypatch):
    calls = {"n": 0}

    def counting_vl(**kwargs):
        calls["n"] += 1
        return _fake_vl(**kwargs)

    monkeypatch.setattr(
        "services.ingestion.image_score_service.score_images_batch",
        counting_vl,
    )
    backfill_image_scores(db_session, source_id="src_bf", limit=10, force=True)
    backfill_image_scores(db_session, source_id="src_bf", limit=10, force=False)
    assert calls["n"] == 2
