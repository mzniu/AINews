"""Tests for Xiaohongshu metrics row parsing."""
from datetime import datetime

from services.publishing.metrics.adapters.common import parse_count_text
from services.publishing.metrics.adapters.xiaohongshu import build_xiaohongshu_metrics_items_from_rows


def test_parse_count_text():
    assert parse_count_text("1.2万") == 12000
    assert parse_count_text("999") == 999
    assert parse_count_text("") is None
    assert parse_count_text("—") is None


def test_build_xiaohongshu_metrics_items_from_rows():
    rows = [
        {
            "note_id": "abc123",
            "title": "AI 新闻",
            "published_at": "2026-08-10T12:00:00",
            "read_count": "1.2万",
            "like_count": "45",
            "comment_count": "3",
            "favorite_count": "12",
        }
    ]
    items = build_xiaohongshu_metrics_items_from_rows(rows)
    assert len(items) == 1
    item = items[0]
    assert item.platform_post_id == "abc123"
    assert item.title == "AI 新闻"
    assert item.view_count == 12000
    assert item.like_count == 45
    assert item.comment_count == 3
    assert item.favorite_count == 12
    assert item.published_at == datetime(2026, 8, 10, 12, 0, 0)
    assert "xiaohongshu.com/explore/abc123" in (item.post_url or "")
