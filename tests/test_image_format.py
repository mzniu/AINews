"""Tests for image format sniffing and GIF content detection."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.gif_processor import gif_processor
from utils.image_format import resolve_image_ext, sniff_image_ext

GIF_HEADER = b"GIF89a" + b"\x00" * 6
WEBP_HEADER = b"RIFF\x00\x00\x00\x00WEBP"


class TestImageFormat(unittest.TestCase):
    def test_sniff_gif_header(self):
        self.assertEqual(sniff_image_ext(GIF_HEADER), ".gif")

    def test_resolve_ext_prefers_magic_over_wrong_url(self):
        ext = resolve_image_ext(
            GIF_HEADER,
            content_type="image/jpeg",
            url="https://cdn.example.com/news/0",
        )
        self.assertEqual(ext, ".gif")

    def test_gif_processor_detects_gif_saved_as_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image_001.jpg"
            path.write_bytes(GIF_HEADER + b"\x00" * 64)
            self.assertTrue(gif_processor.is_gif_file(str(path)))
            self.assertTrue(gif_processor.is_animation_raster(str(path)))
            self.assertTrue(gif_processor.is_convertible_to_mp4_animation(str(path)))

    def test_gif_processor_webp_by_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.jpg"
            path.write_bytes(WEBP_HEADER + b"\x00" * 64)
            self.assertTrue(gif_processor.is_webp_file(str(path)))
            self.assertTrue(gif_processor.is_convertible_to_mp4_animation(str(path)))


if __name__ == "__main__":
    unittest.main()
