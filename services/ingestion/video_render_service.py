"""Render ingested article video using the homepage animated-video pipeline."""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from loguru import logger

from api.schemas.request_models import CreateAnimatedVideoRequest, ImageWithDuration


def _normalize_image_path(path: str) -> str:
    return str(path or "").strip().lstrip("/").replace("\\", "/")


def resolve_ingested_clip_durations(image_count: int) -> list[float]:
    """Per-image clip duration for ingested slideshow videos."""
    if image_count <= 0:
        return []
    if image_count == 2:
        return [3.5, 3.5]
    if image_count == 3:
        return [2.5, 3.0, 3.0]
    if image_count >= 4:
        return [2.0] * image_count
    return [2.5] * image_count


def render_ingested_video(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    bgm_path: str,
    background_image: str = "static/imgs/bg.png",
    clip_duration_sec: float = 2.5,
) -> dict[str, Any]:
    if len(image_paths) < 2:
        return {"success": False, "error": "insufficient_images", "count": len(image_paths)}

    durations = resolve_ingested_clip_durations(len(image_paths))
    if len(durations) < len(image_paths):
        durations = durations + [clip_duration_sec] * (len(image_paths) - len(durations))

    images = [
        ImageWithDuration(path=_normalize_image_path(p), duration=durations[index])
        for index, p in enumerate(image_paths)
    ]
    request = CreateAnimatedVideoRequest(
        summary=draft.get("summary") or "",
        images=images,
        audio_path=bgm_path,
        main_line1=draft.get("main_line1") or "",
        main_line2=draft.get("main_line2") or "",
        subtitle=draft.get("sub_title") or "",
        subtitle2=draft.get("sub_title2") or "",
        background_image_path=background_image,
        tags=draft.get("tags") or "",
        summary_highlight_keywords=draft.get("highlight_keywords") or [],
        show_summary=True,
    )

    from api.routes.video_routes import _create_animated_video_blocking

    try:
        result = _create_animated_video_blocking(request)
    except Exception as exc:
        logger.warning(f"render_ingested_video failed article={article_id}: {exc}")
        return {"success": False, "error": str(exc)}

    if isinstance(result, JSONResponse):
        return {"success": False, "error": "video_render_rejected"}
    if not isinstance(result, dict) or not result.get("success"):
        return {"success": False, "error": "video_render_failed", "detail": result}
    return result
