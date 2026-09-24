"""Desktop runtime configuration (video renderer preferences)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from services.ingestion.remotion_render_service import remotion_available
from services.ingestion.video_renderer_config import (
    build_video_renderer_status,
    save_desktop_runtime_config,
)

router = APIRouter(prefix="/api/runtime", tags=["runtime"])

_last_render_renderer: str | None = None


def set_last_render_renderer(renderer: str | None) -> None:
    global _last_render_renderer
    _last_render_renderer = renderer


class VideoRendererUpdate(BaseModel):
    preferred: Literal["auto", "remotion", "python"] | None = None
    allow_python_fallback: bool | None = None


@router.get("/video-renderer")
def get_video_renderer_status():
    return build_video_renderer_status(
        remotion_available_fn=remotion_available,
        last_render_renderer=_last_render_renderer,
    )


@router.put("/video-renderer")
def put_video_renderer_status(body: VideoRendererUpdate):
    patch: dict[str, Any] = {}
    if body.preferred is not None:
        patch["preferred"] = body.preferred
    if body.allow_python_fallback is not None:
        patch["allow_python_fallback"] = body.allow_python_fallback
    save_desktop_runtime_config(patch)
    return get_video_renderer_status()
