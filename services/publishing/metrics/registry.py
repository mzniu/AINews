"""Metrics adapter registry."""
from __future__ import annotations

from pathlib import Path

from services.publishing.metrics.adapters.base import MetricsAdapter, PostMetricsItem
from services.publishing.metrics.adapters.douyin import DouyinMetricsAdapter
from services.publishing.metrics.adapters.kuaishou import KuaishouMetricsAdapter
from services.publishing.metrics.adapters.wechat_channels import WechatChannelsMetricsAdapter
from services.publishing.metrics.adapters.xiaohongshu import XiaohongshuMetricsAdapter

_METRICS_ADAPTERS: dict[str, MetricsAdapter] = {
    "xiaohongshu": XiaohongshuMetricsAdapter(),
    "douyin": DouyinMetricsAdapter(),
    "kuaishou": KuaishouMetricsAdapter(),
    "wechat_channels": WechatChannelsMetricsAdapter(),
}


def get_metrics_adapter(platform: str) -> MetricsAdapter | None:
    return _METRICS_ADAPTERS.get(platform)


def fetch_platform_metrics_items(
    platform: str,
    session_path: Path,
    *,
    since_days: int = 90,
    limit: int = 100,
    needed_post_ids: set[str] | None = None,
) -> list[PostMetricsItem]:
    adapter = get_metrics_adapter(platform)
    if adapter is None:
        return []
    return adapter.fetch_recent_post_metrics(
        session_path,
        since_days=since_days,
        limit=limit,
        needed_post_ids=needed_post_ids,
    )


def fetch_platform_post_metrics(
    platform: str,
    session_path: Path,
    *,
    platform_post_id: str | None = None,
    post_url: str | None = None,
) -> PostMetricsItem | None:
    adapter = get_metrics_adapter(platform)
    if adapter is None:
        return None
    return adapter.fetch_post_metrics(
        session_path,
        platform_post_id=platform_post_id,
        post_url=post_url,
    )
