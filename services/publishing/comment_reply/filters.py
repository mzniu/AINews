"""Filter inbound comments before reply generation."""
from __future__ import annotations

from services.publishing.comment_reply.types import InboundComment


def should_skip_comment(
    comment: InboundComment,
    *,
    account_nickname: str | None,
    author_first_comments: set[str],
) -> str | None:
    content = (comment.content or "").strip()
    if not content:
        return "empty_content"
    if comment.already_replied_by_author:
        return "already_replied"
    nickname = (comment.author_name or "").strip()
    account_name = (account_nickname or "").strip()
    if nickname and account_name and nickname == account_name:
        return "author_own_comment"
    if content in author_first_comments:
        return "author_first_comment"
    return None
