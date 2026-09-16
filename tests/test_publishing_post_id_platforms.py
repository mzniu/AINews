"""Tests for platform post ID helpers (all platforms)."""
from services.publishing.metrics.post_id import (
    build_douyin_post_url,
    build_kuaishou_post_url,
    build_platform_post_url,
    extract_douyin_aweme_id,
    extract_kuaishou_photo_id,
    extract_wechat_export_id,
)


def test_extract_douyin_aweme_id():
    assert extract_douyin_aweme_id("https://www.douyin.com/video/7123456789012345678") == "7123456789012345678"
    assert extract_douyin_aweme_id("https://creator.douyin.com/creator-micro/content/manage?aweme_id=99") == "99"


def test_extract_kuaishou_photo_id():
    assert extract_kuaishou_photo_id("https://www.kuaishou.com/short-video/3xabc") == "3xabc"
    assert extract_kuaishou_photo_id("https://cp.kuaishou.com/article/publish/video?photoId=3xabc") == "3xabc"


def test_extract_wechat_export_id():
    assert extract_wechat_export_id("https://channels.weixin.qq.com/platform/post/list?export_id=exp1") == "exp1"
    assert extract_wechat_export_id("https://channels.weixin.qq.com/platform/post/detail?objectId=obj9") == "obj9"


def test_build_platform_post_url():
    assert "douyin.com/video/123" in build_platform_post_url("douyin", "123")
    assert build_platform_post_url("wechat_channels", "exp1") is None
