"""Chronicle-frame compositor: 9:16 video frame; cover uses the same canvas without summary."""
from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from src.utils.config import Config
from utils.summary_highlights import finalize_highlight_keywords
from utils.video_utils import (
    DEFAULT_SUMMARY_HIGHLIGHT_COLOR,
    _build_highlight_pattern,
    _find_font_path,
    _load_fonts,
    _split_line_highlight_segments,
    merge_summary_highlight_keywords,
)

CANVAS_W = 1080
CANVAS_H = 1920
COVER_W = 1080
COVER_H = 1920
DEFAULT_TOP_PAD = 0.05
DEFAULT_SUMMARY_Y_PERCENT = 75.2
DEFAULT_FOOTER_Y_PERCENT = 85.2
DEFAULT_CARD_TOP_PERCENT = 32.0
DEFAULT_CARD_BOTTOM_PERCENT = 68.0
DEFAULT_CARD_LEFT_PERCENT = 8.0
DEFAULT_CARD_RIGHT_PERCENT = 92.0
DEFAULT_CARD_INSET_PX = 16
DEFAULT_CARD_MOTION_END_SCALE = 1.22
DEFAULT_CARD_MOTION_PAN = 0.7
DEFAULT_CARD_MOTION_EFFECTS = (
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "pan_down",
    "zoom_in_left",
    "zoom_in_right",
    "zoom_in_up",
    "zoom_in_down",
)


