"""Lightweight watermark region detection (shared by API and image scoring)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


def merge_regions(regions: list[dict[str, int]]) -> list[dict[str, int]]:
    """合并重叠的水印区域。"""
    if not regions:
        return []

    merged = [region.copy() for region in regions]
    i = 0
    while i < len(merged):
        j = i + 1
        while j < len(merged):
            r1, r2 = merged[i], merged[j]
            if (
                r1["x"] < r2["x"] + r2["width"]
                and r1["x"] + r1["width"] > r2["x"]
                and r1["y"] < r2["y"] + r2["height"]
                and r1["y"] + r1["height"] > r2["y"]
            ):
                x1 = min(r1["x"], r2["x"])
                y1 = min(r1["y"], r2["y"])
                x2 = max(r1["x"] + r1["width"], r2["x"] + r2["width"])
                y2 = max(r1["y"] + r1["height"], r2["y"] + r2["height"])
                merged[i] = {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
                merged.pop(j)
                j = i + 1
            else:
                j += 1
        i += 1
    return merged


def detect_watermark_regions(image_path: Path | str) -> list[dict[str, int]]:
    """检测图片中可能的水印区域，失败时返回空列表。"""
    path = Path(image_path)
    if not path.exists():
        return []

    try:
        import cv2
    except ImportError:
        logger.warning("opencv 未安装，跳过水印检测")
        return []

    img = cv2.imread(str(path))
    if img is None:
        return []

    h, w = img.shape[:2]
    regions: list[dict[str, int]] = []

    corner_regions = [
        (int(w * 0.65), int(h * 0.90), int(w * 0.35), int(h * 0.10)),
        (0, int(h * 0.90), int(w * 0.35), int(h * 0.10)),
        (int(w * 0.65), 0, int(w * 0.35), int(h * 0.08)),
        (0, 0, int(w * 0.35), int(h * 0.08)),
    ]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    for rx, ry, rw, rh in corner_regions:
        roi = gray[ry : ry + rh, rx : rx + rw]
        if roi.size == 0:
            continue

        edges = cv2.Canny(roi, 50, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
        dilated = cv2.dilate(edges, kernel, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch
            roi_area = rw * rh
            if area < roi_area * 0.01 or area > roi_area * 0.9:
                continue
            if cw < 20 or ch < 8:
                continue

            pad = 8
            abs_x = max(0, rx + cx - pad)
            abs_y = max(0, ry + cy - pad)
            abs_w = min(w - abs_x, cw + pad * 2)
            abs_h = min(h - abs_y, ch + pad * 2)
            regions.append({"x": abs_x, "y": abs_y, "width": abs_w, "height": abs_h})

    regions = merge_regions(regions)

    if not regions:
        _, bright = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
        kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 10))
        bright_dilated = cv2.dilate(bright, kernel2, iterations=2)
        contours2, _ = cv2.findContours(bright_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours2:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            if area > 500 and bw > 30 and bh > 15:
                regions.append({"x": x, "y": y, "width": bw, "height": bh})

    return regions


def has_likely_watermark(
    image_path: Path | str,
    *,
    min_regions: int = 1,
) -> bool:
    return len(detect_watermark_regions(image_path)) >= min_regions
