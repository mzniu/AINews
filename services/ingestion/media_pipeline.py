"""Execute media pipeline: image scoring, AI copy, prepare-video, render video."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from services.content_generation_service import generate_video_content
from services.ingestion.bgm_picker import pick_random_bgm
from services.ingestion.cover_picker import pick_best_cover_image
from services.ingestion.cover_render_service import render_article_cover
from services.ingestion.cover_video_utils import prepend_cover_intro_to_video
from services.ingestion.bridge import prepare_video_metadata
from services.ingestion.image_score_service import score_article_images
from services.ingestion.media_pipeline_trigger import load_media_pipeline_config
from services.ingestion.video_render_service import render_ingested_video, resolve_ingested_clip_durations
from src.db.models.ingestion import IngestedArticle


def _normalize_local_path(path: str | None) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    return raw if raw.startswith("/") else f"/{raw}"


def _checkpoint(session: Session) -> None:
    """Commit progress so long-running steps do not hold SQLite write locks."""
    session.commit()


def run_media_pipeline(
    session: Session,
    article_id: str,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    article = session.get(IngestedArticle, article_id)
    if article is None:
        raise ValueError(f"Article not found: {article_id}")

    cfg = load_media_pipeline_config(config)
    article.media_pipeline_status = "running"
    session.flush()
    _checkpoint(session)

    started = datetime.utcnow()
    steps: dict[str, Any] = {}
    errors: list[str] = []
    draft: dict[str, Any] | None = None
    selected_images: list[dict[str, Any]] = []
    bgm_path: str | None = None
    video_path: str | None = None

    if cfg.get("score_images", True):
        try:
            img_result = score_article_images(
                session,
                article.id,
                force=False,
                include_story_images=bool(cfg.get("include_story_images", True)),
            )
            steps["score_images"] = {
                "scored_count": img_result.get("scored_count"),
                "from_cache": img_result.get("from_cache"),
            }
        except Exception as exc:
            logger.warning(f"media_pipeline score_images failed: {exc}")
            errors.append(f"score_images: {exc}")
            steps["score_images"] = {"error": str(exc)}
        else:
            _checkpoint(session)

    if cfg.get("generate_content", True):
        try:
            content_text = article.content_text or article.summary or ""
            if not content_text.strip():
                raise ValueError("文章无正文")
            draft = generate_video_content(
                title=article.title or "",
                content=content_text,
                voiceover_min_chars=int(cfg.get("voiceover_min_chars", 40)),
                voiceover_max_chars=int(cfg.get("voiceover_max_chars", 90)),
            )
            article.video_draft_json = json.dumps(draft, ensure_ascii=False)
            article.video_draft_generated_at = datetime.utcnow()
            steps["generate_content"] = {"model": draft.get("model")}
        except Exception as exc:
            logger.warning(f"media_pipeline generate_content failed: {exc}")
            errors.append(f"generate_content: {exc}")
            steps["generate_content"] = {"error": str(exc)}
        else:
            _checkpoint(session)

    if cfg.get("prepare_video", True):
        try:
            prep = prepare_video_metadata(
                session,
                article.id,
                include_story_images=bool(cfg.get("include_story_images", True)),
                sort_by_relevance=True,
                auto_select=True,
            )
            selected_images = prep.get("auto_selected_images") or []
            max_n = int(cfg.get("max_selected_images", 4))
            selected_images = selected_images[:max_n]
            steps["prepare_video"] = {
                "auto_selected_count": len(selected_images),
                "metadata_path": prep.get("metadata_path"),
            }
            article.selected_images_json = json.dumps(selected_images, ensure_ascii=False)
        except Exception as exc:
            logger.warning(f"media_pipeline prepare_video failed: {exc}")
            errors.append(f"prepare_video: {exc}")
            steps["prepare_video"] = {"error": str(exc)}
        else:
            _checkpoint(session)

    image_paths = [
        _normalize_local_path(img.get("local_path"))
        for img in selected_images
        if img.get("local_path")
    ]

    if cfg.get("render_video", True) and draft and len(image_paths) >= 2:
        if cfg.get("random_bgm", True):
            bgm_path = pick_random_bgm(cfg.get("bgm_dir", "static/music"))
            article.selected_bgm_path = bgm_path
        try:
            render_result = render_ingested_video(
                article_id=article.id,
                draft=draft,
                image_paths=image_paths,
                bgm_path=bgm_path or "static/music/background.mp3",
                background_image=str(cfg.get("background_image", "static/imgs/bg.png")),
                clip_duration_sec=float(cfg.get("clip_duration_sec", 2.5)),
            )
            if render_result.get("success"):
                video_path = render_result.get("video_path")
                article.generated_video_path = video_path
                article.generated_video_at = datetime.utcnow()
                steps["render_video"] = {
                    "video_path": video_path,
                    "duration": render_result.get("duration"),
                    "clip_durations": resolve_ingested_clip_durations(len(image_paths)),
                }
            else:
                errors.append(f"render_video: {render_result.get('error')}")
                steps["render_video"] = render_result
        except Exception as exc:
            logger.warning(f"media_pipeline render_video failed: {exc}")
            errors.append(f"render_video: {exc}")
            steps["render_video"] = {"error": str(exc)}
        else:
            _checkpoint(session)
    elif cfg.get("render_video", True):
        errors.append("render_video: skipped (missing draft or images)")
        steps["render_video"] = {"skipped": True, "image_count": len(image_paths)}

    if cfg.get("render_cover", True) and draft:
        try:
            cover_source = pick_best_cover_image(session, article.id)
            if cover_source:
                cover_result = render_article_cover(
                    article_id=article.id,
                    draft=draft,
                    image_path=cover_source["local_path"],
                    background_image=str(cfg.get("background_image", "static/imgs/bg.png")),
                    width=int(cfg.get("cover_width", 1080)),
                    height=int(cfg.get("cover_height", 1440)),
                )
                if cover_result.get("success"):
                    article.generated_cover_path = cover_result.get("cover_path")
                    steps["render_cover"] = cover_result
                else:
                    errors.append(f"render_cover: {cover_result.get('error')}")
                    steps["render_cover"] = cover_result
            else:
                steps["render_cover"] = {"skipped": True, "reason": "no_scored_cover_image"}
        except Exception as exc:
            logger.warning(f"media_pipeline render_cover failed: {exc}")
            errors.append(f"render_cover: {exc}")
            steps["render_cover"] = {"error": str(exc)}
        else:
            _checkpoint(session)

    if (
        cfg.get("prepend_cover_intro", True)
        and video_path
        and article.generated_cover_path
    ):
        try:
            intro_result = prepend_cover_intro_to_video(
                video_path=video_path,
                cover_path=article.generated_cover_path,
                intro_duration=float(cfg.get("cover_intro_duration_sec", 1.0)),
            )
            if intro_result.get("success"):
                video_path = str(intro_result.get("video_path") or video_path)
                article.generated_video_path = video_path
                steps["prepend_cover_intro"] = intro_result
            else:
                errors.append(f"prepend_cover_intro: {intro_result.get('error')}")
                steps["prepend_cover_intro"] = intro_result
        except Exception as exc:
            logger.warning(f"media_pipeline prepend_cover_intro failed: {exc}")
            errors.append(f"prepend_cover_intro: {exc}")
            steps["prepend_cover_intro"] = {"error": str(exc)}

    video_ok = bool(video_path)
    partial_ok = bool(draft) and not video_ok
    success = video_ok or (partial_ok and not errors)

    status_payload = {
        "success": success,
        "video_rendered": video_ok,
        "started_at": started.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
        "steps": steps,
        "errors": errors,
    }
    article.video_prep_status_json = json.dumps(status_payload, ensure_ascii=False)
    if video_ok:
        article.video_prep_at = datetime.utcnow()
        article.media_pipeline_status = "succeeded"
        try:
            from services.publishing.auto_publish import maybe_enqueue_auto_publish_jobs

            auto_publish = maybe_enqueue_auto_publish_jobs(session, article)
            status_payload["auto_publish"] = auto_publish
        except Exception as exc:
            logger.exception(f"auto_publish failed article={article.id}: {exc}")
            status_payload["auto_publish"] = {"success": False, "error": str(exc)}
    elif partial_ok:
        article.media_pipeline_status = "failed"
    else:
        article.media_pipeline_status = "failed"

    session.flush()
    return status_payload
