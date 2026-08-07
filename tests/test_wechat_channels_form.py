"""Tests for WeChat Channels form helpers."""
from __future__ import annotations

from services.publishing.adapters.wechat_channels_form import DESCRIPTION_PLACEHOLDERS


def test_description_placeholders_cover_common_labels():
    assert "说点什么" in DESCRIPTION_PLACEHOLDERS
    assert "描述" in DESCRIPTION_PLACEHOLDERS
