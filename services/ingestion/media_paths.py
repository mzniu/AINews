"""Recover generated video/cover paths from pipeline status JSON."""
from __future__ import annotations

import json
from typing import Any

from src.db.models.ingestion import IngestedArticle


def _nonempty(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def media_paths_from_prep_status(prep: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not isinstance(prep, dict):
        return None, None
    steps = prep.get("steps") if isinstance(prep.get("steps"), dict) else {}
    intro = steps.get("prepend_cover_intro") if isinstance(steps.get("prepend_cover_intro"), dict) else {}
    render = steps.get("render_video") if isinstance(steps.get("render_video"), dict) else {}
    cover = steps.get("render_cover") if isinstance(steps.get("render_cover"), dict) else {}
    video = None
    if intro.get("success"):
        video = _nonempty(intro.get("video_path"))
    if video is None:
        video = _nonempty(render.get("video_path"))
    return video, _nonempty(cover.get("cover_path"))


def restore_generated_media_paths(article: IngestedArticle) -> bool:
    """Fill empty generated_* columns from video_prep_status_json. Returns True if changed."""
    raw = article.video_prep_status_json
    if not raw:
        return False
    try:
        prep = json.loads(raw)
    except json.JSONDecodeError:
        return False
    video, cover = media_paths_from_prep_status(prep)
    changed = False
    if video and not _nonempty(article.generated_video_path):
        article.generated_video_path = video
        changed = True
    if cover and not _nonempty(article.generated_cover_path):
        article.generated_cover_path = cover
        changed = True
    return changed
