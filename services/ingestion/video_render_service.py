"""Render ingested article video using the homepage animated-video pipeline."""
from __future__ import annotations

import os
from typing import Any

from fastapi.responses import JSONResponse
from loguru import logger

from api.schemas.request_models import CreateAnimatedVideoRequest, ImageWithDuration

MIN_VIDEO_DURATION_SEC = 8.0
DEFAULT_VIDEO_RENDERER = "remotion"
PYTHON_VIDEO_RENDERER_ALIASES = frozenset({"python", "moviepy"})


def resolve_video_renderer(renderer: str | None = None) -> str:
    """Return ``remotion`` (default) or ``python`` when explicitly requested."""
    raw = renderer if renderer is not None else os.environ.get("VIDEO_RENDERER", DEFAULT_VIDEO_RENDERER)
    choice = str(raw).strip().lower()
    if choice in PYTHON_VIDEO_RENDERER_ALIASES:
        return "python"
    return "remotion"


def _normalize_image_path(path: str) -> str:
    return str(path or "").strip().lstrip("/").replace("\\", "/")


def _duration_table_lookup(table: dict[Any, Any], count: int) -> list[float] | None:
    if not isinstance(table, dict):
        return None
    raw = table.get(count)
    if raw is None:
        raw = table.get(str(count))
    if not isinstance(raw, list) or len(raw) != count:
        return None
    return [float(item) for item in raw]


def resolve_ingested_clip_durations(
    image_count: int,
    template: dict[str, Any] | None = None,
) -> list[float]:
    """Per-image clip duration for ingested slideshow videos."""
    if image_count <= 0:
        return []
    spec = template
    if spec is None:
        try:
            from services.ingestion.render_templates import get_render_template

            spec = get_render_template(None)
        except Exception:
            spec = {}
    video = (spec or {}).get("video") or {}
    exact = _duration_table_lookup(video.get("clip_durations_by_count") or {}, image_count)
    if exact is not None:
        return exact
    gte = video.get("clip_sec_when_at_least") or {}
    try:
        gte_count = int(gte.get("count", 4))
        gte_sec = float(gte.get("sec", 2.0))
    except (TypeError, ValueError):
        gte_count, gte_sec = 4, 2.0
    if image_count >= gte_count:
        return [gte_sec] * image_count
    try:
        fallback = float(video.get("fallback_clip_sec", 2.5))
    except (TypeError, ValueError):
        fallback = 2.5
    return [fallback] * image_count


def ensure_min_total_duration(
    durations: list[float],
    *,
    min_total: float = MIN_VIDEO_DURATION_SEC,
) -> list[float]:
    if not durations:
        return durations
    total = sum(float(item) for item in durations)
    if total >= min_total:
        return durations
    if total <= 0:
        per = min_total / len(durations)
        return [per] * len(durations)
    scale = min_total / total
    return [round(float(item) * scale, 3) for item in durations]


def render_ingested_video(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    bgm_path: str,
    background_image: str = "static/imgs/bg.png",
    clip_duration_sec: float = 2.5,
    template: dict[str, Any] | None = None,
    renderer: str | None = None,
) -> dict[str, Any]:
    from services.ingestion.render_image_utils import is_renderable_local_image

    renderable_paths = [
        _normalize_image_path(path)
        for path in image_paths
        if is_renderable_local_image(path)
    ]
    renderable_paths = [path for path in renderable_paths if path]
    if len(renderable_paths) < 1:
        return {
            "success": False,
            "error": "insufficient_images",
            "count": len(renderable_paths),
        }

    video_cfg = (template or {}).get("video") or {}
    try:
        min_total = float(video_cfg.get("min_duration_sec", MIN_VIDEO_DURATION_SEC))
    except (TypeError, ValueError):
        min_total = MIN_VIDEO_DURATION_SEC

    durations = resolve_ingested_clip_durations(len(renderable_paths), template=template)
    if len(durations) < len(renderable_paths):
        durations = durations + [clip_duration_sec] * (len(renderable_paths) - len(durations))
    durations = ensure_min_total_duration(durations, min_total=min_total)
    image_paths = renderable_paths

    if resolve_video_renderer(renderer) == "remotion":
        from services.ingestion.remotion_render_service import remotion_available, render_with_remotion

        if remotion_available():
            remotion_result = render_with_remotion(
                article_id=article_id,
                draft=draft,
                image_paths=image_paths,
                bgm_path=bgm_path,
                background_image=background_image,
                durations=durations,
                template=template,
            )
            if remotion_result.get("success"):
                return remotion_result
            logger.warning(
                "Remotion render failed for article={}: {}; falling back to Python",
                article_id,
                remotion_result.get("error"),
            )
        else:
            logger.warning("Remotion not installed; falling back to Python renderer for article={}", article_id)

    if (template or {}).get("layout_kind") == "chronicle_frame":
        from services.ingestion.chronicle_render import render_chronicle_video

        return render_chronicle_video(
            article_id=article_id,
            draft=draft,
            image_paths=image_paths,
            bgm_path=bgm_path,
            template=template or {},
            durations=durations,
        )

    images = [
        ImageWithDuration(path=_normalize_image_path(p), duration=durations[index])
        for index, p in enumerate(image_paths)
    ]
    typo = (template or {}).get("typography") or {}
    video_cfg = (template or {}).get("video") or {}
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
        show_summary=bool(video_cfg.get("show_summary", True)),
        summary_scroll_mode=str(video_cfg.get("summary_scroll_mode") or "line_uniform"),
        title_font_size=typo.get("title_font_size"),
        subtitle_font_size=typo.get("subtitle_font_size"),
        summary_font_size=typo.get("summary_font_size"),
        title_y_percent=typo.get("title_y_percent"),
        main_line1_color=str(typo.get("main_line1_color") or "#FFFFFF"),
        main_line2_color=str(typo.get("main_line2_color") or "#FFFFFF"),
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
