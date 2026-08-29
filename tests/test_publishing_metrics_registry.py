"""Tests for metrics adapter registry."""
from services.publishing.metrics.registry import get_metrics_adapter


def test_all_publish_platforms_have_metrics_adapter():
    for platform in ("xiaohongshu", "douyin", "kuaishou", "wechat_channels"):
        assert get_metrics_adapter(platform) is not None
