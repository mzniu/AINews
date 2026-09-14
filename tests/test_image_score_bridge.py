"""Tests for prepare-video bridge with image relevance sorting and auto-select."""
from __future__ import annotations

import json

import pytest
from PIL import Image

from services.ingestion.bridge import dedupe_image_entries, prepare_video_metadata
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


def test_dedupe_image_entries_prefers_better_rank():
    shared_url = "https://cdn.example.com/shared.jpg"
    images = [
        {
            "url": shared_url,
            "local_path": "/data/art1/shared.jpg",
            "relevance_rank": 3,
            "relevance_score": 70,
        },
        {
            "url": shared_url,
            "local_path": "/data/art2/shared-copy.jpg",
            "relevance_rank": 1,
            "relevance_score": 92,
        },
        {
            "url": "https://cdn.example.com/other.jpg",
            "local_path": "/data/art1/other.jpg",
            "relevance_rank": 2,
            "relevance_score": 85,
        },
    ]
    deduped = dedupe_image_entries(images)
    assert len(deduped) == 2
    assert deduped[0]["relevance_rank"] == 1
    assert len({_normalize_url(img["url"]) for img in deduped}) == 2


def _normalize_url(url: str) -> str:
    return str(url or "").strip().split("?", 1)[0].rstrip("/").lower()


def test_prepare_video_dedupes_article_and_story_images(db_session, tmp_path, monkeypatch):
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
    db_session.add(Story(id="story1", canonical_title="同题", article_count=2))
    db_session.flush()
    shared_url = "https://cdn.example.com/shared.jpg"
    img_path = tmp_path / "shared.jpg"
    Image.new("RGB", (800, 600), color=(120, 80, 40)).save(img_path)
    other_path = tmp_path / "other.jpg"
    Image.new("RGB", (800, 600), color=(40, 80, 120)).save(other_path)

    db_session.add(
        IngestedArticle(
            id="art_a",
            source_id="src1",
            canonical_url="https://example.com/a",
            title="Article A",
            story_id="story1",
        )
    )
    db_session.add(
        ArticleImage(
            id="img_a1",
            article_id="art_a",
            original_url=shared_url,
            local_path=str(img_path),
            sort_order=0,
            download_status="ok",
        )
    )
    db_session.add(
        ArticleImage(
            id="img_a2",
            article_id="art_a",
            original_url="https://cdn.example.com/other.jpg",
            local_path=str(other_path),
            sort_order=1,
            download_status="ok",
        )
    )
    db_session.add(
        StoryAsset(
            id="sa1",
            story_id="story1",
            asset_type="image",
            source_article_id="art_b",
            payload_json=json.dumps(
                {
                    "original_url": shared_url,
                    "local_path": str(img_path),
                    "download_status": "ok",
                }
            ),
            sort_order=0,
        )
    )
    db_session.commit()
    score_article_images(db_session, "art_a", force=True, include_story_images=True)
    db_session.commit()

    result = prepare_video_metadata(
        db_session,
        "art_a",
        include_story_images=True,
        sort_by_relevance=True,
    )
    urls = [img.get("url") for img in result["images"]]
    assert len(urls) == 2
    assert urls.count(shared_url) == 1


def test_prepare_video_fills_min_count_without_unmerged_story_a(db_session, tmp_path):
    """Story-cluster A grades must not consume min_count when story images are excluded."""
    img_a = tmp_path / "a.jpg"
    img_b = tmp_path / "b.jpg"
    Image.new("RGB", (800, 600), (200, 30, 30)).save(img_a)
    Image.new("RGB", (800, 600), (30, 30, 200)).save(img_b)
    db_session.add(
        IngestionSource(
            id="src1", slug="s", display_name="S", adapter_class="t", enabled=True
        )
    )
    db_session.flush()
    db_session.add(Story(id="story1", canonical_title="同题", article_count=2))
    db_session.flush()
    db_session.add(
        IngestedArticle(
            id="art_a",
            source_id="src1",
            canonical_url="https://example.com/a",
            title="Article A",
            story_id="story1",
        )
    )
    db_session.add(
        ArticleImage(
            id="img_a",
            article_id="art_a",
            original_url="https://cdn.example.com/a.jpg",
            local_path=str(img_a),
            sort_order=0,
            download_status="ok",
        )
    )
    db_session.add(
        ArticleImage(
            id="img_b",
            article_id="art_a",
            original_url="https://cdn.example.com/b.jpg",
            local_path=str(img_b),
            sort_order=1,
            download_status="ok",
        )
    )
    db_session.flush()
    db_session.add(
        ImageRelevanceEvaluation(
            id="ev1",
            article_id="art_a",
            source_type="article_image",
            source_id="img_a",
            original_url="https://cdn.example.com/a.jpg",
            local_path=str(img_a),
            relevance_score=70.2,
            relevance_grade="A",
            relevance_rank=2,
        )
    )
    db_session.add(
        ImageRelevanceEvaluation(
            id="ev2",
            article_id="art_a",
            source_type="article_image",
            source_id="img_b",
            original_url="https://cdn.example.com/b.jpg",
            local_path=str(img_b),
            relevance_score=60.4,
            relevance_grade="B",
            relevance_rank=5,
        )
    )
    db_session.add(
        ImageRelevanceEvaluation(
            id="ev3",
            article_id="art_a",
            source_type="story_asset",
            source_id="story_a",
            original_url="https://img.example.com/story.jpg",
            local_path="/data/other/img_003.jpg",
            relevance_score=73.8,
            relevance_grade="A",
            relevance_rank=1,
        )
    )
    db_session.commit()

    result = prepare_video_metadata(
        db_session,
        "art_a",
        include_story_images=False,
        auto_select=True,
    )
    auto_ids = [img.get("source_id") for img in (result.get("auto_selected_images") or [])]
    assert auto_ids == ["img_a", "img_b"]


