"""Recover publishing jobs and QR sessions stuck in active states."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from services.publishing.registry import load_publishing_yaml
from src.db.models.publishing import PublishJob, QrLoginSession

ACTIVE_QR_STATUSES = ("pending", "processing", "waiting_scan", "scanned")


def load_stale_job_minutes() -> int:
    defaults = load_publishing_yaml().get("defaults") or {}
    return int(defaults.get("stale_job_minutes", 15))


def load_publish_lock_timeout_sec() -> float:
    defaults = load_publishing_yaml().get("defaults") or {}
    upload = int(defaults.get("upload_timeout_sec", 600))
    return float(upload + 180)


def has_active_publish_job(session: Session) -> bool:
    """True when any job is currently uploading (enforce serial publish)."""
    return (
        session.query(PublishJob)
        .filter_by(status="uploading")
        .count()
        > 0
    )


def recover_stale_publish_jobs(
    session: Session,
    *,
    stale_minutes: int | None = None,
) -> int:
    now = datetime.utcnow()
    threshold = stale_minutes if stale_minutes is not None else load_stale_job_minutes()
    cutoff = now - timedelta(minutes=threshold)
    updated = 0
    for job in session.query(PublishJob).filter_by(status="uploading").all():
        anchor = job.started_at or job.created_at
        if anchor and anchor < cutoff:
            job.status = "failed"
            job.finished_at = now
            job.error_message = job.error_message or "任务中断或超时（可点击重试）"
            updated += 1
    if updated:
        session.commit()
    return updated


def recover_stale_qr_sessions(session: Session, *, stale_minutes: int = 5) -> int:
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=stale_minutes)
    updated = 0
    for row in session.query(QrLoginSession).filter(QrLoginSession.status.in_(ACTIVE_QR_STATUSES)):
        anchor = row.started_at or row.created_at
        if anchor and anchor < cutoff:
            row.status = "expired"
            row.finished_at = now
            row.error_message = row.error_message or "扫码会话超时"
            updated += 1
    if updated:
        session.commit()
    return updated
