"""Shared types for audience comment reply."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InboundComment:
    platform_post_id: str
    platform_comment_id: str
    author_name: str
    content: str
    commented_at: datetime | None
    post_title: str | None = None
    author_username: str | None = None
    already_replied_by_author: bool = False


@dataclass(frozen=True)
class PostCommentSession:
    platform_post_id: str
    post_title: str | None
    hub_feed_text: str | None
    feed_match_spec: dict[str, list[str]] | None
    feed_active: bool
    post_context_json: str | None = None


@dataclass
class ScanRunSummary:
    account_id: str
    platform: str
    posts_scanned: int = 0
    comments_seen: int = 0
    new_pending: int = 0
    auto_sent: int = 0
    skipped: int = 0
    errors: int = 0
    retried: int = 0
    already_replied: int = 0
    activation_failures: int = 0


@dataclass
class CommentReplyRunResult:
    id: str
    status: str
    mode: str
    accounts_total: int
    posts_scanned: int
    comments_seen: int
    new_pending: int
    auto_sent: int
    skipped: int
    failed: int
    retried: int
    error_summary: str | None
    started_at: datetime
    finished_at: datetime | None
