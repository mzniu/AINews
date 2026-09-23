"""ORM models for publishing subsystem."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from services.industry.constants import DEFAULT_INDUSTRY_ID
from src.db.engine import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class PublisherAccount(Base):
    __tablename__ = "publisher_accounts"
    __table_args__ = (UniqueConstraint("platform", "platform_uid", name="uq_platform_uid"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    platform_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    session_path: Mapped[str] = mapped_column(String(512), nullable=False)
    browser_profile_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    browser_profile_version: Mapped[int] = mapped_column(Integer, default=1)
    last_fingerprint_probe: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_publish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("publisher_accounts.id"))
    video_path: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    cover_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    platform_post_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    platform_post_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metrics_match_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metrics_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_comment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_status: Mapped[str] = mapped_column(String(16), default="none")
    comment_posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    comment_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    playbook_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    copy_draft_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    playbook_attribution: Mapped[str | None] = mapped_column(String(32), nullable=True)


class AutoPublishCandidate(Base):
    __tablename__ = "auto_publish_candidates"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "platform",
            "policy_version",
            name="uq_auto_publish_candidate_policy",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    article_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ingested_articles.id"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reasons_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    publish_job_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("publish_jobs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    industry_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=DEFAULT_INDUSTRY_ID, index=True
    )


class AutoPublishDispatchLease(Base):
    __tablename__ = "auto_publish_dispatch_leases"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "dispatch_date",
            name="uq_auto_publish_dispatch_lease_day",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dispatch_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(32), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PublishLog(Base):
    __tablename__ = "publish_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("publish_jobs.id"))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text, default="")
    screenshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QrLoginSession(Base):
    __tablename__ = "qr_login_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), default="create")
    account_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    qr_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CommentInbox(Base):
    __tablename__ = "comment_inbox"
    __table_args__ = (
        UniqueConstraint("platform", "platform_comment_id", name="uq_comment_inbox_platform_comment"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("publisher_accounts.id"))
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_post_id: Mapped[str] = mapped_column(String(256), nullable=False)
    platform_comment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    publish_job_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("publish_jobs.id"), nullable=True)
    post_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    commented_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_approval")
    skip_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reply_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    post_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CommentReplyRun(Base):
    __tablename__ = "comment_reply_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(32), default="running")
    mode: Mapped[str] = mapped_column(String(16), default="approve")
    accounts_total: Mapped[int] = mapped_column(Integer, default=0)
    posts_scanned: Mapped[int] = mapped_column(Integer, default=0)
    comments_seen: Mapped[int] = mapped_column(Integer, default=0)
    new_pending: Mapped[int] = mapped_column(Integer, default=0)
    auto_sent: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    retried: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
