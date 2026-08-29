"""GIF / animated WebP frame timing for chronicle card heroes."""
from __future__ import annotations

from pathlib import Path

from PIL import Image


def _two_frame_gif(path: Path, *, duration_ms: int = 100) -> Path:
    red = Image.new("RGB", (64, 64), (220, 20, 20))
    blue = Image.new("RGB", (64, 64), (20, 40, 220))
    red.save(
        path,
        save_all=True,
        append_images=[blue],
        duration=duration_ms,
        loop=0,
        format="GIF",
    )
    return path


def test_load_hero_animation_marks_gif_animated(tmp_path):
    from services.ingestion.hero_animation import load_hero_animation

    anim = load_hero_animation(_two_frame_gif(tmp_path / "loop.gif"))
    assert anim.animated is True
    assert len(anim.frames) == 2
    assert anim.frames[0].getpixel((8, 8))[0] > 180
    assert anim.frames[1].getpixel((8, 8))[2] > 180


def test_hero_frame_at_switches_and_loops(tmp_path):
    from services.ingestion.hero_animation import hero_frame_at, load_hero_animation

    anim = load_hero_animation(_two_frame_gif(tmp_path / "loop.gif", duration_ms=100))
    first = hero_frame_at(anim, 0.0).getpixel((8, 8))
    second = hero_frame_at(anim, 0.08).getpixel((8, 8))
    looped = hero_frame_at(anim, 0.14).getpixel((8, 8))
    assert first != second
    assert looped == first


def test_hero_frame_at_plays_faster_than_source(tmp_path):
    from services.ingestion.hero_animation import hero_frame_at, load_hero_animation

    anim = load_hero_animation(_two_frame_gif(tmp_path / "loop.gif", duration_ms=100))
    first = hero_frame_at(anim, 0.0).getpixel((8, 8))
    # Native 100ms frames: 80ms is still frame 1. At 1.5x it must already be frame 2.
    assert hero_frame_at(anim, 0.08).getpixel((8, 8)) != first
    # Native cycle is 200ms; at 1.5x it loops by 140ms.
    assert hero_frame_at(anim, 0.14).getpixel((8, 8)) == first


def test_jpeg_hero_is_not_animated(tmp_path):
    from services.ingestion.hero_animation import hero_frame_at, load_hero_animation

    path = tmp_path / "still.jpg"
    Image.new("RGB", (32, 32), (10, 180, 10)).save(path)
    anim = load_hero_animation(path)
    assert anim.animated is False
    assert len(anim.frames) == 1
    assert hero_frame_at(anim, 0.0).getpixel((4, 4)) == hero_frame_at(anim, 1.5).getpixel((4, 4))


def test_single_frame_gif_is_not_animated(tmp_path):
    from services.ingestion.hero_animation import load_hero_animation

    path = tmp_path / "one.gif"
    Image.new("RGB", (24, 24), (200, 30, 30)).save(path, format="GIF")
    anim = load_hero_animation(path)
    assert anim.animated is False
    assert len(anim.frames) == 1
