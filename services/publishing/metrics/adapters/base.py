"""Metrics adapter base types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class PostMetricsItem:
    platform_post_id: str
    title: str = ""
    published_at: datetime | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    favorite_count: int | None = None
    follow_count: int | None = None
    play_3s_rate: float | None = None
    completion_rate: float | None = None
    avg_watch_sec: float | None = None
    profile_click_count: int | None = None
    post_url: str | None = None
    raw: dict = field(default_factory=dict)


class MetricsAdapter:
    platform_id: str

    def fetch_recent_post_metrics(
        self,
        session_path: Path,
        *,
        since_days: int = 90,
        limit: int = 100,
        needed_post_ids: set[str] | None = None,
    ) -> list[PostMetricsItem]:
        raise NotImplementedError

    def fetch_post_metrics(
        self,
        session_path: Path,
        *,
        platform_post_id: str | None = None,
        post_url: str | None = None,
    ) -> PostMetricsItem | None:
        """Optional single-post refresh. Default skips a second browser session.

        List sync already paginates with `needed_post_ids`. Re-scraping the same
        creator list per unmatched job launches many browsers and can abort
        before snapshots are written.
        """
        del session_path, platform_post_id, post_url
        return None
