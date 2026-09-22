"""Classic overlay subtitle bar colors from the render template (TDD)."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFont

from utils.video_utils import _render_frame_animated


def _sample_frame(*, bar_color: str, text_color: str):
    bg = Image.new("RGB", (240, 400), (0, 0, 0))
    user = Image.new("RGBA", (40, 40), (20, 20, 20, 255))
    font = ImageFont.load_default()
    title_info = (font, font, ["TITLE"], ["HOOK LINE"], 30, 16, 20, 200)
    return _render_frame_animated(
        bg,
        user,
        20,
        220,
        40,
        40,
        240,
        400,
        title_info,
        None,
        t=2.0,
        entrance_duration=0.1,
        title_slide_entrance=False,
        subtitle_bar_color=bar_color,
        subtitle_text_color=text_color,
    )


def test_subtitle_bar_keeps_yellow_by_default():
    frame = _sample_frame(bar_color="#FFEB3B", text_color="#000000")
    arr = np.asarray(frame)
    yellow = (
        (arr[:, :, 0] > 200) & (arr[:, :, 1] > 180) & (arr[:, :, 2] < 120)
    ).sum()
    assert yellow > 50


def test_subtitle_bar_uses_override_colors():
    frame = _sample_frame(bar_color="#6B4DFF", text_color="#FFFFFF")
    arr = np.asarray(frame)
    yellow = (
        (arr[:, :, 0] > 200) & (arr[:, :, 1] > 180) & (arr[:, :, 2] < 120)
    ).sum()
    purple = (
        (arr[:, :, 0] > 80)
        & (arr[:, :, 0] < 140)
        & (arr[:, :, 1] < 120)
        & (arr[:, :, 2] > 200)
    ).sum()
    assert yellow == 0
    assert purple > 50
