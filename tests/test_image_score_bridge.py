"""Tests for prepare-video bridge with image relevance sorting and auto-select."""
from __future__ import annotations

import json

import pytest
from PIL import Image

from services.ingestion.bridge import prepare_video_metadata
from services.ingestion.image_score_service import score_article_images
from src.db.engine import init_db, get_session_factory
from src.db.models.ingestion import ArticleImage, IngestedArticle, IngestionSource


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "bridge_test.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    session = factory()
    yield session
    session.close()


def _fake_vl(**kwargs):
    images = kwargs.get("images") or []
    out = []
    for idx, (source_id, _path) in enumerate(images):
        score = 9 - idx
        out.append(
            {
                "source_id": source_id,
                "dimensions": {
                    "topic_relevance": {"score": score, "signals": []},
                    "info_value": {"score": score, "signals": []},
                    "visual_quality": {"score": score, "signals": []},
                    "flash_fit": {"score": score, "signals": []},
                    "cover_fit": {"score": score, "signals": ["封面"]},
                    "figure_prominence": {"score": score - 1, "signals": []},
                    "compliance": {"score": score, "signals": []},
                },
                "penalties": [],
                "caption": f"c-{source_id}",
                "verdict": "ok",
                "reject": False,
            }
        )
    return out


@pytest.fixture
def scored_article(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.ingestion.image_score_service.score_images_batch",
        _fake_vl,
    )
    db_session.add(
        IngestionSource(
            id="src1",
            slug="s",
            display_name="S",
            adapter_class="t",
            enabled=True,
        )
    )
    db_session.flush()
    db_session.add(
        IngestedArticle(
            id="art_bridge",
            source_id="src1",
            canonical_url="https://example.com/b",
            title="Bridge Test",
            summary="sum",
        )
    )
    img_dir = tmp_path / "imgs"
    img_dir.mkdir()
    for i in range(2):
        p = img_dir / f"{i}.jpg"
        Image.new("RGB", (800, 600), color=(i * 80, 100, 150)).save(p)
        db_session.add(
            ArticleImage(
                id=f"bimg{i}",
                article_id="art_bridge",
                original_url=f"https://cdn.example.com/{i}.jpg",
                local_path=str(p),
                sort_order=i,
                download_status="ok",
                origin="cover" if i == 0 else "article_body",
            )
        )
    db_session.commit()
    score_article_images(db_session, "art_bridge", force=True)
    db_session.commit()
    return "art_bridge"


def test_prepare_video_sorts_by_relevance_rank(db_session, scored_article):
    result = prepare_video_metadata(
        db_session,
        scored_article,
        sort_by_relevance=True,
    )
    images = result["images"]
    assert len(images) >= 2
    assert images[0].get("relevance_rank") == 1
    assert images[0]["relevance_score"] >= images[1]["relevance_score"]


def test_prepare_video_auto_selects_a_grade(db_session, scored_article):
    result = prepare_video_metadata(
        db_session,
        scored_article,
        auto_select=True,
        sort_by_relevance=True,
    )
    auto = result.get("auto_selected_images") or []
    assert len(auto) >= 1
    assert all(img.get("auto_selected") for img in auto)
    meta_path = result["metadata_path"].lstrip("/")
    saved = json.loads(open(meta_path, encoding="utf-8").read())
    assert "auto_selected_images" in saved


def test_prepare_video_includes_extended_score_fields(db_session, scored_article):
    result = prepare_video_metadata(db_session, scored_article, sort_by_relevance=True)
    img = result["images"][0]
    assert img.get("relevance_grade") is not None
    assert img.get("cover_fit_score") is not None
    assert img.get("figure_prominence_score") is not None
    assert result["metadata"].get("image_scores_available") is True
