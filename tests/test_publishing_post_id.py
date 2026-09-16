"""Tests for publish post ID helpers."""
from services.publishing.metrics.post_id import (
    build_platform_post_url,
    build_xiaohongshu_post_url,
    extract_platform_post_id,
    extract_xiaohongshu_note_id,
    is_synthetic_platform_post_id,
)


def test_is_synthetic_platform_post_id():
    assert is_synthetic_platform_post_id("xhs_1739000000")
    assert is_synthetic_platform_post_id("dy_123")
    assert is_synthetic_platform_post_id("dy_manual_1786029979")
    assert not is_synthetic_platform_post_id("67890abcdef")
    assert is_synthetic_platform_post_id(None)
    assert is_synthetic_platform_post_id("")


def test_extract_xiaohongshu_note_id_from_success_url():
    url = "https://creator.xiaohongshu.com/publish/success?noteId=67890abc&source=official"
    assert extract_xiaohongshu_note_id(url) == "67890abc"


def test_extract_xiaohongshu_note_id_from_explore_url():
    url = "https://www.xiaohongshu.com/explore/67890abc"
    assert extract_xiaohongshu_note_id(url) == "67890abc"


def test_build_xiaohongshu_post_url():
    assert build_xiaohongshu_post_url("abc123") == "https://www.xiaohongshu.com/explore/abc123"


def test_extract_platform_post_id_douyin():
    url = "https://www.douyin.com/video/7123456789012345678"
    assert extract_platform_post_id("douyin", url) == "7123456789012345678"
    assert build_platform_post_url("douyin", "123").endswith("/video/123")
