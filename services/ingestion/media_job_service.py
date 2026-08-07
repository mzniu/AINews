"""Enqueue and process media generation jobs."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from services.ingestion.media_pipeline_trigger import (
    load_media_pipeline_config,
    should_run_media_pipeline,
)
from src.db.models.ingestion import IngestedArticle, MediaGenerationJob


def has_active_media_job(session: Session, article_id: str) -> bool:
    row = (
        session.query(MediaGenerationJob)
        .filter(
            MediaGenerationJob.article_id == article_id,
            MediaGenerationJob.status.in_(("pending", "running")),
        )
        .first()
    )
    return row is not None


def _pipeline_already_done(article: IngestedArticle, cfg: dict[str, Any]) -> bool:
    if not cfg.get("skip_if_done", True):
        return False
    if article.media_pipeline_status == "succeeded" and article.generated_video_path:
        return True
    if article.video_prep_at and article.media_pipeline_status == "succeeded":
        return True
    return False


def enqueue_media_job(
    session: Session,
    article_id: str,
    *,
    trigger_reason: str,
    final_grade: str,
    final_total: float,
) -> MediaGenerationJob | None:
    if has_active_media_job(session, article_id):
        return None
    article = session.get(IngestedArticle, article_id)
    if article is None:
        return None
    cfg = load_media_pipeline_config()
    if _pipeline_already_done(article, cfg):
        return None
    job = MediaGenerationJob(
        article_id=article_id,
        status="pending",
        trigger_reason=trigger_reason,
        payload_json=json.dumps(
            {"final_grade": final_grade, "final_total": final_total},
            ensure_ascii=False,
        ),
    )
    session.add(job)
    article.media_pipeline_status = "pending"
    session.flush()
    return job


def maybe_enqueue_media_job(
    session: Session,
    article: IngestedArticle,
    *,
    final_grade: str,
    final_total: float,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = load_media_pipeline_config(config)
    if not should_run_media_pipeline(
        final_grade=final_grade, final_total=final_total, config=config
    ):
        return {"skipped": True, "reason": "not_eligible"}
    reason = f"grade={final_grade},score={round(final_total, 1)}"
    job = enqueue_media_job(
        session,
        article.id,
        trigger_reason=reason,
        final_grade=final_grade,
        final_total=final_total,
    )
    if job is None:
        return {"skipped": True, "reason": "already_queued_or_done"}
    return {"enqueued": True, "job_id": job.id, "trigger_reason": reason}


def claim_next_media_job(session: Session) -> MediaGenerationJob | None:
    job = (
        session.query(MediaGenerationJob)
        .filter_by(status="pending")
        .order_by(MediaGenerationJob.created_at.asc())
        .first()
    )
    if job is None:
        return None
    job.status = "running"
    job.started_at = datetime.utcnow()
    session.flush()
    return job


def mark_media_job_finished(
    session: Session,
    job: MediaGenerationJob,
    *,
    success: bool,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    job.status = "succeeded" if success else "failed"
    job.finished_at = datetime.utcnow()
    job.error_message = error
    if result is not None:
        job.payload_json = json.dumps(result, ensure_ascii=False)
    session.flush()


def process_next_media_job(session: Session) -> dict[str, Any] | None:
    job = claim_next_media_job(session)
    if job is None:
        return None
    job_id = job.id
    article_id = job.article_id
    session.commit()

    from services.ingestion.media_pipeline import run_media_pipeline

    try:
        result = run_media_pipeline(session, article_id)
        job = session.get(MediaGenerationJob, job_id)
        if job is None:
            raise ValueError(f"Media job not found after pipeline: {job_id}")
        mark_media_job_finished(session, job, success=bool(result.get("success")), result=result)
        session.commit()
        return {"job_id": job_id, "article_id": article_id, **result}
    except Exception as exc:
        logger.exception(f"media job {job_id} failed: {exc}")
        job = session.get(MediaGenerationJob, job_id)
        if job is not None:
            mark_media_job_finished(session, job, success=False, error=str(exc))
        article = session.get(IngestedArticle, article_id)
        if article:
            article.media_pipeline_status = "failed"
        session.commit()
        return {"job_id": job_id, "success": False, "error": str(exc)}
