"""Helpers for inline comment-reply batch processing."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from services.publishing.comment_reply.generation import generate_comment_reply, validate_reply_text
from services.publishing.comment_reply.types import InboundComment

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.db.models.publishing import CommentInbox


def merge_post_backlog(
    session: Session,
    *,
    account: Any,
    post_id: str,
    api_comments: list[InboundComment],
    lookback: datetime | None,
) -> list[InboundComment]:
    """Merge platform API comments with inbox backlog not returned by the API."""
    from src.db.models.publishing import CommentInbox

    merged = list(api_comments)
    seen = {comment.platform_comment_id for comment in merged}
    backlog_rows = (
        session.query(CommentInbox)
        .filter(
            CommentInbox.account_id == account.id,
            CommentInbox.platform == account.platform,
            CommentInbox.platform_post_id == post_id,
            CommentInbox.status.in_(["pending_approval", "failed"]),
        )
        .all()
    )
    for row in backlog_rows:
        comment_id = str(row.platform_comment_id or "").strip()
        if not comment_id or comment_id in seen:
            continue
        if lookback is not None and row.commented_at and row.commented_at < lookback:
            continue
        merged.append(
            InboundComment(
                platform_post_id=row.platform_post_id,
                platform_comment_id=comment_id,
                author_name=row.author_name,
                content=row.content or "",
                commented_at=row.commented_at,
                post_title=row.post_title,
            )
        )
        seen.add(comment_id)
    return merged


def resolve_inline_reply_text(
    existing: CommentInbox | None,
    *,
    comment: InboundComment,
    post_title: str | None,
    post_description: str | None,
    audience_name: str | None,
    min_length: int,
    max_length: int,
) -> str:
    if existing is not None:
        cached = str(existing.reply_text or "").strip()
        if cached:
            return validate_reply_text(cached, min_length=min_length, max_length=max_length)
    return generate_comment_reply(
        post_title=post_title or "",
        post_description=post_description,
        audience_comment=comment.content,
        audience_name=audience_name,
        min_length=min_length,
        max_length=max_length,
    )


def first_processable_comment_content(
    comments: list[InboundComment],
    *,
    session: Session,
    account: Any,
    account_nickname: str | None,
    author_first_comments: set[str],
    lookback: datetime | None,
    retry_max: int,
) -> str | None:
    from services.publishing.comment_reply.decision import should_process_comment
    from src.db.models.publishing import CommentInbox

    for comment in comments:
        existing = (
            session.query(CommentInbox)
            .filter_by(
                platform=account.platform,
                platform_comment_id=comment.platform_comment_id,
            )
            .first()
        )
        decision = should_process_comment(
            comment,
            existing_row=existing,
            account_nickname=account_nickname,
            author_first_comments=author_first_comments,
            lookback=lookback,
            intent="inline",
            retry_max=retry_max,
        )
        if decision.process and str(comment.content or "").strip():
            return str(comment.content).strip()
    return None
