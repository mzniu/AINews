"""Tests for cover intro video utilities."""
from __future__ import annotations

from PIL import Image

from services.ingestion.cover_video_utils import letterbox_image_on_canvas


def test_letterbox_image_on_canvas_centers_image():
    image = Image.new("RGB", (400, 300), color=(255, 0, 0))
    canvas = letterbox_image_on_canvas(image, 200, 400)
    assert canvas.size == (200, 400)
    center = canvas.getpixel((100, 200))
    assert center == (255, 0, 0)