def _crop_center_to_aspect(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
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


def _hex_rgb(value: Any, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return fallback


def _pct(value: float, total: int) -> int:
    return int(total * value)


def crop_top_cover(frame: Image.Image, width: int, height: int) -> Image.Image:
    cropped = frame.crop((0, 0, frame.width, min(height, frame.height)))
    if cropped.size != (width, height):
        return cropped.resize((width, height), Image.Resampling.LANCZOS)
    return cropped


def _wrap_line(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = char
        if len(lines) >= 3:
            break
    if current and len(lines) < 3:
        lines.append(current)
    return lines


def _strip_prefixes(text: str, prefixes: list[str]) -> str:
    cleaned = str(text or "").strip()
    for prefix in prefixes or []:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    return cleaned


def _layout_top_pad(typo: dict[str, Any] | None = None) -> float:
    return float((typo or {}).get("top_pad_percent", DEFAULT_TOP_PAD * 100.0)) / 100.0


def _layout_section(template: dict[str, Any] | None = None) -> dict[str, Any]:
    return (template or {}).get("layout") or {}


DEFAULT_TITLE_PLACEMENT = "above_card"


def _title_placement(layout: dict[str, Any] | None = None) -> str:
    value = str((layout or {}).get("title_placement") or DEFAULT_TITLE_PLACEMENT).strip().lower()
    if value == "below_card":
        return "below_card"
    return DEFAULT_TITLE_PLACEMENT


def _title_top_y(height: int, layout: dict[str, Any], typo: dict[str, Any]) -> int:
    if layout.get("title_top_percent") is not None:
        return _pct(float(layout["title_top_percent"]) / 100.0, height)
    return _pct(0.11 + _layout_top_pad(typo), height)


def _card_box(
    width: int,
    height: int,
    template: dict[str, Any] | None = None,
) -> tuple[int, int, int, int]:
    layout = _layout_section(template)
    left = _pct(float(layout.get("card_left_percent", DEFAULT_CARD_LEFT_PERCENT)) / 100.0, width)
    right = _pct(float(layout.get("card_right_percent", DEFAULT_CARD_RIGHT_PERCENT)) / 100.0, width)
    top = _pct(float(layout.get("card_top_percent", DEFAULT_CARD_TOP_PERCENT)) / 100.0, height)
    bottom = _pct(float(layout.get("card_bottom_percent", DEFAULT_CARD_BOTTOM_PERCENT)) / 100.0, height)
    return left, top, right, bottom


def hero_inner_box(
    width: int,
    height: int,
    template: dict[str, Any] | None = None,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = _card_box(width, height, template)
    inset = int(_layout_section(template).get("card_inset_px") or DEFAULT_CARD_INSET_PX)
    return left + inset, top + inset, right - inset, bottom - inset


def ken_burns_scale_at(t: float, duration: float, start: float, end: float) -> float:
    if duration <= 0:
        return float(end)
    progress = max(0.0, min(1.0, float(t) / float(duration)))
    ease = 1 - (1 - progress) ** 2
    return float(start) + (float(end) - float(start)) * ease


def hero_motion_at(
    t: float,
    duration: float,
    effect: str,
    *,
    end_scale: float = DEFAULT_CARD_MOTION_END_SCALE,
    pan: float = DEFAULT_CARD_MOTION_PAN,
) -> tuple[float, float, float]:
    """Return (scale, offset_x, offset_y). Offsets are -1..1 within the zoomed crop."""
    progress = 1.0 if duration <= 0 else max(0.0, min(1.0, float(t) / float(duration)))
    ease = 1 - (1 - progress) ** 2
    scale = max(1.0, float(end_scale))
    amp = max(0.0, min(1.0, float(pan)))
    name = str(effect or "zoom_in").strip().lower()
    zoom = 1.0 + (scale - 1.0) * ease
    if name == "zoom_out":
        return (scale + (1.0 - scale) * ease, 0.0, 0.0)
    if name == "pan_left":
        return (scale, amp * (1.0 - 2.0 * ease), 0.0)
    if name == "pan_right":
        return (scale, -amp * (1.0 - 2.0 * ease), 0.0)
    if name == "pan_up":
        return (scale, 0.0, amp * (1.0 - 2.0 * ease))
    if name == "pan_down":
        return (scale, 0.0, -amp * (1.0 - 2.0 * ease))
    if name == "zoom_in_left":
        return (zoom, -amp * ease, 0.0)
    if name == "zoom_in_right":
        return (zoom, amp * ease, 0.0)
    if name == "zoom_in_up":
        return (zoom, 0.0, -amp * ease)
    if name == "zoom_in_down":
        return (zoom, 0.0, amp * ease)
    return (zoom, 0.0, 0.0)


def pick_card_motion_effect(
    effects: list[str] | tuple[str, ...],
    *,
    seed: str | int | None = None,
    index: int = 0,
) -> str:
    names = [str(item).strip() for item in (effects or []) if str(item).strip()]
    if not names:
        return "zoom_in"
    rng = random.Random(f"{seed}:{index}")
    return rng.choice(names)


def resolve_card_motion(video_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = video_cfg or {}
    motion = cfg.get("card_motion") if isinstance(cfg.get("card_motion"), dict) else {}
    enabled = motion.get("enabled")
    if enabled is None:
        enabled = bool(cfg.get("card_ken_burns", True))
    end_scale = float(
        motion.get("end_scale") or cfg.get("ken_burns_end_scale") or DEFAULT_CARD_MOTION_END_SCALE
    )
    pan = float(motion.get("pan_percent", DEFAULT_CARD_MOTION_PAN * 100.0)) / 100.0
    raw_effects = motion.get("effects") or list(DEFAULT_CARD_MOTION_EFFECTS)
    effects = [str(item).strip() for item in raw_effects if str(item).strip()]
    return {
        "enabled": bool(enabled) and end_scale > 1.0,
        "end_scale": max(1.0, end_scale),
        "pan": max(0.0, min(1.0, pan)),
        "effects": effects or list(DEFAULT_CARD_MOTION_EFFECTS),
        "random": bool(motion.get("random", True)),
    }


def scaled_hero(
    image: Image.Image,
    inner_w: int,
    inner_h: int,
    scale: float,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> Image.Image:
    inner_w = max(1, int(inner_w))
    inner_h = max(1, int(inner_h))
    rgb = image.convert("RGB")
    scale = max(1.0, float(scale))
    if scale <= 1.0001:
        return _crop_center_to_aspect(rgb, inner_w, inner_h)
    zoom_w = max(inner_w, int(inner_w * scale))
    zoom_h = max(inner_h, int(inner_h * scale))
    hero = _crop_center_to_aspect(rgb, zoom_w, zoom_h)
    max_x = max(0, zoom_w - inner_w)
    max_y = max(0, zoom_h - inner_h)
    ox = max(-1.0, min(1.0, float(offset_x)))
    oy = max(-1.0, min(1.0, float(offset_y)))
    x0 = int(round((max_x / 2.0) * (1.0 + ox)))
    y0 = int(round((max_y / 2.0) * (1.0 + oy)))
    x0 = max(0, min(max_x, x0))
    y0 = max(0, min(max_y, y0))
    return hero.crop((x0, y0, x0 + inner_w, y0 + inner_h))


_BACKDROP_CACHE: dict[tuple, Image.Image] = {}


def _build_tech_backdrop(
    width: int,
    height: int,
    *,
    bg: tuple[int, int, int],
    glow: tuple[int, int, int],
    accent: tuple[int, int, int],
    accent_dim: tuple[int, int, int],
) -> Image.Image:
    yy, xx = np.ogrid[:height, :width]
    cx = width / 2.0
    cy = height * 0.48
    nx = (xx - cx) / max(1.0, width * 0.55)
    ny = (yy - cy) / max(1.0, height * 0.46)
    dist = np.sqrt(nx * nx + ny * ny)

    arr = np.empty((height, width, 3), dtype=np.float32)
    arr[:] = bg
    well = np.clip(1.0 - dist * 0.82, 0.0, 1.0) ** 1.45
    for i in range(3):
        arr[:, :, i] += (glow[i] - arr[:, :, i]) * well * 0.62
    core = np.clip(1.0 - dist * 1.25, 0.0, 1.0) ** 2.1
    for i in range(3):
        arr[:, :, i] += (accent[i] - arr[:, :, i]) * core * 0.16
    vignette = np.clip(dist * 0.38, 0.0, 1.0) ** 1.35
    arr *= (1.0 - vignette * 0.42)[..., None]
    arr *= (1.0 - ((yy % 3) == 0).astype(np.float32) * 0.055)[..., None]
    noise = np.random.default_rng(7).normal(0.0, 2.8, (height, width, 1)).astype(np.float32)
    arr += noise
    frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    grid = (*accent_dim, 36)
    grid_hi = (*accent, 28)
    step_x, step_y = 54, 48
    for x in range(0, width, step_x):
        od.line((x, 0, x, height), fill=grid_hi if x % (step_x * 4) == 0 else grid, width=1)
    for y in range(0, height, step_y):
        od.line((0, y, width, y), fill=grid_hi if y % (step_y * 4) == 0 else grid, width=1)

    cxi, cyi = int(cx), int(cy)
    rings = ((0.26, 1, 42), (0.40, 2, 58), (0.56, 1, 40), (0.74, 1, 32))
    for scale, stroke, alpha in rings:
        rx = int(width * scale * 0.50)
        ry = int(height * scale * 0.36)
        color = (*accent, alpha) if stroke == 2 else (*accent_dim, alpha)
        od.ellipse((cxi - rx, cyi - ry, cxi + rx, cyi + ry), outline=color, width=stroke)

    rx, ry = int(width * 0.20), int(height * 0.144)
    tick, tick_color = 16, (*accent, 70)
    od.line((cxi, cyi - ry - tick, cxi, cyi - ry + tick), fill=tick_color, width=1)
    od.line((cxi, cyi + ry - tick, cxi, cyi + ry + tick), fill=tick_color, width=1)
    od.line((cxi - rx - tick, cyi, cxi - rx + tick, cyi), fill=tick_color, width=1)
    od.line((cxi + rx - tick, cyi, cxi + rx + tick, cyi), fill=tick_color, width=1)

    vanish_y = int(height * 0.60)
    for i in range(-7, 8):
        x_bottom = cxi + i * int(width * 0.11)
        od.line((cxi, vanish_y, x_bottom, height + 30), fill=(*accent_dim, 40), width=1)
    for frac in (0.76, 0.82, 0.88, 0.93, 0.97):
        y = int(height * frac)
        span = int(width * max(0.18, frac - 0.52))
        od.line((cxi - span, y, cxi + span, y), fill=(*accent_dim, 34), width=1)

    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def _tech_backdrop(
    width: int,
    height: int,
    *,
    bg: tuple[int, int, int],
    glow: tuple[int, int, int],
    accent: tuple[int, int, int],
    accent_dim: tuple[int, int, int],
) -> Image.Image:
    key = (width, height, bg, glow, accent, accent_dim)
    cached = _BACKDROP_CACHE.get(key)
    if cached is None:
        cached = _build_tech_backdrop(
            width, height, bg=bg, glow=glow, accent=accent, accent_dim=accent_dim
        )
        _BACKDROP_CACHE[key] = cached
    return cached.copy()


def _truetype(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    size = max(12, int(size))
    names = ["msyhbd.ttc", "simhei.ttf"] if bold else ["msyh.ttc", "simhei.ttf"]
    path = _find_font_path(names) or _find_font_path(["simhei.ttf"])
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _draw_title_block(
    draw: ImageDraw.ImageDraw,
    *,
    draft: dict[str, Any],
    title_x: int,
    title_top: int,
    title_max_w: int,
    title_font: ImageFont.ImageFont,
    subtitle_font: ImageFont.ImageFont,
    sub_size: int,
    text_color: tuple[int, int, int],
    title_hi: tuple[int, int, int],
    hook_color: tuple[int, int, int],
    title_keywords: list[str],
) -> int:
    y = title_top
    for line in _wrap_line(str(draft.get("main_line1") or ""), title_font, title_max_w, draw)[:2]:
        _draw_highlighted_line(
            draw, title_x, y, line, title_font, text_color, title_hi, title_keywords
        )
        y += (draw.textbbox((0, 0), line, font=title_font)[3] - draw.textbbox((0, 0), line, font=title_font)[1]) + 8
    if draft.get("main_line2"):
        for line in _wrap_line(str(draft.get("main_line2")), subtitle_font, title_max_w, draw)[:1]:
            _draw_highlighted_line(
                draw, title_x, y, line, subtitle_font, text_color, title_hi, title_keywords
            )
            y += sub_size + 6
    if draft.get("sub_title"):
        for line in _wrap_line(str(draft.get("sub_title")), subtitle_font, title_max_w, draw)[:1]:
            draw.text((title_x, y), line, font=subtitle_font, fill=text_color)
            y += sub_size + 4
    if draft.get("sub_title2"):
        for line in _wrap_line(str(draft.get("sub_title2")), subtitle_font, title_max_w, draw)[:1]:
            draw.text((title_x, y), line, font=subtitle_font, fill=hook_color)
            bbox = draw.textbbox((0, 0), line, font=subtitle_font)
            y += (bbox[3] - bbox[1]) + 4
    return y


def _draw_highlighted_line(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    base_color: tuple[int, int, int],
    highlight_color: tuple[int, int, int],
    keywords: list[str],
) -> None:
    pattern = _build_highlight_pattern(keywords)
    if not pattern:
        draw.text((x, y), text, font=font, fill=base_color)
        return
    cx = float(x)
    for seg, is_hi in _split_line_highlight_segments(text, pattern):
        if not seg:
            continue
        fill = highlight_color if is_hi else base_color
        draw.text((int(cx), y), seg, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), seg, font=font)
        cx += bbox[2] - bbox[0]


def render_chronicle_frame(
    *,
    draft: dict[str, Any],
    image: Image.Image,
    template: dict[str, Any],
    include_footer: bool = True,
    include_summary: bool | None = None,
    source_name: str | None = None,  # ignored; kept so callers cannot accidentally paint it
    ken_burns_scale: float = 1.0,
    include_hero: bool = True,
) -> Image.Image:
    del source_name  # never drawn
    if include_summary is None:
        include_summary = include_footer
    canvas = template.get("canvas") or {}
    width = int(canvas.get("width") or CANVAS_W)
    height = int(canvas.get("height") or CANVAS_H)
    palette = template.get("palette") or {}
    chrome = template.get("chrome") or {}
    typo = template.get("typography") or {}

    bg = _hex_rgb(palette.get("bg"), (7, 11, 16))
    glow = _hex_rgb(palette.get("bg_glow"), (14, 42, 68))
    accent = _hex_rgb(palette.get("accent"), (61, 220, 255))
    accent_dim = _hex_rgb(palette.get("accent_dim"), (26, 106, 138))
    text_color = _hex_rgb(palette.get("text"), (244, 247, 250))
    muted = _hex_rgb(palette.get("text_muted"), (139, 150, 168))
    card_color = _hex_rgb(palette.get("card"), (255, 255, 255))
    frame_color = _hex_rgb(palette.get("frame"), accent_dim)
    title_hi = _hex_rgb(typo.get("title_highlight_color"), DEFAULT_SUMMARY_HIGHLIGHT_COLOR)

    frame = _tech_backdrop(
        width,
        height,
        bg=bg,
        glow=glow,
        accent=accent,
        accent_dim=accent_dim,
    )
    draw = ImageDraw.Draw(frame)

    inset = _pct(0.024, width)
    draw.rectangle((inset, inset, width - inset, height - inset), outline=frame_color, width=2)
    tick = 14
    for x, y in (
        (inset, inset),
        (width - inset - tick, inset),
        (inset, height - inset - tick),
        (width - inset - tick, height - inset - tick),
    ):
        draw.rectangle((x, y, x + tick, y + tick), outline=accent_dim, width=2)

    title_size = int(typo.get("title_font_size") or 64)
    sub_size = int(typo.get("subtitle_font_size") or 47)
    brand_sub_size = int(typo.get("brand_sub_font_size") or 28)
    footer_size = int(typo.get("footer_font_size") or 40)
    title_font, subtitle_font, _meta_font = _load_fonts(
        None,
        title_size,
        subtitle_font_size=sub_size,
    )
    brand_font = _truetype(int(typo.get("brand_font_size") or 43))
    brand_sub_font = _truetype(brand_sub_size)
    footer_font = _truetype(footer_size)
    small_font = _truetype(max(12, int(round(footer_size * 0.9))))

    brand = str(chrome.get("brand") or "小牛聊AI")
    glyph = str(chrome.get("mark_glyph") or "牛")
    top_pad = _layout_top_pad(typo)
    header_y = _pct(0.038 + top_pad, height)
    mark_box = (inset + 16, header_y, inset + 16 + 64, header_y + 64)
    draw.rectangle(mark_box, outline=accent, width=2)
    gb = draw.textbbox((0, 0), glyph, font=brand_font)
    gx = mark_box[0] + (64 - (gb[2] - gb[0])) // 2
    gy = mark_box[1] + (64 - (gb[3] - gb[1])) // 2 - gb[1]
    draw.text((gx, gy), glyph, font=brand_font, fill=text_color)
    brand_xy = (mark_box[2] + 16, mark_box[1] + 4)
    draw.text(brand_xy, brand, font=brand_font, fill=text_color)
    brand_sub = str(chrome.get("brand_sub") or "")
    if brand_sub:
        brand_box = draw.textbbox(brand_xy, brand, font=brand_font)
        sub_y = brand_box[3] + 10
        draw.text((brand_xy[0], sub_y), brand_sub, font=brand_sub_font, fill=muted)

    year = str(datetime.now().year)
    badge = f"RECORD {year}"
    bw = draw.textbbox((0, 0), badge, font=small_font)
    badge_w = bw[2] - bw[0] + 24
    badge_box = (width - inset - 20 - badge_w, mark_box[1] + 8, width - inset - 20, mark_box[1] + 44)
    draw.rectangle(badge_box, outline=accent_dim, width=1)
    draw.text((badge_box[0] + 12, badge_box[1] + 6), badge, font=small_font, fill=accent)

    layout = _layout_section(template)
    placement = _title_placement(layout)
    title_top = _title_top_y(height, layout, typo)
    rule_x = _pct(0.045, width)
    title_x = rule_x + 18
    title_max_w = width - title_x - inset - 20
    title_blob = " ".join(str(draft.get(key) or "") for key in ("main_line1", "main_line2"))
    title_keywords = finalize_highlight_keywords(
        merge_summary_highlight_keywords(
            list(draft.get("highlight_keywords") or []),
            str(draft.get("tags") or ""),
        ),
        title_blob,
    )
    hook_color = _hex_rgb(typo.get("subtitle2_color"), accent)
    title_kwargs = dict(
        draft=draft,
        title_x=title_x,
        title_top=title_top,
        title_max_w=title_max_w,
        title_font=title_font,
        subtitle_font=subtitle_font,
        sub_size=sub_size,
        text_color=text_color,
        title_hi=title_hi,
        hook_color=hook_color,
        title_keywords=title_keywords,
    )

    if placement == "above_card":
        draw.line((rule_x, title_top, rule_x, title_top + _pct(0.14, height)), fill=accent_dim, width=2)
        _draw_title_block(draw, **title_kwargs)

    left, top, right, bottom = _card_box(width, height, template)
    draw.rounded_rectangle((left, top, right, bottom), radius=12, fill=card_color)

    inner = hero_inner_box(width, height, template)
    if include_hero:
        inner_w = max(1, inner[2] - inner[0])
        inner_h = max(1, inner[3] - inner[1])
        hero = scaled_hero(image, inner_w, inner_h, ken_burns_scale)
        frame.paste(hero, (inner[0], inner[1]))

    if placement == "below_card":
        title_bottom = _draw_title_block(draw, **title_kwargs)
        if bool(layout.get("title_rule")) and title_bottom > title_top:
            rule_w = max(1, int(layout.get("title_rule_width_px") or 4))
            draw.rectangle((rule_x, title_top, rule_x + rule_w, title_bottom), fill=accent)

    if include_footer:
        footer_y_pct = float(typo.get("footer_y_percent", DEFAULT_FOOTER_Y_PERCENT)) / 100.0
        footer_y = _pct(footer_y_pct, height)
        if include_summary:
            footer = _strip_prefixes(
                str(draft.get("summary") or ""),
                list(chrome.get("footer_strip_prefixes") or []),
            )
            footer_keywords = finalize_highlight_keywords(
                merge_summary_highlight_keywords(
                    list(draft.get("highlight_keywords") or []),
                    str(draft.get("tags") or ""),
                ),
                footer,
            )
            footer_hi = _hex_rgb(typo.get("footer_highlight_color"), accent)
            summary_fill = _hex_rgb(typo.get("summary_color"), text_color)
            summary_y_pct = float(typo.get("summary_y_percent", DEFAULT_SUMMARY_Y_PERCENT)) / 100.0
            summary_y = _pct(summary_y_pct, height)
            footer_lines = _wrap_line(footer, footer_font, _pct(0.78, width), draw)
            fy = summary_y
            line_gap = max(6, int(round(footer_size * 0.28)))
            for line in footer_lines[:3]:
                bbox = draw.textbbox((0, 0), line, font=footer_font)
                fx = (width - (bbox[2] - bbox[0])) // 2
                _draw_highlighted_line(
                    draw, fx, fy, line, footer_font, summary_fill, footer_hi, footer_keywords
                )
                fy += footer_size + line_gap
        draw.line(
            (rule_x, footer_y, rule_x, _pct(footer_y_pct + 0.10, height)),
            fill=accent_dim,
            width=2,
        )
        draw.text(
            (rule_x + 14, _pct(footer_y_pct + 0.02, height)),
            str(chrome.get("footer_left") or "快讯档案"),
            font=small_font,
            fill=muted,
        )

    return frame


def render_chronicle_cover(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_path: str,
    template: dict[str, Any],
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    cleaned = str(image_path or "").strip().lstrip("/").replace("\\", "/")
    asset_path = (Config.ROOT_DIR / cleaned).resolve()
    if not asset_path.is_file():
        asset_path = Path(image_path)
    if not asset_path.is_file():
        return {"success": False, "error": f"cover_source_missing: {image_path}"}

    canvas = template.get("canvas") or {}
    cover_w = int(canvas.get("width") or COVER_W)
    cover_h = int(canvas.get("height") or COVER_H)

    with Image.open(asset_path) as src:
        cover = render_chronicle_frame(
            draft=draft,
            image=src.convert("RGB"),
            template=template,
            include_footer=True,
            include_summary=False,
        )
    if cover.size != (cover_w, cover_h):
        cover = cover.resize((cover_w, cover_h), Image.Resampling.LANCZOS)
    out_dir = Path(output_dir) if output_dir else Config.ROOT_DIR / "data" / "publish" / "covers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{article_id}_cover.jpg"
    cover.save(out_path, format="JPEG", quality=92)
    try:
        rel = out_path.resolve().relative_to(Config.ROOT_DIR).as_posix()
    except ValueError:
        rel = out_path.name
    logger.info(f"Chronicle cover rendered for {article_id}: {rel}")
    return {
        "success": True,
        "cover_path": rel,
        "width": cover_w,
        "height": cover_h,
        "layout_kind": "chronicle_frame",
    }


def render_chronicle_video(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    bgm_path: str,
    template: dict[str, Any],
    durations: list[float],
) -> dict[str, Any]:
    from moviepy import AudioFileClip, ImageClip, VideoClip, concatenate_videoclips

    canvas = template.get("canvas") or {}
    fps = int(canvas.get("fps") or 24)
    video_cfg = template.get("video") or {}
    motion = resolve_card_motion(video_cfg)
    width = int(canvas.get("width") or CANVAS_W)
    height = int(canvas.get("height") or CANVAS_H)
    clips = []
    for index, raw_path in enumerate(image_paths):
        cleaned = str(raw_path or "").strip().lstrip("/").replace("\\", "/")
        path = (Config.ROOT_DIR / cleaned).resolve()
        if not path.is_file():
            path = Path(raw_path)
        if not path.is_file():
            continue
        duration = float(durations[index]) if index < len(durations) else 2.5
        src_rgb = Image.open(path).convert("RGB")
        if motion["enabled"]:
            chrome = render_chronicle_frame(
                draft=draft,
                image=src_rgb,
                template=template,
                include_footer=True,
                include_hero=False,
            )
            inner = hero_inner_box(width, height, template)
            inner_w = max(1, inner[2] - inner[0])
            inner_h = max(1, inner[3] - inner[1])
            if motion["random"]:
                effect = pick_card_motion_effect(
                    motion["effects"],
                    seed=article_id,
                    index=index,
                )
            else:
                effect = motion["effects"][index % len(motion["effects"])]

            def make_frame(
                t,
                _src=src_rgb,
                _chrome=chrome,
                _inner=inner,
                _iw=inner_w,
                _ih=inner_h,
                _dur=duration,
                _effect=effect,
                _end=motion["end_scale"],
                _pan=motion["pan"],
            ):
                frame = _chrome.copy()
                scale, ox, oy = hero_motion_at(
                    t, _dur, _effect, end_scale=_end, pan=_pan
                )
                frame.paste(
                    scaled_hero(_src, _iw, _ih, scale, offset_x=ox, offset_y=oy),
                    (_inner[0], _inner[1]),
                )
                return np.asarray(frame)

            clips.append(VideoClip(make_frame, duration=duration).with_fps(fps))
        else:
            still = render_chronicle_frame(
                draft=draft,
                image=src_rgb,
                template=template,
                include_footer=True,
            )
            clips.append(ImageClip(np.asarray(still, dtype=np.uint8)).with_duration(duration))
    if not clips:
        return {"success": False, "error": "insufficient_images"}
    video = concatenate_videoclips(clips, method="compose").with_fps(fps)
    audio_file = Path(str(bgm_path or "").lstrip("/"))
    if not audio_file.is_file():
        audio_file = Config.ROOT_DIR / str(bgm_path or "").lstrip("/").replace("\\", "/")
    if audio_file.is_file():
        from services.ingestion.cover_video_utils import fit_audio_to_duration

        audio = AudioFileClip(str(audio_file))
        video = video.with_audio(fit_audio_to_duration(audio, float(video.duration)))
    out_dir = Config.ROOT_DIR / "data" / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{article_id}_chronicle.mp4"
    video.write_videofile(str(out_path), fps=fps, codec="libx264", audio_codec="aac", logger=None)
    rel = f"/{out_path.relative_to(Config.ROOT_DIR).as_posix()}"
    return {"success": True, "video_path": rel, "duration": float(video.duration)}
