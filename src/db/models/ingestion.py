"""ORM models for news ingestion."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.engine import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class IngestionSource(Base):
    __tablename__ = "ingestion_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    adapter_class: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_cron: Mapped[str] = mapped_column(String(64), default="0 * * * *")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(32), default="manual")
    source_id: Mapped[str] = mapped_column(String(64), ForeignKey("ingestion_sources.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(64), ForeignKey("ingestion_sources.id"))
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestedArticle(Base):
    __tablename__ = "ingested_articles"
    __table_args__ = (UniqueConstraint("source_id", "canonical_url", name="uq_source_url"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(64), ForeignKey("ingestion_sources.id"))
    canonical_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    theme: Mapped[str | None] = mapped_column(String(128), nullable=True)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    cover_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_grade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    score_breakdown_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="fetched")
    crawl_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    story_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    images_scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    images_score_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_draft_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_draft_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    video_prep_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    video_prep_status_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_video_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    generated_video_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    selected_bgm_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    selected_images_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_pipeline_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    generated_cover_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    images: Mapped[list["ArticleImage"]] = relationship(back_populates="article")


class MediaGenerationJob(Base):
    __tablename__ = "media_generation_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    article_id: Mapped[str] = mapped_column(String(32), ForeignKey("ingested_articles.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    trigger_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ArticleImage(Base):
    __tablename__ = "article_images"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    article_id: Mapped[str] = mapped_column(String(32), ForeignKey("ingested_articles.id"))
    original_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    local_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    download_status: Mapped[str] = mapped_column(String(32), default="pending")
    origin: Mapped[str] = mapped_column(String(32), default="article_body")

    article: Mapped[IngestedArticle] = relationship(back_populates="images")


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    canonical_title: Mapped[str] = mapped_column(String(512), default="")
    topic_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    cluster_method: Mapped[str] = mapped_column(String(32), default="rule")
    cluster_score: Mapped[float] = mapped_column(Float, default=0.0)
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StoryArticle(Base):
    __tablename__ = "story_articles"
    __table_args__ = (UniqueConstraint("story_id", "article_id", name="uq_story_article"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id"))
    article_id: Mapped[str] = mapped_column(String(32), ForeignKey("ingested_articles.id"))
    role: Mapped[str] = mapped_column(String(32), default="related")
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)


class StoryAsset(Base):
    __tablename__ = "story_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    story_id: Mapped[str] = mapped_column(String(32), ForeignKey("stories.id"))
    asset_type: Mapped[str] = mapped_column(String(32), default="image")
    source_article_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ImageRelevanceEvaluation(Base):
    __tablename__ = "image_relevance_evaluations"
    __table_args__ = (
        UniqueConstraint("article_id", "source_type", "source_id", name="uq_image_relevance"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    article_id: Mapped[str] = mapped_column(String(32), ForeignKey("ingested_articles.id"))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    original_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    local_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_grade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    relevance_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    breakdown_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    vision_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scorer_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
