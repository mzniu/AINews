"""Post-score hook: enqueue async media pipeline (replaces synchronous automation)."""
from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from services.ingestion.media_job_service import maybe_enqueue_media_job
from src.db.models.ingestion import IngestedArticle


def maybe_run_post_score_automation(
    db: Session,
    article: IngestedArticle,
    *,
    final_grade: str,
    final_total: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Enqueue media pipeline if eligible. Never raises."""
    try:
        total = float(final_total if final_total is not None else article.score_total or 0)
        return maybe_enqueue_media_job(
            db,
            article,
            final_grade=final_grade,
            final_total=total,
            config=config,
        )
    except Exception as exc:
        logger.exception(f"post_score_automation enqueue failed article={article.id}: {exc}")
        return {"success": False, "errors": [str(exc)]}
