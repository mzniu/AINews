"""Tests for async media pipeline execution."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from services.ingestion.media_pipeline import run_media_pipeline
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import ArticleImage, IngestedArticle, IngestionSource


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "media_pipeline.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    factory = get_session_factory()
    session = factory()
    session.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="Test",
            adapter_class="aitnt_news",
            enabled=True,
            schedule_cron="0 * * * *",
        )
    )
    session.commit()
    article = IngestedArticle(
        id="art_pipe",
        source_id="src1",
        canonical_url="https://example.com/pipe",
        title="DeepSeek 发布",
        content_text="DeepSeek 今日发布新模型。",
        score_grade="S",
        score_total=88.0,
    )
    session.add(article)
    session.add(
        ArticleImage(
            id="img1",
            article_id="art_pipe",
            original_url="https://cdn.example.com/a.jpg",
            local_path="data/ingested/src1/art_pipe/images/img_001.jpg",
            download_status="ok",
            sort_order=1,
        )
    )
    session.commit()
    yield session
    session.close()


@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_runs_all_steps_and_persists_video(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    db_session,
    tmp_path,
):
    mock_score.return_value = {
        "scored_count": 1,
        "summary": {"auto_selected_ids": ["img1"]},
    }
    mock_content.return_value = {
        "success": True,
        "main_line1": "突发！DeepSeek",
        "main_line2": "",
        "sub_title": "副标题",
        "sub_title2": "",
        "summary": "小牛说：测试",
        "tags": "#AI",
        "highlight_keywords": ["DeepSeek"],
        "model": "deepseek-chat",
    }
    mock_prepare.return_value = {
        "auto_selected_images": [
            {"local_path": "/data/ingested/src1/art_pipe/images/img_001.jpg", "source_id": "img1"},
            {"local_path": "/data/ingested/src1/art_pipe/images/img_002.jpg", "source_id": "img2"},
        ],
        "images": [],
    }
    mock_bgm.return_value = "static/music/test.mp3"
    mock_render.return_value = {
        "success": True,
        "video_path": "/data/videos/ingested_art_pipe.mp4",
    }

    result = run_media_pipeline(db_session, "art_pipe")

    assert result["success"] is True
    article = db_session.get(IngestedArticle, "art_pipe")
    assert article.video_draft_json is not None
    assert article.generated_video_path == "/data/videos/ingested_art_pipe.mp4"
    assert article.selected_bgm_path == "static/music/test.mp3"
    assert article.media_pipeline_status == "succeeded"
    mock_render.assert_called_once()


@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_keeps_draft_when_video_fails(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    db_session,
):
    mock_score.return_value = {"scored_count": 1, "summary": {"auto_selected_ids": ["img1"]}}
    mock_content.return_value = {
        "success": True,
        "main_line1": "突发！",
        "summary": "小牛说：x",
        "tags": "#AI",
        "model": "m",
    }
    mock_prepare.return_value = {
        "auto_selected_images": [{"local_path": "/data/x.jpg"}],
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": False, "error": "ffmpeg missing"}

    result = run_media_pipeline(db_session, "art_pipe")

    article = db_session.get(IngestedArticle, "art_pipe")
    assert article.video_draft_json is not None
    assert result["success"] is False
    assert article.media_pipeline_status == "failed"
    assert article.generated_video_path is None
