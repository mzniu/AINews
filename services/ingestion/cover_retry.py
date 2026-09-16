"""Regenerate a single article's publish cover without re-running the full media pipeline."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from services.ingestion.cover_picker import pick_best_cover_image
from services.ingestion.media_pipeline_trigger import load_media_pipeline_config
from src.db.models.ingestion import IngestedArticle


def _parse_video_draft(article: IngestedArticle) -> dict[str, Any]:
    if article.video_draft_json:
        try:
            data = json.loads(article.video_draft_json)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {"main_line1": (article.title or "未命名").strip()}


def render_cover_for_article(session: Session, article_id: str) -> dict[str, Any]:
    """Pick best image and render a video-sized cover. Raises ValueError if article missing."""
    article = session.get(IngestedArticle, article_id)
    if article is None:
        raise ValueError("Article not found")

    cover_source = pick_best_cover_image(session, article_id)
    if not cover_source:
        return {
            "success": False,
            "error": "no_scored_cover_image",
            "message": "无可用配图，请先运行「评估配图」或确保图片已下载到本地",
        }

    cfg = load_media_pipeline_config()
    draft = _parse_video_draft(article)
    from services.ingestion.cover_render_service import render_article_cover

    result = render_article_cover(
        article_id=article.id,
        draft=draft,
        image_path=cover_source["local_path"],
        background_image=str(cfg.get("background_image", "static/imgs/bg.png")),
        width=int(cfg.get("cover_width", 1080)),
        height=int(cfg.get("cover_height", 1920)),
        template=cfg.get("render_template"),
    )
    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error") or "render_failed",
            "message": str(result.get("error") or "封面生成失败"),
        }

    article.generated_cover_path = result.get("cover_path")
    session.flush()
    return {
        "success": True,
        "cover_path": article.generated_cover_path,
        "cover_source": cover_source.get("local_path"),
    }
