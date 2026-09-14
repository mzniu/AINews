from pathlib import Path

from PIL import Image

from services.ingestion.render_image_utils import (
    filter_renderable_image_dicts,
    is_renderable_local_image,
)
from services.ingestion.video_render_service import ensure_min_total_duration


def test_is_renderable_local_image_rejects_tiny_and_corrupt(tmp_path):
    tiny = tmp_path / "tiny.webp"
    Image.new("RGB", (32, 32), color=(10, 10, 10)).save(tiny)
    assert is_renderable_local_image(tiny) is False

    good = tmp_path / "good.jpg"
    Image.new("RGB", (800, 600), color=(20, 20, 20)).save(good)
    assert is_renderable_local_image(good) is True

    corrupt = tmp_path / "bad.jpg"
    corrupt.write_bytes(b"not-an-image")
    assert is_renderable_local_image(corrupt) is False


def test_filter_renderable_image_dicts(tmp_path):
    good = tmp_path / "good.jpg"
    Image.new("RGB", (640, 480), color=(30, 30, 30)).save(good)
    images = [
        {"local_path": str(good), "url": "https://cdn.example.com/good.jpg"},
        {"local_path": str(tmp_path / "missing.jpg"), "url": "https://cdn.example.com/missing.jpg"},
    ]
    kept = filter_renderable_image_dicts(images)
    assert len(kept) == 1
    assert kept[0]["url"].endswith("good.jpg")


def test_ensure_min_total_duration_scales_up():
    assert ensure_min_total_duration([2.5, 3.0], min_total=8.0) == [3.636, 4.364]
    assert ensure_min_total_duration([7.0], min_total=8.0) == [8.0]
    assert ensure_min_total_duration([3.0, 3.0, 3.0], min_total=8.0) == [3.0, 3.0, 3.0]
