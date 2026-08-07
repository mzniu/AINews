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


class ExtractCoverRequest(BaseModel):
    video_path: str


class PublishingHealthResponse(BaseModel):
    worker_mode: str
    worker_reachable: bool
    pending_jobs_count: int
    oldest_pending_seconds: Optional[float] = None
