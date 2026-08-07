"""Pydantic schemas for ingestion API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IngestionSourceOut(BaseModel):
    id: str
    slug: str
    display_name: str
    adapter_class: str
    enabled: bool
    schedule_cron: str
    last_run_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None


class ArticleImageOut(BaseModel):
    id: str
    original_url: str
    local_path: Optional[str] = None
    download_status: str
    sort_order: int
    relevance_score: Optional[float] = None
    relevance_grade: Optional[str] = None
    relevance_rank: Optional[int] = None
    caption: Optional[str] = None
    verdict: Optional[str] = None
    cover_fit_score: Optional[float] = None
    figure_prominence_score: Optional[float] = None
    flash_fit_score: Optional[float] = None
    orientation: Optional[str] = None
    is_animated: Optional[bool] = None


class IngestedArticleOut(BaseModel):
    id: str
    source_id: str
    canonical_url: str
    title: str
    summary: Optional[str] = None
    published_at: Optional[datetime] = None
    theme: Optional[str] = None
    status: str
    created_at: datetime
    cover_image_url: Optional[str] = None
    view_count: Optional[int] = None
    score_total: Optional[float] = None
    score_grade: Optional[str] = None
    score_breakdown: Optional[Dict[str, Any]] = None
    score_comment: Optional[str] = None
    scored_at: Optional[datetime] = None
    content_text: Optional[str] = None
    video_draft_generated_at: Optional[datetime] = None
    video_prep_at: Optional[datetime] = None
    video_draft: Optional[Dict[str, Any]] = None
    video_prep_status: Optional[Dict[str, Any]] = None
    generated_video_path: Optional[str] = None
    generated_cover_path: Optional[str] = None
    generated_video_at: Optional[datetime] = None
    selected_bgm_path: Optional[str] = None
    media_pipeline_status: Optional[str] = None
    selected_images: List[Dict[str, Any]] = Field(default_factory=list)
    images: List[ArticleImageOut] = Field(default_factory=list)


class ScoreArticleRequest(BaseModel):
    use_llm: bool = True


class BatchScoreRequest(BaseModel):
    article_ids: List[str] = Field(default_factory=list)
    use_llm: bool = False
    source_id: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)


class JobOut(BaseModel):
    id: str
    job_type: str
    source_id: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None


class BatchSelectRequest(BaseModel):
    article_ids: List[str]


class PrepareVideoResponse(BaseModel):
    success: bool
    article_id: str
    metadata: Dict[str, Any]
    metadata_path: str
    content: str
    title: str
    images: List[Dict[str, Any]]
    story_id: Optional[str] = None
    story_merged_images: List[Dict[str, Any]] = Field(default_factory=list)
    auto_selected_images: List[Dict[str, Any]] = Field(default_factory=list)
    video_draft: Optional[Dict[str, Any]] = None
    generated_video_path: Optional[str] = None
    generated_cover_path: Optional[str] = None
    media_pipeline_status: Optional[str] = None


class ScoreImagesRequest(BaseModel):
    force: bool = False
    include_story_images: bool = True


class ImageRelevanceOut(BaseModel):
    source_type: str
    source_id: str
    original_url: str
    local_path: Optional[str] = None
    relevance_score: Optional[float] = None
    relevance_grade: Optional[str] = None
    relevance_rank: Optional[int] = None
    caption: Optional[str] = None
    verdict: Optional[str] = None
    auto_selected: bool = False
    breakdown: Optional[Dict[str, Any]] = None


class ScoreImagesResponse(BaseModel):
    success: bool
    article_id: str
    scored_count: int
    skipped_count: int
    vl_calls: int
    duration_ms: int
    vision_profile_id: Optional[str] = None
    scorer_version: str
    from_cache: bool = False
    images: List[ImageRelevanceOut] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class StoryOut(BaseModel):
    id: str
    canonical_title: str
    article_count: int
    cluster_method: str
    cluster_score: float
    created_at: datetime
    updated_at: datetime


class StoryAssetOut(BaseModel):
    id: str
    asset_type: str
    source_article_id: Optional[str] = None
    original_url: Optional[str] = None
    local_path: Optional[str] = None
    download_status: Optional[str] = None
    sort_order: int


class MergeStoriesRequest(BaseModel):
    article_ids: List[str]
