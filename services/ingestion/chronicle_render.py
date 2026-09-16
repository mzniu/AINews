"""Chronicle-frame compositor: 9:16 video frame; cover uses the same canvas without summary."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from src.utils.config import Config
from src.utils.paths import path_relative_to_data, resolve_local_asset_path, to_data_url_path, use_writable_workdir
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
    if current:
        lines.append(current)
    return lines


def _summary_line_step(font_size: int) -> int:
    line_gap = max(6, int(round(font_size * 0.28)))
    return font_size + line_gap


def _summary_max_lines(*, summary_y: int, footer_y: int, font_size: int, bottom_pad: int = 12) -> int:
    available = max(0, footer_y - summary_y - bottom_pad)
    step = _summary_line_step(font_size)
    if step <= 0:
        return 1
    return max(1, available // step)


def _prepare_summary_lines(
    draw: ImageDraw.ImageDraw,
    footer: str,
    *,
    max_width: int,
    summary_y: int,
    footer_y: int,
    preferred_font_size: int,
    min_font_size: int = 28,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    font_size = max(min_font_size, int(preferred_font_size))
    while font_size >= min_font_size:
        font = _truetype(font_size)
        lines = _wrap_line(footer, font, max_width, draw)
        budget = _summary_max_lines(summary_y=summary_y, footer_y=footer_y, font_size=font_size)
        if len(lines) <= budget:
            return font, lines, font_size
        if font_size <= min_font_size:
            return font, lines[:budget], font_size
        font_size -= 2
    font = _truetype(min_font_size)
    lines = _wrap_line(footer, font, max_width, draw)
    budget = _summary_max_lines(summary_y=summary_y, footer_y=footer_y, font_size=min_font_size)
    return font, lines[:budget], min_font_size


def _strip_prefixes(text: str, prefixes: list[str]) -> str:
    cleaned = str(text or "").strip()
    for prefix in prefixes or []:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    return cleaned


DEFAULT_SUMMARY_ANIMATION: dict[str, Any] = {
    "mode": "static",
    "scope": "once",
    "chars_per_second": 14,
    "start_delay_sec": 0.35,
    "show_cursor": True,
    "cursor_blink_hz": 2,
    "cursor_hide_after_done_sec": 0.5,
    "fit_video_duration": False,
    "max_chars_per_second": 28,
    "tail_margin_sec": 0.5,
}


def parse_summary_animation_config(video_cfg: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict((video_cfg or {}).get("summary_animation") or {})
    merged = dict(DEFAULT_SUMMARY_ANIMATION)
    merged.update(raw)
    mode = str(merged.get("mode") or "static").strip().lower()
    merged["mode"] = "typewriter" if mode == "typewriter" else "static"
    return merged


def chronicle_content_global_t(
    *,
    cover_intro_sec: float,
    clip_durations: list[float],
    clip_index: int,
    t_within_clip: float,
) -> float:
    elapsed = float(cover_intro_sec)
    for idx in range(max(0, clip_index)):
        if idx < len(clip_durations):
            elapsed += float(clip_durations[idx])
    return elapsed + float(t_within_clip)


def summary_visible_chars(
    global_t: float,
    *,
    total_chars: int,
    anim_cfg: dict[str, Any],
    content_start_t: float = 0.0,
    video_duration: float | None = None,
) -> int:
    if total_chars <= 0:
        return 0
    if str(anim_cfg.get("mode") or "static") != "typewriter":
        return total_chars
    delay = float(anim_cfg.get("start_delay_sec", 0.35))
    cps = max(0.1, float(anim_cfg.get("chars_per_second", 14)))
    typing_t = float(global_t) - float(content_start_t) - delay
    if typing_t <= 0:
        return 0
    if anim_cfg.get("fit_video_duration") and video_duration is not None:
        tail = float(anim_cfg.get("tail_margin_sec", 0.5))
        max_cps = max(cps, float(anim_cfg.get("max_chars_per_second", 28)))
        budget = max(0.1, float(video_duration) - float(content_start_t) - delay - tail)
        needed_cps = total_chars / budget
        effective_cps = min(max_cps, max(cps, needed_cps))
        visible = int(typing_t * effective_cps)
        if float(global_t) >= float(video_duration) - tail:
            return total_chars
        return min(total_chars, visible)
    return min(total_chars, int(typing_t * cps))


def _partial_summary_lines(lines: list[str], visible_char_count: int) -> list[str]:
    if visible_char_count <= 0:
        return []
    remaining = visible_char_count
    partial: list[str] = []
    for line in lines:
        if remaining <= 0:
            break
        take = min(len(line), remaining)
        partial.append(line[:take])
        remaining -= take
    return partial


def _cursor_blink_on(global_t: float, anim_cfg: dict[str, Any]) -> bool:
    hz = max(0.1, float(anim_cfg.get("cursor_blink_hz", 2)))
    period = 1.0 / hz
    return int(global_t / (period / 2.0)) % 2 == 0


def _should_draw_summary_cursor(
    global_t: float,
    visible_char_count: int,
    total_chars: int,
    anim_cfg: dict[str, Any],
    *,
    content_start_t: float = 0.0,
) -> bool:
    if not anim_cfg.get("show_cursor") or visible_char_count <= 0:
        return False
    if visible_char_count < total_chars:
        return _cursor_blink_on(global_t, anim_cfg)
    delay = float(anim_cfg.get("start_delay_sec", 0.35))
    cps = max(0.1, float(anim_cfg.get("chars_per_second", 14)))
    hide_after = float(anim_cfg.get("cursor_hide_after_done_sec", 0.5))
    done_t = float(content_start_t) + delay + total_chars / cps
    if global_t > done_t + hide_after:
        return False
    return _cursor_blink_on(global_t, anim_cfg)


@dataclass
class SummaryLayout:
    lines: list[str]
    font: ImageFont.ImageFont
    font_size: int
    line_gap: int
    width: int
    summary_x: int
    summary_align: str
    summary_y: int
    summary_fill: tuple[int, int, int]
    footer_hi: tuple[int, int, int]
    footer_keywords: list[str]
    accent: tuple[int, int, int]

    @property
    def total_chars(self) -> int:
        return sum(len(line) for line in self.lines)


def build_summary_layout(
    *,
    draft: dict[str, Any],
    template: dict[str, Any],
    width: int,
    height: int,
) -> SummaryLayout:
    chrome = template.get("chrome") or {}
    typo = template.get("typography") or {}
    palette = template.get("palette") or {}
    footer_size = int(typo.get("footer_font_size") or 40)
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
    accent = _hex_rgb(palette.get("accent"), (61, 220, 255))
    footer_hi = _hex_rgb(typo.get("footer_highlight_color"), accent)
    summary_fill = _hex_rgb(typo.get("summary_color"), _hex_rgb(palette.get("text"), (244, 247, 250)))
    summary_y_pct = float(typo.get("summary_y_percent", DEFAULT_SUMMARY_Y_PERCENT)) / 100.0
    summary_y = _pct(summary_y_pct, height)
    footer_y_pct = float(typo.get("footer_y_percent", DEFAULT_FOOTER_Y_PERCENT)) / 100.0
    footer_y = _pct(footer_y_pct, height)
    summary_width_pct = float(typo.get("summary_width_percent") or 84) / 100.0
    summary_max_width = int(width * summary_width_pct)
    summary_font_size = int(typo.get("summary_font_size") or footer_size)
    rule_x = _pct(0.045, width)
    summary_align = str(typo.get("summary_align") or "left").strip().lower()
    if summary_align not in {"left", "center"}:
        summary_align = "left"
    if typo.get("summary_x_px") is not None:
        summary_x = int(typo.get("summary_x_px"))
    elif summary_align == "left":
        summary_x = rule_x + 18
    else:
        summary_x = (width - summary_max_width) // 2
    scratch = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(scratch)
    summary_font, footer_lines, summary_font_size = _prepare_summary_lines(
        draw,
        footer,
        max_width=summary_max_width,
        summary_y=summary_y,
        footer_y=footer_y,
        preferred_font_size=summary_font_size,
    )
    line_gap = max(6, int(round(summary_font_size * 0.28)))
    return SummaryLayout(
        lines=footer_lines,
        font=summary_font,
        font_size=summary_font_size,
        line_gap=line_gap,
        width=width,
        summary_x=summary_x,
        summary_align=summary_align,
        summary_y=summary_y,
        summary_fill=summary_fill,
        footer_hi=footer_hi,
        footer_keywords=footer_keywords,
        accent=accent,
    )


def _draw_summary_lines_block(
    draw: ImageDraw.ImageDraw,
    *,
    layout: SummaryLayout,
    visible_char_count: int | None = None,
    global_t: float = 0.0,
    anim_cfg: dict[str, Any] | None = None,
    content_start_t: float = 0.0,
) -> None:
    lines = layout.lines
    if visible_char_count is not None:
        lines = _partial_summary_lines(layout.lines, visible_char_count)
    if not lines:
        return
    fy = layout.summary_y
    last_fx = layout.summary_x
    last_line_w = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=layout.font)
        line_w = bbox[2] - bbox[0]
        if layout.summary_align == "center":
            fx = (layout.width - line_w) // 2
        else:
            fx = layout.summary_x
        last_fx = fx
        last_line_w = line_w
        _draw_highlighted_line(
            draw,
            fx,
            fy,
            line,
            layout.font,
            layout.summary_fill,
            layout.footer_hi,
            layout.footer_keywords,
        )
        fy += layout.font_size + layout.line_gap
    if (
        visible_char_count is not None
        and anim_cfg
        and _should_draw_summary_cursor(
            global_t,
            visible_char_count,
            layout.total_chars,
            anim_cfg,
            content_start_t=content_start_t,
        )
    ):
        cy = fy - layout.font_size - layout.line_gap
        cx = last_fx + last_line_w
        draw.rectangle((cx + 2, cy, cx + 4, cy + layout.font_size), fill=layout.accent)


def draw_summary_typewriter(
    frame: Image.Image,
    *,
    layout: SummaryLayout,
    visible_char_count: int,
    global_t: float,
    anim_cfg: dict[str, Any],
    content_start_t: float = 0.0,
) -> Image.Image:
    out = frame.copy()
    draw = ImageDraw.Draw(out)
    _draw_summary_lines_block(
        draw,
        layout=layout,
        visible_char_count=visible_char_count,
        global_t=global_t,
        anim_cfg=anim_cfg,
        content_start_t=content_start_t,
    )
    return out


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


def _chrome_placement(layout: dict[str, Any] | None = None) -> str:
    value = str((layout or {}).get("chrome_placement") or "header").strip().lower()
    if value == "footer":
        return "footer"
    return "header"


def _draw_brand_chrome(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    inset: int,
    brand: str,
    glyph: str,
    brand_sub: str,
    brand_font: ImageFont.ImageFont,
    brand_sub_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
    accent: tuple[int, int, int],
    accent_dim: tuple[int, int, int],
    text_color: tuple[int, int, int],
    muted: tuple[int, int, int],
    mark_y: int,
    include_brand_sub: bool,
) -> None:
    mark_box = (inset + 16, mark_y, inset + 16 + 64, mark_y + 64)
    draw.rectangle(mark_box, outline=accent, width=2)
    gb = draw.textbbox((0, 0), glyph, font=brand_font)
    gx = mark_box[0] + (64 - (gb[2] - gb[0])) // 2
    gy = mark_box[1] + (64 - (gb[3] - gb[1])) // 2 - gb[1]
    draw.text((gx, gy), glyph, font=brand_font, fill=text_color)
    brand_xy = (mark_box[2] + 16, mark_box[1] + 4)
    draw.text(brand_xy, brand, font=brand_font, fill=text_color)
    if include_brand_sub and brand_sub:
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


def chronicle_hero_at(
    anim,
    t: float,
    *,
    duration: float,
    effect: str,
    end_scale: float,
    pan: float,
    apply_motion: bool | None = None,
) -> tuple[Image.Image, float, float, float]:
    """Pick the card hero at time `t`. Animated GIFs loop and skip Ken Burns."""
    from services.ingestion.hero_animation import HeroAnimation, hero_frame_at

    if not isinstance(anim, HeroAnimation):
        raise TypeError("anim must be a HeroAnimation")
    src = hero_frame_at(anim, t)
    use_motion = (not anim.animated) if apply_motion is None else bool(apply_motion)
    if anim.animated or not use_motion:
        return src, 1.0, 0.0, 0.0
    scale, ox, oy = hero_motion_at(
        t, duration, effect, end_scale=end_scale, pan=pan
    )
    return src, scale, ox, oy


def compose_chronicle_live_frame(
    *,
    chrome: Image.Image,
    anim,
    t: float,
    inner: tuple[int, int, int, int],
    duration: float,
    effect: str,
    end_scale: float,
    pan: float,
    apply_motion: bool,
) -> Image.Image:
    frame = chrome.copy()
    inner_w = max(1, inner[2] - inner[0])
    inner_h = max(1, inner[3] - inner[1])
    hero, scale, ox, oy = chronicle_hero_at(
        anim,
        t,
        duration=duration,
        effect=effect,
        end_scale=end_scale,
        pan=pan,
        apply_motion=apply_motion,
    )
    frame.paste(
        scaled_hero(hero, inner_w, inner_h, scale, offset_x=ox, offset_y=oy),
        (inner[0], inner[1]),
    )
    return frame


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
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    cx = width / 2.0
    cy = height * 0.42
    nx = (xx - cx) / max(1.0, width * 0.58)
    ny = (yy - cy) / max(1.0, height * 0.50)
    dist = np.sqrt(nx * nx + ny * ny)

    top_tint = tuple(min(255, int(bg[i] * 0.72 + glow[i] * 0.28)) for i in range(3))
    bottom_tint = tuple(min(255, int(bg[i] * 0.88 + accent_dim[i] * 0.12)) for i in range(3))
    vertical = (yy / max(1.0, height - 1))[..., None]
    arr = np.empty((height, width, 3), dtype=np.float32)
    for i in range(3):
        arr[:, :, i] = top_tint[i] * (1.0 - vertical[:, :, 0]) + bottom_tint[i] * vertical[:, :, 0]

    bloom = np.clip(1.0 - dist * 0.95, 0.0, 1.0) ** 1.85
    for i in range(3):
        arr[:, :, i] += (glow[i] - arr[:, :, i]) * bloom * 0.48
    core = np.clip(1.0 - dist * 1.35, 0.0, 1.0) ** 2.4
    for i in range(3):
        arr[:, :, i] += (accent[i] - arr[:, :, i]) * core * 0.12

    # Soft top wash — studio light instead of flat chalkboard matte.
    top_glow = np.clip(1.0 - (yy / max(1.0, height * 0.72)), 0.0, 1.0) ** 1.6
    for i in range(3):
        arr[:, :, i] += (glow[i] - arr[:, :, i]) * top_glow * 0.10

    edge = np.clip(dist * 0.55, 0.0, 1.0) ** 1.25
    arr *= (1.0 - edge * 0.34)[..., None]

    noise = np.random.default_rng(7).normal(0.0, 1.1, (height, width, 1)).astype(np.float32)
    arr += noise
    frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    fade = np.clip(1.0 - dist * 0.72, 0.12, 1.0)

    step_x, step_y = 72, 64
    for x in range(0, width, step_x):
        alpha = int(18 + 14 * fade[height // 2, min(x, width - 1)])
        od.line((x, 0, x, height), fill=(*accent_dim, alpha), width=1)
    for y in range(0, height, step_y):
        alpha = int(16 + 12 * fade[min(y, height - 1), width // 2])
        od.line((0, y, width, y), fill=(*accent_dim, alpha), width=1)

    cxi, cyi = int(cx), int(cy)
    for scale, stroke, alpha in ((0.34, 1, 26), (0.52, 1, 20), (0.70, 1, 14)):
        rx = int(width * scale * 0.46)
        ry = int(height * scale * 0.30)
        od.ellipse((cxi - rx, cyi - ry, cxi + rx, cyi + ry), outline=(*accent, alpha), width=stroke)

    inset = int(min(width, height) * 0.028)
    corner = int(min(width, height) * 0.055)
    corner_color = (*accent, 54)
    for ox, oy, flip_x, flip_y in (
        (inset, inset, 1, 1),
        (width - inset, inset, -1, 1),
        (inset, height - inset, 1, -1),
        (width - inset, height - inset, -1, -1),
    ):
        od.line((ox, oy, ox + flip_x * corner, oy), fill=corner_color, width=2)
        od.line((ox, oy, ox, oy + flip_y * corner), fill=corner_color, width=2)

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


def _draw_main_title_background(
    draw: ImageDraw.ImageDraw,
    *,
    title_x: int,
    title_top: int,
    title_max_w: int,
    draft: dict[str, Any],
    title_font: ImageFont.ImageFont,
    bg_color: tuple[int, int, int],
    border_color: tuple[int, int, int] | None,
    pad_x: int,
    pad_y: int,
    radius: int,
) -> None:
    lines: list[tuple[str, ImageFont.ImageFont, int]] = []
    for line in _wrap_line(str(draft.get("main_line1") or ""), title_font, title_max_w, draw)[:2]:
        if line:
            lines.append((line, title_font, 8))
    if not lines:
        return

    y = title_top
    min_x = title_x
    max_x = title_x
    max_y = title_top
    for line, font, gap in lines:
        bbox = draw.textbbox((title_x, y), line, font=font)
        min_x = min(min_x, bbox[0])
        max_x = max(max_x, bbox[2])
        max_y = max(max_y, bbox[3])
        y = bbox[3] + gap

    box = (min_x - pad_x, title_top - pad_y, max_x + pad_x, max_y + pad_y)
    if radius <= 0:
        draw.rectangle(box, fill=bg_color)
    else:
        draw.rounded_rectangle(box, radius=radius, fill=bg_color)
    if border_color is not None:
        if radius <= 0:
            draw.rectangle(box, outline=border_color, width=1)
        else:
            draw.rounded_rectangle(box, radius=radius, outline=border_color, width=1)


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
    main_line1_color: tuple[int, int, int] | None = None,
    title_bg_color: tuple[int, int, int] | None = None,
    title_bg_border: tuple[int, int, int] | None = None,
    title_bg_pad_x: int = 14,
    title_bg_pad_y: int = 8,
    title_bg_radius: int = 10,
) -> int:
    if title_bg_color is not None:
        _draw_main_title_background(
            draw,
            title_x=title_x,
            title_top=title_top,
            title_max_w=title_max_w,
            draft=draft,
            title_font=title_font,
            bg_color=title_bg_color,
            border_color=title_bg_border,
            pad_x=title_bg_pad_x,
            pad_y=title_bg_pad_y,
            radius=title_bg_radius,
        )
    y = title_top
    line1_color = main_line1_color if title_bg_color is not None and main_line1_color is not None else text_color
    for line in _wrap_line(str(draft.get("main_line1") or ""), title_font, title_max_w, draw)[:2]:
        _draw_highlighted_line(
            draw, title_x, y, line, title_font, line1_color, title_hi, title_keywords
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
    summary_visible_chars: int | None = None,
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
    brand_sub = str(chrome.get("brand_sub") or "")
    layout = _layout_section(template)
    chrome_place = _chrome_placement(layout)
    brand_kwargs = dict(
        width=width,
        inset=inset,
        brand=brand,
        glyph=glyph,
        brand_sub=brand_sub,
        brand_font=brand_font,
        brand_sub_font=brand_sub_font,
        small_font=small_font,
        accent=accent,
        accent_dim=accent_dim,
        text_color=text_color,
        muted=muted,
    )
    if chrome_place != "footer":
        header_y = _pct(0.038 + _layout_top_pad(typo), height)
        _draw_brand_chrome(draw, mark_y=header_y, include_brand_sub=True, **brand_kwargs)

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
    main_line1_color = _hex_rgb(typo.get("main_line1_color"), text_color)
    title_bg_color = _hex_rgb(typo.get("title_bg_color"), (0, 0, 0)) if typo.get("title_bg_color") else None
    border_raw = typo.get("title_bg_border_color")
    title_bg_border = (
        _hex_rgb(border_raw, accent_dim) if border_raw else None
    ) if title_bg_color else None
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
        main_line1_color=main_line1_color,
        title_bg_color=title_bg_color,
        title_bg_border=title_bg_border,
        title_bg_pad_x=int(typo.get("title_bg_pad_x") or 16),
        title_bg_pad_y=int(typo.get("title_bg_pad_y") or 10),
        title_bg_radius=int(typo.get("title_bg_radius") or 12),
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
            layout = build_summary_layout(
                draft=draft,
                template=template,
                width=width,
                height=height,
            )
            _draw_summary_lines_block(
                draw,
                layout=layout,
                visible_char_count=summary_visible_chars,
            )
        if chrome_place == "footer":
            _draw_brand_chrome(draw, mark_y=footer_y, include_brand_sub=False, **brand_kwargs)
        else:
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
    asset_path = resolve_local_asset_path(image_path)
    if asset_path is None or not asset_path.is_file():
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
    out_dir = Path(output_dir) if output_dir else Config.DATA_DIR / "publish" / "covers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{article_id}_cover.jpg"
    cover.save(out_path, format="JPEG", quality=92)
    try:
        rel = path_relative_to_data(out_path.resolve())
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


def _compose_chronicle_clip_frame(
    *,
    chrome: Image.Image,
    anim,
    t: float,
    inner: tuple[int, int, int, int],
    duration: float,
    effect: str,
    end_scale: float,
    pan: float,
    apply_motion: bool,
    summary_layout: SummaryLayout | None,
    anim_cfg: dict[str, Any],
    clip_global_start: float,
    video_duration: float | None,
) -> np.ndarray:
    frame = compose_chronicle_live_frame(
        chrome=chrome,
        anim=anim,
        t=t,
        inner=inner,
        duration=duration,
        effect=effect,
        end_scale=end_scale,
        pan=pan,
        apply_motion=apply_motion,
    )
    if summary_layout is not None and anim_cfg.get("mode") == "typewriter":
        global_t = clip_global_start + t
        visible = summary_visible_chars(
            global_t,
            total_chars=summary_layout.total_chars,
            anim_cfg=anim_cfg,
            content_start_t=0.0,
            video_duration=video_duration,
        )
        frame = draw_summary_typewriter(
            frame,
            layout=summary_layout,
            visible_char_count=visible,
            global_t=global_t,
            anim_cfg=anim_cfg,
            content_start_t=0.0,
        )
    return np.asarray(frame, dtype=np.uint8)


def build_chronicle_video_clips(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    template: dict[str, Any],
    durations: list[float],
    cover_intro_sec: float = 0.0,
):
    """Build per-image MoviePy clips. Animated heroes loop inside the card."""
    from moviepy import ImageClip, VideoClip

    from services.ingestion.hero_animation import load_hero_animation

    canvas = template.get("canvas") or {}
    fps = int(canvas.get("fps") or 24)
    video_cfg = template.get("video") or {}
    anim_cfg = parse_summary_animation_config(video_cfg)
    use_typewriter = anim_cfg.get("mode") == "typewriter"
    motion = resolve_card_motion(video_cfg)
    width = int(canvas.get("width") or CANVAS_W)
    height = int(canvas.get("height") or CANVAS_H)
    video_duration = float(cover_intro_sec) + sum(float(d) for d in durations)
    summary_layout = (
        build_summary_layout(draft=draft, template=template, width=width, height=height)
        if use_typewriter
        else None
    )
    clip_starts: list[float] = []
    elapsed = float(cover_intro_sec)
    for idx, dur in enumerate(durations):
        clip_starts.append(elapsed)
        elapsed += float(dur)
    clips = []
    for index, raw_path in enumerate(image_paths):
        path = resolve_local_asset_path(raw_path)
        if path is None or not path.is_file():
            continue
        duration = float(durations[index]) if index < len(durations) else 2.5
        try:
            anim = load_hero_animation(path)
        except Exception as exc:
            logger.warning("Chronicle hero animation load failed {}: {}", path, exc)
            try:
                with Image.open(path) as src:
                    still = src.convert("RGB").copy()
                from services.ingestion.hero_animation import HeroAnimation

                anim = HeroAnimation(
                    frames=[still],
                    durations_sec=[0.1],
                    animated=False,
                )
            except Exception:
                continue
        src_rgb = anim.frames[0]
        use_live_clip = anim.animated or motion["enabled"] or use_typewriter
        chrome = render_chronicle_frame(
            draft=draft,
            image=src_rgb,
            template=template,
            include_footer=True,
            include_summary=not use_typewriter,
            include_hero=False,
        )
        clip_global_start = clip_starts[index] if index < len(clip_starts) else float(cover_intro_sec)
        if use_live_clip:
            inner = hero_inner_box(width, height, template)
            if motion["random"]:
                effect = pick_card_motion_effect(
                    motion["effects"],
                    seed=article_id,
                    index=index,
                )
            else:
                effect = motion["effects"][index % len(motion["effects"])]
            apply_motion = motion["enabled"] and not anim.animated

            def make_frame(
                t,
                _anim=anim,
                _chrome=chrome,
                _inner=inner,
                _dur=duration,
                _effect=effect,
                _end=motion["end_scale"],
                _pan=motion["pan"],
                _apply=apply_motion,
                _clip_start=clip_global_start,
            ):
                return _compose_chronicle_clip_frame(
                    chrome=_chrome,
                    anim=_anim,
                    t=t,
                    inner=_inner,
                    duration=_dur,
                    effect=_effect,
                    end_scale=_end,
                    pan=_pan,
                    apply_motion=_apply,
                    summary_layout=summary_layout,
                    anim_cfg=anim_cfg,
                    clip_global_start=_clip_start,
                    video_duration=video_duration,
                )

            clips.append(VideoClip(make_frame, duration=duration).with_fps(fps))
        else:
            still = render_chronicle_frame(
                draft=draft,
                image=src_rgb,
                template=template,
                include_footer=True,
                include_summary=not use_typewriter,
            )
            clips.append(ImageClip(np.asarray(still, dtype=np.uint8)).with_duration(duration))
    return clips


def render_chronicle_video(
    *,
    article_id: str,
    draft: dict[str, Any],
    image_paths: list[str],
    bgm_path: str,
    template: dict[str, Any],
    durations: list[float],
) -> dict[str, Any]:
    from moviepy import AudioFileClip, concatenate_videoclips

    canvas = template.get("canvas") or {}
    fps = int(canvas.get("fps") or 24)
    clips = build_chronicle_video_clips(
        article_id=article_id,
        draft=draft,
        image_paths=image_paths,
        template=template,
        durations=durations,
    )
    if not clips:
        return {"success": False, "error": "insufficient_images"}
    video = concatenate_videoclips(clips, method="compose").with_fps(fps)
    audio_file = resolve_local_asset_path(bgm_path)
    if audio_file is None:
        audio_file = Config.ROOT_DIR / str(bgm_path or "").lstrip("/").replace("\\", "/")
    if audio_file.is_file():
        from services.ingestion.cover_video_utils import fit_audio_to_duration

        audio = AudioFileClip(str(audio_file))
        video = video.with_audio(fit_audio_to_duration(audio, float(video.duration)))
    out_dir = Config.DATA_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{article_id}_chronicle.mp4"
    with use_writable_workdir("videos"):
        video.write_videofile(str(out_path), fps=fps, codec="libx264", audio_codec="aac", logger=None)
    rel = to_data_url_path(path_relative_to_data(out_path))
    return {"success": True, "video_path": rel, "duration": float(video.duration)}
