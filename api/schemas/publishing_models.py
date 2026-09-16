"""Pydantic models for publishing API."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class QrStartRequest(BaseModel):
    platform: str
    purpose: str = "create"
    account_id: Optional[str] = None


class QrStartResponse(BaseModel):
    success: bool = True
    session_id: str


class QrStatusResponse(BaseModel):
    session_id: str
    status: str
    qr_image_url: Optional[str] = None
    account_id: Optional[str] = None
    error_message: Optional[str] = None


class AccountStatusResponse(BaseModel):
    success: bool
    account_id: str
    status: str
    message: str
    nickname: Optional[str] = None
    platform: Optional[str] = None


class CreatePublishJobRequest(BaseModel):
    account_id: str
    video_path: str
    title: str
    description: Optional[str] = None
    main_line2: Optional[str] = None
    sub_title: Optional[str] = None
    sub_title2: Optional[str] = None
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    cover_path: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    first_comment_text: Optional[str] = None


class ReschedulePublishJobRequest(BaseModel):
    scheduled_at: datetime
    cascade: bool = True


class UpdatePublishPlatformsRequest(BaseModel):
    platforms: List[str] = Field(default_factory=list)


class PublishJobResponse(BaseModel):
    id: str
    account_id: str
    platform: Optional[str] = None
    platform_display_name: Optional[str] = None
    account_nickname: Optional[str] = None
    video_path: str
    title: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    cover_path: Optional[str] = None
    status: str
    platform_post_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    first_comment_text: Optional[str] = None
    comment_status: Optional[str] = None
    comment_posted_at: Optional[datetime] = None
    comment_error_message: Optional[str] = None
    comment_retry_count: int = 0


class ExtractCoverRequest(BaseModel):
    video_path: str


class PublishingHealthResponse(BaseModel):
    worker_mode: str
    worker_reachable: bool
    pending_jobs_count: int
    oldest_pending_seconds: Optional[float] = None


class PublishedPostMetrics(BaseModel):
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    favorite_count: Optional[int] = None
    follow_count: Optional[int] = None
    play_3s_rate: Optional[float] = None
    completion_rate: Optional[float] = None
    avg_watch_sec: Optional[float] = None
    profile_click_count: Optional[int] = None
    snapshot_date: Optional[str] = None
    fetched_at: Optional[str] = None


class PublishedPostResponse(BaseModel):
    job_id: str
    title: str
    platform: str
    platform_display_name: Optional[str] = None
    account_id: str
    account_nickname: Optional[str] = None
    published_at: Optional[str] = None
    platform_post_id: Optional[str] = None
    platform_post_url: Optional[str] = None
    metrics_match_status: str = "pending"
    metrics_last_synced_at: Optional[str] = None
    metrics: Optional[PublishedPostMetrics] = None


class MetricsSyncStatusResponse(BaseModel):
    success: bool = True
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    accounts_total: int = 0
    posts_synced: int = 0
    posts_unmatched: int = 0
    posts_failed: int = 0
    error_summary: Optional[str] = None


class MetricsSummaryTotals(BaseModel):
    posts_total: int = 0
    posts_with_metrics: int = 0
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    favorite_count: int = 0


class MetricsSummaryPlatformRow(MetricsSummaryTotals):
    platform: str
    platform_display_name: Optional[str] = None


class MetricsSummaryResponse(BaseModel):
    success: bool = True
    totals: MetricsSummaryTotals
    by_platform: List[MetricsSummaryPlatformRow] = Field(default_factory=list)


class BindPublishedPostRequest(BaseModel):
    platform_post_id: str
    platform_post_url: Optional[str] = None


class ViewDropAlert(BaseModel):
    job_id: str
    title: str = ""
    platform: Optional[str] = None
    platform_display_name: Optional[str] = None
    account_nickname: Optional[str] = None
    previous_snapshot_date: str
    current_snapshot_date: str
    previous_view_count: int
    current_view_count: int
    drop_count: int
    drop_pct: float


class MetricsAlertsResponse(BaseModel):
    success: bool = True
    alerts: List[ViewDropAlert] = Field(default_factory=list)


class CommentInboxResponse(BaseModel):
    id: str
    account_id: str
    platform: str
    platform_post_id: str
    platform_comment_id: str
    publish_job_id: Optional[str] = None
    post_title: Optional[str] = None
    author_name: Optional[str] = None
    content: str
    commented_at: Optional[datetime] = None
    status: str
    skip_reason: Optional[str] = None
    reply_text: Optional[str] = None
    replied_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    account_nickname: Optional[str] = None


class CommentInboxListResponse(BaseModel):
    success: bool = True
    items: List[CommentInboxResponse] = Field(default_factory=list)
    total: int = 0


class ApproveCommentReplyRequest(BaseModel):
    reply_text: Optional[str] = None


class CommentReplyRunResponse(BaseModel):
    id: str
    status: str
    mode: str
    accounts_total: int = 0
    posts_scanned: int = 0
    comments_seen: int = 0
    new_pending: int = 0
    auto_sent: int = 0
    skipped: int = 0
    failed: int = 0
    retried: int = 0
    error_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class CommentReplyRunListResponse(BaseModel):
    success: bool = True
    items: List[CommentReplyRunResponse] = Field(default_factory=list)
    total: int = 0


class CandidateListItem(BaseModel):
    id: str
    article_id: str
    title: str = ""
    platform: str
    action: str
    recommended_action: str
    priority: float = 0.0
    reasons: List[str] = Field(default_factory=list)
    status: str
    evaluated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class CandidateListResponse(BaseModel):
    success: bool = True
    items: List[CandidateListItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20


class CandidateActionResponse(BaseModel):
    success: bool = True
    candidate_id: str
    status: str
    publish_job_id: Optional[str] = None

