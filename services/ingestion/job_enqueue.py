"""Enqueue ingestion crawl jobs with SQLite-safe writes."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from services.ingestion.db_retry import serialized_sqlite_write
from services.ingestion.job_recovery import recover_stale_jobs
from src.db.models.ingestion import IngestionJob


def find_active_ingestion_job(session: Session, source_id: str) -> IngestionJob | None:
    return (
        session.query(IngestionJob)
        .filter(
            IngestionJob.source_id == source_id,
            IngestionJob.status.in_(("running", "pending")),
        )
        .order_by(IngestionJob.created_at.desc())
        .first()
    )


def enqueue_ingestion_job(
    session: Session,
    *,
    source_id: str,
    job_type: str = "manual",
) -> tuple[IngestionJob | None, bool]:
    """Return (job, created). created=False when reusing an active queued/running job."""

    def _write() -> tuple[IngestionJob | None, bool]:
        recover_stale_jobs(session)
        active = find_active_ingestion_job(session, source_id)
        if active is not None:
            return active, False
        job = IngestionJob(job_type=job_type, source_id=source_id, status="pending")
        session.add(job)
        session.commit()
        session.refresh(job)
        return job, True

    return serialized_sqlite_write(_write)


def find_active_article_recrawl_job(session: Session, article_id: str) -> IngestionJob | None:
    needle = f'"article_id": "{article_id}"'
    return (
        session.query(IngestionJob)
        .filter(
            IngestionJob.job_type == "article_recrawl",
            IngestionJob.status.in_(("running", "pending")),
            IngestionJob.payload_json.contains(needle),
        )
        .order_by(IngestionJob.created_at.desc())
        .first()
    )


def enqueue_article_recrawl(
    session: Session,
    *,
    article_id: str,
    source_id: str,
) -> tuple[IngestionJob | None, bool]:
    """Return (job, created). created=False when reusing an active queued/running job."""

    def _write() -> tuple[IngestionJob | None, bool]:
        recover_stale_jobs(session)
        active = find_active_article_recrawl_job(session, article_id)
        if active is not None:
            return active, False
        job = IngestionJob(job_type="article_recrawl", source_id=source_id, status="pending")
        job.payload_json = json.dumps({"article_id": article_id, "source_id": source_id}, ensure_ascii=False)
        session.add(job)
        session.commit()
        session.refresh(job)
        return job, True

    return serialized_sqlite_write(_write)
