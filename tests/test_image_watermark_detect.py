"""Tests for watermark region detection helper."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from services.image_watermark_detect import detect_watermark_regions, has_likely_watermark


@pytest.fixture
def plain_image(tmp_path):
    path = tmp_path / "plain.jpg"
    img = np.full((600, 800, 3), 180, dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return path


@pytest.fixture
def corner_watermark_image(tmp_path):
    path = tmp_path / "wm.jpg"
    img = np.full((600, 800, 3), 120, dtype=np.uint8)
    # 右下角高对比文字块，模拟水印
    cv2.rectangle(img, (620, 540), (790, 585), (255, 255, 255), -1)
    cv2.putText(img, "LOGO", (630, 572), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    cv2.imwrite(str(path), img)
    return path


def test_detect_watermark_regions_empty_on_plain_image(plain_image):
    regions = detect_watermark_regions(plain_image)
    assert regions == []


def test_has_likely_watermark_false_on_plain_image(plain_image):
    assert has_likely_watermark(plain_image) is False


def test_detect_watermark_regions_finds_corner_logo(corner_watermark_image):
    regions = detect_watermark_regions(corner_watermark_image)
    assert len(regions) >= 1


def test_has_likely_watermark_true_on_corner_logo(corner_watermark_image):
    assert has_likely_watermark(corner_watermark_image) is True


def test_detect_watermark_regions_missing_file():
    assert detect_watermark_regions(Path("no_such_file.jpg")) == []
