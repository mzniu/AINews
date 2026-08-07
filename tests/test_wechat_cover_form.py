"""Tests for WeChat Channels form helpers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from services.publishing.adapters.wechat_channels_form import fill_wechat_cover


def test_fill_wechat_cover_uploads_via_image_input(tmp_path):
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"fake")

    page = MagicMock()
    locator = MagicMock()
    locator.count.return_value = 1
    candidate = MagicMock()
    candidate.get_attribute.return_value = "image/jpeg"
    locator.nth.return_value = candidate
    page.locator.return_value = locator
    page.get_by_text.side_effect = Exception("no trigger")

    ok = fill_wechat_cover(page, cover, timeout_ms=3000)

    assert ok is True
    candidate.set_input_files.assert_called_once()
