"""Render 3:4 video cover image with video-like layout."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from PIL import Image, ImageDraw

from api.routes.video_routes import (
    MAIN_SUBTITLE_GAP_PX,
    _clamp_percent,
    _load_fonts,
    _resolve_animated_title_lines,
    _resolve_background_image_path,
    _subtitle_block_height,
)
from api.schemas.request_models import CreateAnimatedVideoRequest
from src.utils.config import Config
from utils.video_utils import _render_frame_animated

DEFAULT_COVER_WIDTH = 1080
DEFAULT_COVER_HEIGHT = 1440
COVER_TITLE_FONT_SIZE = 72
COVER_SUBTITLE_FONT_SIZE = 68


def crop_center_to_aspect(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = image.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h if src_h else target_ratio
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        cropped = image.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        cropped = image.crop((0, top, src_w, top + new_h))
    return cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)


def _resolve_asset_path(path_str: str) -> Path:
    cleaned = str(path_str or "").strip().lstrip("/").replace("\\", "/")
    return (Config.ROOT_DIR / cleaned).resolve()


def render_article_cover(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_path: str,
    background_image: str = "static/imgs/bg.png",
    width: int = DEFAULT_COVER_WIDTH,
    height: int = DEFAULT_COVER_HEIGHT,
) -> dict[str, Any]:
    asset_path = _resolve_asset_path(image_path)
    if not asset_path.is_file():
        return {"success": False, "error": f"cover_source_missing: {image_path}"}

    bg_path = _resolve_background_image_path(background_image)
    if bg_path.exists():
        bg_template = crop_center_to_aspect(Image.open(bg_path).convert("RGB"), width, height)
    else:
        bg_template = Image.new("RGB", (width, height), (102, 126, 234))

    request = CreateAnimatedVideoRequest(
        summary=draft.get("summary") or "",
        images=[],
        audio_path="static/music/background.mp3",
        main_line1=draft.get("main_line1") or "",
        main_line2=draft.get("main_line2") or "",
        subtitle=draft.get("sub_title") or "",
        subtitle2=draft.get("sub_title2") or "",
        background_image_path=background_image,
        tags=draft.get("tags") or "",
        summary_highlight_keywords=draft.get("highlight_keywords") or [],
        show_summary=False,
        title_y_percent=12.0,
    )

    img_width, img_height = bg_template.size
    temp_draw = ImageDraw.Draw(bg_template.copy())
    title_font, subtitle_font, _ = _load_fonts(
        None,
        COVER_TITLE_FONT_SIZE,
        subtitle_font_size=COVER_SUBTITLE_FONT_SIZE,
    )
    margin = int(img_width * 0.08)
    text_width = img_width - 2 * margin
    main_title_lines, sub_title_lines = _resolve_animated_title_lines(
        request, temp_draw, title_font, subtitle_font, text_width
    )
    main_title_height = sum(
        temp_draw.textbbox((0, 0), line, font=title_font)[3]
        - temp_draw.textbbox((0, 0), line, font=title_font)[1]
        + 14
        for line in main_title_lines
    )
    sub_title_height = (
        _subtitle_block_height(sub_title_lines, subtitle_font, temp_draw)
        if sub_title_lines
        else 0
    )
    title_height = main_title_height + (
        sub_title_height + MAIN_SUBTITLE_GAP_PX if sub_title_height else 0
    )
    title_start_y = int(img_height * (_clamp_percent(request.title_y_percent, 12.0, 0.0, 45.0) / 100.0))
    title_info = (
        title_font,
        subtitle_font,
        main_title_lines,
        sub_title_lines,
        title_start_y,
        main_title_height,
        margin,
        text_width,
    )

    with Image.open(asset_path) as user_img:
        if user_img.mode != "RGBA":
            user_img = user_img.convert("RGBA")
        target_w = img_width
        ratio = target_w / max(user_img.width, 1)
        target_h = int(user_img.height * ratio)
        user_img_resized = user_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    paste_x = (img_width - target_w) // 2
    content_bottom = img_height - 40
    available = content_bottom - (title_start_y + title_height + 30)
    final_paste_y = title_start_y + title_height + 30 + max(0, (available - target_h) // 2)
    final_paste_y = max(title_start_y + title_height + 30, final_paste_y)

    frame_np = _render_frame_animated(
        bg_template,
        user_img_resized,
        paste_x,
        final_paste_y,
        target_w,
        target_h,
        img_width,
        img_height,
        title_info,
        None,
        t=2.5,
        entrance_duration=0.4,
        hold_with_text_start=0.8,
        anim_type="zoom_in",
        title_slide_entrance=False,
        main_line1_color="#FFFFFF",
        main_line2_color="#FFFFFF",
    )
    final = Image.fromarray(np.asarray(frame_np, dtype=np.uint8))

    out_dir = Config.ROOT_DIR / "data" / "publish" / "covers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{article_id}_cover.jpg"
    final.save(out_path, format="JPEG", quality=92)
    rel = out_path.relative_to(Config.ROOT_DIR).as_posix()
    logger.info(f"Cover rendered for {article_id}: {rel}")
    return {
        "success": True,
        "cover_path": rel,
        "source_image": image_path,
        "width": width,
        "height": height,
    }
