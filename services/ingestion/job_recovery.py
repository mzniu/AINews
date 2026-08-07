"""Recover ingestion jobs stuck in running state."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.db.models.ingestion import CrawlRun, IngestionJob

DEFAULT_STALE_MINUTES = 30


def recover_stale_jobs(session: Session, *, stale_minutes: int = DEFAULT_STALE_MINUTES) -> int:
    """Reconcile running jobs with finished crawl runs or mark stale ones failed."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=stale_minutes)
    updated = 0

    running_jobs = session.query(IngestionJob).filter_by(status="running").all()
    for job in running_jobs:
        crawl_run = (
            session.query(CrawlRun)
            .filter_by(job_id=job.id)
            .order_by(CrawlRun.started_at.desc())
            .first()
        )
        if crawl_run and crawl_run.finished_at:
            job.status = "succeeded" if crawl_run.status in {"succeeded", "partial"} else "failed"
            job.finished_at = crawl_run.finished_at
            job.payload_json = crawl_run.stats_json or job.payload_json
            if job.status == "failed" and crawl_run.error_message:
                job.error_message = crawl_run.error_message
            updated += 1
            continue

        anchor = job.started_at or job.created_at
        if anchor and anchor < cutoff:
            job.status = "failed"
            job.finished_at = now
            job.error_message = job.error_message or "任务超时或 worker 未运行，已自动回收"
            updated += 1

    if updated:
        session.commit()
    return updated
