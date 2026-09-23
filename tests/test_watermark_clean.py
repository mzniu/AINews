from pathlib import Path

from PIL import Image

from services.ingestion.watermark_clean import (
    clean_images_for_render,
    encoded_size,
    project_regions,
)
from src.utils.paths import to_data_url_path


def test_encoded_size_shrinks_long_edge():
    assert encoded_size(2560, 1440) == (1280, 720)


def test_normalized_box_maps_to_source_pixels():
    regions = project_regions(
        {
            "has_watermark": True,
            "regions": [
                {"x": 0.75, "y": 0.90, "width": 0.20, "height": 0.08, "kind": "logo"}
            ],
        },
        src_w=2560,
        src_h=1440,
    )
    assert len(regions) == 1
    box = regions[0]
    assert box.kind == "logo"
    assert 1900 <= box.x <= 1950
    assert 1280 <= box.y <= 1320
    assert 480 <= box.width <= 540
    assert 100 <= box.height <= 130


def test_encoded_pixel_box_maps_back_on_large_source():
    regions = project_regions(
        {
            "has_watermark": True,
            "regions": [{"x": 960, "y": 648, "width": 256, "height": 58, "kind": "logo"}],
        },
        src_w=2560,
        src_h=1440,
    )
    assert len(regions) == 1
    box = regions[0]
    assert box.x == 1920
    assert box.y == 1296
    assert box.width == 512
    assert box.height == 116


def test_oversized_box_is_dropped():
    regions = project_regions(
        {
            "has_watermark": True,
            "regions": [{"x": 0.0, "y": 0.0, "width": 0.9, "height": 0.9}],
        },
        src_w=800,
        src_h=600,
    )
    assert regions == ()


def test_mixed_units_are_dropped():
    regions = project_regions(
        {
            "has_watermark": True,
            "regions": [{"x": 10, "y": 0.1, "width": 0.2, "height": 40}],
        },
        src_w=800,
        src_h=600,
    )
    assert regions == ()


class _Vision:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def model_id(self):
        return "vision-test"

    def detect(self, image_path: Path):
        self.calls += 1
        return self.payload


class _Inpaint:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def inpaint(self, image_path, regions, output_path):
        self.calls += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.open(image_path).save(output_path)
        return output_path


def _jpg(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 200), (80, 80, 80)).save(path)
    return path


def test_disabled_skips_without_io(tmp_path):
    src = _jpg(tmp_path / "a.jpg")
    vision = _Vision({"has_watermark": True, "regions": []})
    result = clean_images_for_render([str(src)], enabled=False, vision=vision)
    key = to_data_url_path(src)
    assert result[key].status == "skipped"
    assert result[key].reason == "disabled"
    assert vision.calls == 0


def test_gif_is_not_static(tmp_path):
    gif = tmp_path / "a.gif"
    Image.new("RGB", (40, 40), (1, 2, 3)).save(gif)
    result = clean_images_for_render(
        [str(gif)],
        vision=_Vision(
            {
                "has_watermark": True,
                "regions": [{"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}],
            }
        ),
        inpaint=_Inpaint(),
    )
    key = to_data_url_path(gif)
    assert result[key].status == "skipped"
    assert result[key].reason == "not_static"


def test_cleans_and_keeps_original(tmp_path):
    src = _jpg(tmp_path / "shot.jpg")
    before = src.read_bytes()
    inpaint = _Inpaint()
    result = clean_images_for_render(
        [str(src), str(src).replace("\\", "/")],
        vision=_Vision(
            {
                "has_watermark": True,
                "regions": [{"x": 0.7, "y": 0.8, "width": 0.2, "height": 0.1, "kind": "logo"}],
            }
        ),
        inpaint=inpaint,
    )
    key = to_data_url_path(src)
    assert len(result) == 1
    assert result[key].status == "cleaned"
    assert result[key].cleaned_path
    assert src.read_bytes() == before
    assert inpaint.calls == 1


def test_fingerprint_reuse_then_refresh(tmp_path):
    src = _jpg(tmp_path / "shot.jpg")
    vision = _Vision(
        {
            "has_watermark": True,
            "regions": [{"x": 0.7, "y": 0.8, "width": 0.2, "height": 0.1}],
        }
    )
    inpaint = _Inpaint()
    first = clean_images_for_render([str(src)], vision=vision, inpaint=inpaint)
    assert inpaint.calls == 1
    second = clean_images_for_render([str(src)], vision=vision, inpaint=inpaint)
    assert inpaint.calls == 1
    assert first[to_data_url_path(src)].path == second[to_data_url_path(src)].path
    vision.payload = {
        "has_watermark": True,
        "regions": [{"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}],
    }
    clean_images_for_render([str(src)], vision=vision, inpaint=inpaint)
    assert inpaint.calls == 2


def test_missing_vision_skips(tmp_path, monkeypatch):
    src = _jpg(tmp_path / "a.jpg")
    monkeypatch.setattr(
        "services.model_config.registry.get_vision_client",
        lambda: (None, None),
    )
    result = clean_images_for_render([str(src)])
    assert result[to_data_url_path(src)].reason == "vision_unavailable"
