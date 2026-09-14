"""Platform dispatch for audience comment reply."""
from __future__ import annotations

from typing import Any, Callable

from playwright.sync_api import Page

from services.publishing.adapters.base import CommentResult
from services.publishing.adapters.douyin_audience_reply import (
    reply_douyin_audience_comment,
    scan_douyin_account_comments,
)
from services.publishing.adapters.kuaishou_audience_reply import (
    reply_kuaishou_audience_comment,
    scan_kuaishou_account_comments,
)
from services.publishing.adapters.wechat_channels_audience_reply import (
    reply_wechat_audience_comment,
    scan_wechat_account_comments,
)
from services.publishing.comment_reply.types import InboundComment

SUPPORTED_PLATFORMS = frozenset({"wechat_channels", "kuaishou", "douyin"})


def post_id_from_row(platform: str, post_row: dict[str, Any]) -> str:
    if platform == "wechat_channels":
        return str(post_row.get("export_id") or "").strip()
    if platform == "kuaishou":
        return str(post_row.get("photo_id") or post_row.get("work_id") or "").strip()
    if platform == "douyin":
        return str(post_row.get("video_id") or post_row.get("work_id") or "").strip()
    return ""


def scan_account_comments(
    platform: str,
    page: Page,
    *,
    account_nickname: str | None,
    max_posts: int,
    match_spec_resolver: Callable[[dict[str, Any]], dict[str, list[str]] | None] | None = None,
) -> list[tuple[dict[str, Any], list[InboundComment]]]:
    if platform == "wechat_channels":
        return scan_wechat_account_comments(
            page,
            account_nickname=account_nickname,
            max_posts=max_posts,
            match_spec_resolver=match_spec_resolver,
        )
    if platform == "kuaishou":
        return scan_kuaishou_account_comments(
            page,
            account_nickname=account_nickname,
            max_posts=max_posts,
        )
    if platform == "douyin":
        return scan_douyin_account_comments(
            page,
            account_nickname=account_nickname,
            max_posts=max_posts,
        )
    raise ValueError(f"unsupported_platform:{platform}")


def reply_audience_comment(
    platform: str,
    page: Page,
    *,
    platform_post_id: str,
    post_title: str,
    platform_comment_id: str,
    comment_content: str,
    reply_text: str,
    post_description: str | None = None,
    main_line1: str | None = None,
    main_line2: str | None = None,
    sub_title: str | None = None,
    sub_title2: str | None = None,
    feed_match_spec: dict[str, list[str]] | None = None,
    account_nickname: str | None = None,
) -> CommentResult:
    if platform == "wechat_channels":
        return reply_wechat_audience_comment(
            page,
            export_id=platform_post_id,
            post_title=post_title,
            platform_comment_id=platform_comment_id,
            comment_content=comment_content,
            reply_text=reply_text,
            post_description=post_description,
            main_line1=main_line1,
            main_line2=main_line2,
            sub_title=sub_title,
            sub_title2=sub_title2,
            feed_match_spec=feed_match_spec,
        )
    if platform == "kuaishou":
        return reply_kuaishou_audience_comment(
            page,
            photo_id=platform_post_id,
            post_title=post_title,
            platform_comment_id=platform_comment_id,
            comment_content=comment_content,
            reply_text=reply_text,
        )
    if platform == "douyin":
        return reply_douyin_audience_comment(
            page,
            video_id=platform_post_id,
            post_title=post_title,
            platform_comment_id=platform_comment_id,
            comment_content=comment_content,
            reply_text=reply_text,
            account_nickname=account_nickname,
        )
    raise ValueError(f"unsupported_platform:{platform}")
