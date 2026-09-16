"""First-comment decision helpers and validation."""
from __future__ import annotations

from datetime import datetime

from services.publishing.adapters.base import CommentResult, PublishResult
from services.publishing.platform_capabilities import can_post_first_comment
from src.db.models.publishing import PublishJob
FIRST_COMMENT_MIN_LEN = 15
FIRST_COMMENT_MAX_LEN = 50
RETRYABLE_COMMENT_STATUSES = frozenset({"failed", "pending"})

COMMENT_STATUS_LABELS = {
    "none": "无",
    "pending": "待发",
    "posted": "已发",
    "failed": "失败",
    "skipped": "已跳过",
    "unsupported": "不支持",
}


def validate_first_comment(text: str) -> tuple[bool, str | None]:
    cleaned = (text or "").strip()
    if len(cleaned) < FIRST_COMMENT_MIN_LEN:
        return False, f"首评至少 {FIRST_COMMENT_MIN_LEN} 字"
    if len(cleaned) > FIRST_COMMENT_MAX_LEN:
        return False, f"首评不超过 {FIRST_COMMENT_MAX_LEN} 字"
    return True, None


def should_post_first_comment(
    *,
    first_comment_text: str | None,
    comment_status: str | None,
    platform_id: str,
    enabled: bool,
) -> bool:
    if not (first_comment_text or "").strip():
        return False
    if (comment_status or "").strip() == "posted":
        return False
    if not enabled:
        return False
    if not can_post_first_comment(platform_id):
        return False
    return True


def apply_comment_result(job: PublishJob, comment_result: CommentResult) -> None:
    if comment_result.success:
        job.comment_status = "posted"
        job.comment_posted_at = datetime.utcnow()
        job.comment_error_message = None
        return
    job.comment_status = "failed"
    job.comment_error_message = (comment_result.error_message or "发评失败")[:500]


def apply_comment_outcome(
    job: PublishJob,
    result: PublishResult,
    *,
    platform_id: str,
    enabled: bool,
) -> None:
    text = (job.first_comment_text or "").strip()
    if not text:
        job.comment_status = "none"
        return
    if (job.comment_status or "").strip() == "posted":
        return
    if not enabled:
        job.comment_status = "skipped"
        return
    if not can_post_first_comment(platform_id):
        job.comment_status = "unsupported"
        return

    comment_result = result.comment_result
    if comment_result is None:
        job.comment_status = "skipped"
        return
    apply_comment_result(job, comment_result)


def can_retry_comment(
    job: PublishJob,
    *,
    platform_id: str,
    retry_max: int = 3,
    force: bool = False,
) -> tuple[bool, str | None]:
    if job.status != "published":
        return False, "job_not_published"
    if not (job.first_comment_text or "").strip():
        return False, "no_comment_text"
    if (job.comment_status or "").strip() == "posted":
        return False, "already_posted"
    if (job.comment_status or "") not in RETRYABLE_COMMENT_STATUSES:
        return False, "comment_status_not_retryable"
    if not force and (job.comment_retry_count or 0) >= retry_max:
        return False, "retry_limit_reached"
    if not can_post_first_comment(platform_id):
        return False, "unsupported_platform"
    return True, None


def apply_comment_retry_outcome(job: PublishJob, comment_result: CommentResult) -> None:
    job.comment_retry_count = (job.comment_retry_count or 0) + 1
    apply_comment_result(job, comment_result)
