"""Tests for async media pipeline execution."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from services.ingestion.media_pipeline import run_media_pipeline
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import ArticleImage, IngestedArticle, IngestionSource


def _pipeline_test_image(rel_name: str) -> dict:
    from PIL import Image

    from src.utils.paths import get_data_dir

    path = get_data_dir() / rel_name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        Image.new("RGB", (800, 600), color="green").save(path)
    return {"local_path": f"/data/{rel_name}"}


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    from PIL import Image

    from src.utils.paths import get_data_dir

    db_path = tmp_path / "media_pipeline.db"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    get_data_dir.cache_clear()
    img_path = data_dir / "ingested/src1/art_pipe/images/img_001.jpg"
    img_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), color="green").save(img_path)
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
        "renderer": "python",
        "fallback_from": "remotion",
    }

    result = run_media_pipeline(db_session, "art_pipe")

    assert result["success"] is True
    assert result["steps"]["render_video"]["renderer"] == "python"
    assert result["steps"]["render_video"]["fallback_from"] == "remotion"
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


@patch("services.ingestion.media_pipeline.prepend_cover_intro_to_video")
@patch("services.ingestion.media_pipeline.render_article_cover")
@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_renders_video_with_one_selected_image(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    mock_cover,
    mock_intro,
    db_session,
):
    mock_score.return_value = {"scored_count": 28, "from_cache": True}
    mock_content.return_value = {
        "success": True,
        "main_line1": "突发！单图也能出片",
        "summary": "小牛说：x",
        "tags": "#AI",
        "model": "m",
    }
    hero = _pipeline_test_image("hero.jpg")
    mock_prepare.return_value = {
        "auto_selected_images": [hero],
        "images": [hero],
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": True, "video_path": "/data/videos/one.mp4"}
    mock_cover.return_value = {"success": True, "cover_path": "/data/covers/one.jpg"}
    mock_intro.return_value = {"success": True, "video_path": "/data/videos/one.mp4"}

    result = run_media_pipeline(db_session, "art_pipe")

    assert result["success"] is True
    assert result["video_rendered"] is True
    mock_render.assert_called_once()
    article = db_session.get(IngestedArticle, "art_pipe")
    assert article.generated_video_path == "/data/videos/one.mp4"


@patch("services.ingestion.media_pipeline.prepend_cover_intro_to_video")
@patch("services.ingestion.media_pipeline.render_article_cover")
@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_reuses_existing_draft_when_llm_empty(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    mock_cover,
    mock_intro,
    db_session,
):
    article = db_session.get(IngestedArticle, "art_pipe")
    article.video_draft_json = '{"main_line1": "已有标题", "summary": "小牛说：旧稿"}'
    db_session.commit()

    mock_score.return_value = {"scored_count": 2, "from_cache": True}
    mock_content.side_effect = ValueError("LLM 返回空内容")
    mock_prepare.return_value = {
        "auto_selected_images": [
            _pipeline_test_image("a.jpg"),
            _pipeline_test_image("b.jpg"),
        ],
        "metadata_path": "/data/meta.json",
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": True, "video_path": "/data/videos/reused.mp4"}
    mock_cover.return_value = {"success": True, "cover_path": "/data/covers/reused.jpg"}
    mock_intro.return_value = {"success": True, "video_path": "/data/videos/reused.mp4"}

    result = run_media_pipeline(db_session, "art_pipe")

    assert result["success"] is True
    assert any("generate_content" in e for e in result["errors"])
    assert result["steps"]["generate_content"]["reused_existing_draft"] is True
    mock_render.assert_called_once()
    assert mock_render.call_args.kwargs["draft"]["main_line1"] == "已有标题"


@patch("services.ingestion.media_pipeline.prepend_cover_intro_to_video")
@patch("services.ingestion.media_pipeline.render_article_cover")
@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_falls_back_to_title_draft_when_llm_empty(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    mock_cover,
    mock_intro,
    db_session,
):
    mock_score.return_value = {"scored_count": 2, "from_cache": True}
    mock_content.side_effect = ValueError("LLM 返回空内容")
    mock_prepare.return_value = {
        "auto_selected_images": [
            _pipeline_test_image("a.jpg"),
            _pipeline_test_image("b.jpg"),
        ],
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": True, "video_path": "/data/videos/fallback.mp4"}
    mock_cover.return_value = {"success": True, "cover_path": "/data/covers/fallback.jpg"}
    mock_intro.return_value = {"success": True, "video_path": "/data/videos/fallback.mp4"}

    result = run_media_pipeline(db_session, "art_pipe")

    assert result["success"] is True
    assert result["steps"]["generate_content"]["used_fallback_draft"] is True
    mock_render.assert_called_once()
    draft = mock_render.call_args.kwargs["draft"]
    assert "DeepSeek" in draft["main_line1"]
    article = db_session.get(IngestedArticle, "art_pipe")
    assert article.video_draft_json is None


@patch("services.ingestion.media_pipeline.prepend_cover_intro_to_video")
@patch("services.ingestion.media_pipeline.render_article_cover")
@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_skips_llm_and_uses_existing_draft(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    mock_cover,
    mock_intro,
    db_session,
):
    article = db_session.get(IngestedArticle, "art_pipe")
    article.video_draft_json = '{"main_line1": "跳过生成", "summary": "小牛说：旧稿"}'
    db_session.commit()

    mock_score.return_value = {"scored_count": 2}
    mock_prepare.return_value = {
        "auto_selected_images": [
            _pipeline_test_image("a.jpg"),
            _pipeline_test_image("b.jpg"),
        ],
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": True, "video_path": "/data/videos/skip.mp4"}
    mock_cover.return_value = {"success": True, "cover_path": "/data/covers/skip.jpg"}
    mock_intro.return_value = {"success": True, "video_path": "/data/videos/skip.mp4"}

    result = run_media_pipeline(
        db_session,
        "art_pipe",
        config={"generate_content": False, "include_story_images": False},
    )

    mock_content.assert_not_called()
    assert result["success"] is True
    assert mock_render.call_args.kwargs["draft"]["main_line1"] == "跳过生成"


def test_restore_generated_media_paths_from_prep_status(db_session):
    from services.ingestion.media_paths import restore_generated_media_paths

    article = db_session.get(IngestedArticle, "art_pipe")
    article.media_pipeline_status = "succeeded"
    article.generated_video_path = None
    article.generated_cover_path = None
    article.video_prep_status_json = (
        '{"success": true, "video_rendered": true, "steps": {'
        '"render_video": {"video_path": "/data/videos/animated_x.mp4"},'
        '"render_cover": {"success": true, "cover_path": "data/publish/covers/art_pipe_cover.jpg"}'
        "}}"
    )
    db_session.commit()

    changed = restore_generated_media_paths(article)
    assert changed is True
    assert article.generated_video_path == "/data/videos/animated_x.mp4"
    assert article.generated_cover_path == "data/publish/covers/art_pipe_cover.jpg"


@patch("services.ingestion.media_pipeline.prepend_cover_intro_to_video")
@patch("services.ingestion.media_pipeline.render_article_cover")
@patch("services.ingestion.media_pipeline.pick_best_cover_image")
@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_rewrites_paths_if_cleared_after_checkpoint(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    mock_pick_cover,
    mock_cover,
    mock_intro,
    db_session,
):
    mock_score.return_value = {"scored_count": 1, "from_cache": True}
    mock_content.return_value = {
        "success": True,
        "main_line1": "突发！",
        "summary": "小牛说：x",
        "tags": "#AI",
        "model": "m",
    }
    hero = _pipeline_test_image("hero.jpg")
    mock_prepare.return_value = {
        "auto_selected_images": [hero],
        "images": [hero],
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": True, "video_path": "/data/videos/kept.mp4"}
    mock_pick_cover.return_value = hero
    mock_cover.return_value = {"success": True, "cover_path": "data/publish/covers/kept.jpg"}
    mock_intro.return_value = {"success": True, "video_path": "/data/videos/kept.mp4"}

    import services.ingestion.media_pipeline as media_pipeline

    original_checkpoint = media_pipeline._checkpoint

    def clear_paths_after_commit(session):
        original_checkpoint(session)
        article = session.get(IngestedArticle, "art_pipe")
        if article is not None and (article.generated_video_path or article.generated_cover_path):
            article.generated_video_path = None
            article.generated_cover_path = None
            session.commit()

    with patch.object(media_pipeline, "_checkpoint", clear_paths_after_commit):
        result = run_media_pipeline(db_session, "art_pipe")

    assert result["success"] is True
    article = db_session.get(IngestedArticle, "art_pipe")
    assert article.generated_video_path == "/data/videos/kept.mp4"
    assert article.generated_cover_path == "data/publish/covers/kept.jpg"


@patch("services.ingestion.media_pipeline.render_article_cover")
@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_falls_back_to_pool_when_auto_selected_empty(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    mock_cover,
    db_session,
    tmp_path,
    monkeypatch,
):
    from PIL import Image

    from src.utils.paths import get_data_dir

    data_dir = tmp_path / "appdata"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    get_data_dir.cache_clear()

    img_path = data_dir / "ingested/src1/art_pipe/images/img_001.jpg"
    img_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), color="green").save(img_path)
    stored = "data/ingested/src1/art_pipe/images/img_001.jpg"
    pool_image = {"local_path": f"/{stored}", "success": True, "url": "https://cdn.example.com/a.jpg"}

    mock_score.return_value = {"scored_count": 0, "from_cache": False}
    mock_content.return_value = {
        "success": True,
        "main_line1": "无评分也能出片",
        "summary": "小牛说：x",
        "tags": "#AI",
        "model": "m",
    }
    mock_prepare.return_value = {
        "auto_selected_images": [],
        "images": [pool_image, pool_image, pool_image],
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": True, "video_path": "/data/videos/fallback.mp4"}
    mock_cover.return_value = {"success": True, "cover_path": "/data/covers/fallback.jpg"}

    result = run_media_pipeline(db_session, "art_pipe")

    assert result["success"] is True
    assert result["video_rendered"] is True
    mock_render.assert_called_once()
    image_paths = mock_render.call_args.kwargs.get("image_paths") or mock_render.call_args[1].get("image_paths")
    assert image_paths
    get_data_dir.cache_clear()


@patch("services.ingestion.media_pipeline.clean_images_for_render")
@patch("services.ingestion.media_pipeline.prepend_cover_intro_to_video")
@patch("services.ingestion.media_pipeline.render_article_cover")
@patch("services.ingestion.media_pipeline.pick_best_cover_image")
@patch("services.ingestion.media_pipeline.render_ingested_video")
@patch("services.ingestion.media_pipeline.pick_random_bgm")
@patch("services.ingestion.media_pipeline.prepare_video_metadata")
@patch("services.ingestion.media_pipeline.generate_video_content")
@patch("services.ingestion.media_pipeline.score_article_images")
def test_pipeline_uses_cleaned_paths_and_picks_cover_once(
    mock_score,
    mock_content,
    mock_prepare,
    mock_bgm,
    mock_render,
    mock_pick_cover,
    mock_cover,
    mock_intro,
    mock_clean,
    db_session,
):
    from services.ingestion.watermark_clean import WatermarkCleanResult

    hero = _pipeline_test_image("hero.jpg")
    cover = _pipeline_test_image("cover.jpg")
    mock_score.return_value = {"scored_count": 1, "from_cache": True}
    mock_content.return_value = {
        "success": True,
        "main_line1": "突发！",
        "summary": "小牛说：x",
        "tags": "#AI",
        "model": "m",
    }
    mock_prepare.return_value = {
        "auto_selected_images": [hero],
        "images": [hero],
    }
    mock_bgm.return_value = "static/music/a.mp3"
    mock_render.return_value = {"success": True, "video_path": "/data/videos/out.mp4"}
    mock_pick_cover.return_value = cover
    mock_cover.return_value = {"success": True, "cover_path": "data/publish/covers/out.jpg"}
    mock_intro.return_value = {"success": True, "video_path": "/data/videos/out.mp4"}

    cleaned_hero = "/data/hero_auto_clean.jpg"
    cleaned_cover = "/data/cover_auto_clean.jpg"

    def _clean(paths, *, enabled=True, **kwargs):
        assert enabled is True
        return {
            path: WatermarkCleanResult(
                path=cleaned_hero if "hero" in path else cleaned_cover,
                status="cleaned",
                original_path=path,
                cleaned_path=cleaned_hero if "hero" in path else cleaned_cover,
                regions=(),
                reason="ok",
            )
            for path in paths
        }

    mock_clean.side_effect = _clean

    result = run_media_pipeline(db_session, "art_pipe")
    assert result["success"] is True
    assert mock_pick_cover.call_count == 1
    sent_images = mock_render.call_args.kwargs["image_paths"]
    assert cleaned_hero in sent_images
    assert mock_cover.call_args.kwargs["image_path"] == cleaned_cover
    assert "clean_watermarks" in result["steps"]
    assert "clean_watermarks:" not in " ".join(result.get("errors") or [])