def test_prepare_video_auto_select_orders_by_relevance_rank(db_session, tmp_path):
    img_a = tmp_path / "a.jpg"
    img_b = tmp_path / "b.jpg"
    Image.new("RGB", (800, 600), (200, 30, 30)).save(img_a)
    Image.new("RGB", (800, 600), (30, 30, 200)).save(img_b)
    db_session.add(
        IngestionSource(
            id="src1", slug="s", display_name="S", adapter_class="t", enabled=True
        )
    )
    db_session.flush()
    db_session.add(
        IngestedArticle(
            id="art_order",
            source_id="src1",
            canonical_url="https://example.com/order",
            title="Order test",
        )
    )
    db_session.add(
        ArticleImage(
            id="img_low",
            article_id="art_order",
            original_url="https://cdn.example.com/low.jpg",
            local_path=str(img_b),
            sort_order=0,
            download_status="ok",
        )
    )
    db_session.add(
        ArticleImage(
            id="img_high",
            article_id="art_order",
            original_url="https://cdn.example.com/high.jpg",
            local_path=str(img_a),
            sort_order=1,
            download_status="ok",
        )
    )
    db_session.flush()
    db_session.add(
        ImageRelevanceEvaluation(
            id="ev_low",
            article_id="art_order",
            source_type="article_image",
            source_id="img_low",
            original_url="https://cdn.example.com/low.jpg",
            local_path=str(img_b),
            relevance_score=55.0,
            relevance_grade="B",
            relevance_rank=2,
        )
    )
    db_session.add(
        ImageRelevanceEvaluation(
            id="ev_high",
            article_id="art_order",
            source_type="article_image",
            source_id="img_high",
            original_url="https://cdn.example.com/high.jpg",
            local_path=str(img_a),
            relevance_score=88.0,
            relevance_grade="A",
            relevance_rank=1,
        )
    )
    db_session.commit()

    result = prepare_video_metadata(db_session, "art_order", auto_select=True, sort_by_relevance=True)
    auto_ids = [img.get("source_id") for img in (result.get("auto_selected_images") or [])]
    assert auto_ids == ["img_high", "img_low"]


def test_prepare_video_supplements_title_match_images(db_session, tmp_path):
    title = "英伟达400亿押注开源，边卖铲子边挖矿"
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not-an-image")
    good = tmp_path / "good.jpg"
    Image.new("RGB", (900, 600), color=(40, 80, 120)).save(good)
    db_session.add(
        IngestionSource(
            id="src1", slug="s", display_name="S", adapter_class="t", enabled=True
        )
    )
    db_session.flush()
    db_session.add(Story(id="story_readhub", canonical_title=title, article_count=1))
    db_session.flush()
    db_session.add(
        IngestedArticle(
            id="art_readhub",
            source_id="src1",
            canonical_url="https://readhub.cn/topic/abc",
            title=title,
            story_id="story_readhub",
        )
    )
    db_session.add(
        IngestedArticle(
            id="art_kr36",
            source_id="src1",
            canonical_url="https://36kr.com/p/abc",
            title="英伟达 400 亿押注开源，边卖铲子边挖矿",
            story_id="story_kr36",
        )
    )
    db_session.add(
        ArticleImage(
            id="img_bad",
            article_id="art_readhub",
            original_url="https://readhub.cn/icons/bookmark.svg",
            local_path=str(bad),
            sort_order=0,
            download_status="ok",
        )
    )
    db_session.add(
        ArticleImage(
            id="img_good",
            article_id="art_kr36",
            original_url="https://cdn.example.com/nvidia.jpg",
            local_path=str(good),
            sort_order=0,
            download_status="ok",
        )
    )
    db_session.commit()

    result = prepare_video_metadata(
        db_session,
        "art_readhub",
        include_story_images=True,
        auto_select=False,
    )
    sources = {img.get("source") for img in result["images"]}
    assert "story_related" in sources
    assert any(img.get("source_id") == "img_good" for img in result["images"])

