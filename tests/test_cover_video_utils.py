"""Tests for cover intro video utilities."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from services.ingestion.cover_video_utils import (
    fit_audio_to_duration,
    fit_rgba_within_box,
    letterbox_image_on_canvas,
    shift_audio_for_cover_intro,
)


def test_fit_rgba_within_box_limits_long_edge():
    wide = Image.new("RGBA", (400, 100), color=(255, 0, 0, 255))
    fitted = fit_rgba_within_box(wide, 200, 200)
    assert fitted.size == (200, 50)
    tall = Image.new("RGBA", (100, 400), color=(0, 255, 0, 255))
    fitted_tall = fit_rgba_within_box(tall, 200, 200)
    assert fitted_tall.size == (50, 200)


def test_letterbox_image_on_canvas_centers_image():
    image = Image.new("RGB", (400, 300), color=(255, 0, 0))
    canvas = letterbox_image_on_canvas(image, 200, 400)
    assert canvas.size == (200, 400)
    center = canvas.getpixel((100, 200))
    assert center == (255, 0, 0)


def test_shift_audio_for_cover_intro_keeps_music_until_end():
    from moviepy import AudioClip

    def make_frame(t):
        t = np.atleast_1d(t).astype(float)
        ones = np.ones((t.shape[0], 2), dtype=float) * 0.4
        if np.isscalar(t) or t.shape == ():
            return ones[0]
        return ones

    tone = AudioClip(make_frame, duration=2.0, fps=44100)
    shifted = shift_audio_for_cover_intro(tone, 1.0)
    assert abs(float(shifted.duration) - 3.0) < 0.02
    assert float(np.mean(np.abs(np.atleast_1d(shifted.get_frame(0.2))))) > 0.2
    assert float(np.mean(np.abs(np.atleast_1d(shifted.get_frame(2.8))))) > 0.2


def test_fit_audio_to_duration_covers_requested_length():
    from moviepy import AudioClip

    def make_frame(t):
        t = np.atleast_1d(t).astype(float)
        return np.column_stack([np.full_like(t, 0.4), np.full_like(t, 0.4)])

    tone = AudioClip(make_frame, duration=1.0, fps=44100)
    fitted = fit_audio_to_duration(tone, 2.5)
    assert abs(float(fitted.duration) - 2.5) < 0.02
    assert float(np.mean(np.abs(np.atleast_1d(fitted.get_frame(2.4))))) > 0.2


def test_prepend_cover_intro_keeps_bgm_on_last_second(tmp_path, monkeypatch):
    from moviepy import VideoFileClip

    from services.ingestion.cover_video_utils import prepend_cover_intro_to_video

    src = Path("data/videos/animated_20260813_190638.mp4")
    cover_src = Path("data/publish/covers/18c6f3878ab4435db586da369b8c41f1_cover.jpg")
    if not src.is_file() or not cover_src.is_file():
        pytest.skip("sample rendered video/cover not available")

    monkeypatch.setattr("services.ingestion.cover_video_utils.Config.ROOT_DIR", tmp_path)
    video_path = tmp_path / "data" / "videos" / "body.mp4"
    cover_path = tmp_path / "data" / "publish" / "covers" / "cover.jpg"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(src.read_bytes())
    cover_path.write_bytes(cover_src.read_bytes())

    result = prepend_cover_intro_to_video(
        video_path=str(video_path.relative_to(tmp_path)).replace("\\", "/"),
        cover_path=str(cover_path.relative_to(tmp_path)).replace("\\", "/"),
        intro_duration=1.0,
    )
    assert result["success"] is True

    out = VideoFileClip(str(video_path))
    try:
        duration = float(out.duration)
        assert duration >= 8.8
        tail = np.vstack(
            [
                np.atleast_1d(out.audio.get_frame(t))
                for t in np.linspace(duration - 0.8, duration - 0.15, num=8)
            ]
        )
        assert float(np.sqrt(np.mean(np.square(tail)))) > 0.01
    finally:
        out.close()

