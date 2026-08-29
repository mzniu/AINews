"""CSV export for published post metrics."""
from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from services.publishing.metrics.query import list_published_posts

CSV_HEADERS = (
    "标题",
    "平台",
    "账号",
    "发布时间",
    "平台作品ID",
    "作品链接",
    "匹配状态",
    "播放量",
    "点赞",
    "评论",
    "分享",
    "收藏",
    "关注",
    "3秒播放率",
    "完播率",
    "平均观看秒",
    "点头像",
    "快照日期",
)


def build_published_posts_csv(
    session: Session,
    *,
    platform: str | None = None,
    account_id: str | None = None,
    days: int | None = 30,
) -> str:
    posts, _ = list_published_posts(
        session,
        platform=platform,
        account_id=account_id,
        days=days,
        limit=500,
        offset=0,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADERS)
    for post in posts:
        metrics = post.get("metrics") or {}
        writer.writerow(
            [
                post.get("title") or "",
                post.get("platform_display_name") or post.get("platform") or "",
                post.get("account_nickname") or "",
                post.get("published_at") or "",
                post.get("platform_post_id") or "",
                post.get("platform_post_url") or "",
                post.get("metrics_match_status") or "",
                metrics.get("view_count") if metrics.get("view_count") is not None else "",
                metrics.get("like_count") if metrics.get("like_count") is not None else "",
                metrics.get("comment_count") if metrics.get("comment_count") is not None else "",
                metrics.get("share_count") if metrics.get("share_count") is not None else "",
                metrics.get("favorite_count") if metrics.get("favorite_count") is not None else "",
                metrics.get("follow_count") if metrics.get("follow_count") is not None else "",
                metrics.get("play_3s_rate") if metrics.get("play_3s_rate") is not None else "",
                metrics.get("completion_rate") if metrics.get("completion_rate") is not None else "",
                metrics.get("avg_watch_sec") if metrics.get("avg_watch_sec") is not None else "",
                metrics.get("profile_click_count") if metrics.get("profile_click_count") is not None else "",
                metrics.get("snapshot_date") or "",
            ]
        )
    return buffer.getvalue()
