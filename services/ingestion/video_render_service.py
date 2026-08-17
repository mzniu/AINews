"""Render ingested article video using the homepage animated-video pipeline."""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from loguru import logger

from api.schemas.request_models import CreateAnimatedVideoRequest, ImageWithDuration


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


def render_ingested_video(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    bgm_path: str,
    background_image: str = "static/imgs/bg.png",
    clip_duration_sec: float = 2.5,
    template: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(image_paths) < 1:
        return {"success": False, "error": "insufficient_images", "count": len(image_paths)}

    durations = resolve_ingested_clip_durations(len(image_paths), template=template)
    if len(durations) < len(image_paths):
        durations = durations + [clip_duration_sec] * (len(image_paths) - len(durations))

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
