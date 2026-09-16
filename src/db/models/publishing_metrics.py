"""ORM models for publish post metrics."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.engine import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class PublishPostMetricSnapshot(Base):
    __tablename__ = "publish_post_metric_snapshots"
    __table_args__ = (
        UniqueConstraint("job_id", "snapshot_date", name="uq_publish_metric_job_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("publish_jobs.id"), nullable=False)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("publisher_accounts.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    share_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favorite_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follow_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    play_3s_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_watch_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    profile_click_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PublishMetricsSyncRun(Base):
    __tablename__ = "publish_metrics_sync_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(32), default="running")
    accounts_total: Mapped[int] = mapped_column(Integer, default=0)
    posts_synced: Mapped[int] = mapped_column(Integer, default=0)
    posts_failed: Mapped[int] = mapped_column(Integer, default=0)
    posts_unmatched: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
