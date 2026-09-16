"""Unified process/skip decisions for comment reply scan, inline, and retry."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from services.publishing.comment_reply.filters import should_skip_comment
from services.publishing.comment_reply.types import InboundComment

Intent = Literal["scan", "retry", "inline"]


@dataclass(frozen=True)
class ProcessDecision:
    process: bool
    reason: str | None = None
    record_skip: bool = False
    update_status: str | None = None


def should_process_comment(
    comment: InboundComment,
    *,
    existing_row: object | None,
    account_nickname: str | None,
    author_first_comments: set[str],
    lookback: datetime | None = None,
    intent: Intent = "scan",
    retry_max: int = 3,
) -> ProcessDecision:
    if existing_row is not None:
        status = str(getattr(existing_row, "status", "") or "")
        if status == "replied":
            return ProcessDecision(process=False, reason="already_recorded")
        if status == "skipped":
            return ProcessDecision(process=False, reason="already_recorded")
        if intent == "inline":
            if status == "pending_approval":
                return ProcessDecision(process=True)
            if status == "failed":
                retry_count = int(getattr(existing_row, "retry_count", 0) or 0)
                if retry_count >= retry_max:
                    return ProcessDecision(process=False, reason="retry_exhausted")
                return ProcessDecision(process=True)
            return ProcessDecision(process=False, reason="already_recorded")
        if intent == "scan":
            return ProcessDecision(process=False, reason="already_recorded")
        if intent == "retry" and status not in {"failed", "pending_approval"}:
            return ProcessDecision(process=False, reason=f"invalid_status:{status}")

    if comment.already_replied_by_author:
        decision = ProcessDecision(
            process=False,
            reason="already_replied",
            record_skip=existing_row is None,
            update_status="skipped" if existing_row is not None else None,
        )
        return decision

    if lookback is not None and comment.commented_at and comment.commented_at < lookback:
        return ProcessDecision(process=False, reason="too_old", record_skip=True)

    skip_reason = should_skip_comment(
        comment,
        account_nickname=account_nickname,
        author_first_comments=author_first_comments,
    )
    if skip_reason:
        return ProcessDecision(process=False, reason=skip_reason, record_skip=True)

    return ProcessDecision(process=True)
