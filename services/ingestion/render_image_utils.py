"""Helpers for validating local images before video/cover render."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils.paths import resolve_local_asset_path

DEFAULT_MIN_RENDER_PX = 100


def resolve_local_image_path(path: str | None) -> Path | None:
    return resolve_local_asset_path(path)


def is_renderable_local_image(
    path: str | Path | None,
    *,
    min_px: int = DEFAULT_MIN_RENDER_PX,
) -> bool:
    file_path = path if isinstance(path, Path) else resolve_local_image_path(str(path or ""))
    if file_path is None or not file_path.is_file():
        return False
    try:
        from PIL import Image

        with Image.open(file_path) as img:
            width, height = img.size
    except Exception:
        return False
    if width < min_px or height < min_px:
        return False
    return True


def filter_renderable_image_dicts(
    images: list[dict[str, Any]],
    *,
    min_px: int = DEFAULT_MIN_RENDER_PX,
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in images:
        local_path = item.get("local_path")
        if not local_path:
            continue
        if not is_renderable_local_image(local_path, min_px=min_px):
            continue
        kept.append(item)
    return kept
