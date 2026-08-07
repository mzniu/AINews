"""Batch backfill for image relevance scoring."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.ingestion.image_score_service import score_article_images
from src.db.models.ingestion import ArticleImage, IngestedArticle


def _article_has_scorable_images(session: Session, article_id: str) -> bool:
    return (
        session.query(ArticleImage)
        .filter_by(article_id=article_id, download_status="ok")
        .filter(ArticleImage.local_path.isnot(None))
        .count()
        > 0
    )


def backfill_image_scores(
    session: Session,
    *,
    source_id: str | None = None,
    article_id: str | None = None,
    limit: int = 50,
    force: bool = False,
    include_story_images: bool = True,
) -> dict[str, Any]:
    """Score images for multiple articles. Returns summary counters."""
    query = session.query(IngestedArticle).order_by(IngestedArticle.created_at.desc())
    if source_id:
        query = query.filter_by(source_id=source_id)
    if article_id:
        query = query.filter_by(id=article_id)
    rows = query.limit(max(1, limit)).all()

    processed = 0
    scored = 0
    skipped = 0
    errors: list[dict[str, str]] = []

    for row in rows:
        processed += 1
        if not _article_has_scorable_images(session, row.id):
            skipped += 1
            continue
        try:
            result = score_article_images(
                session,
                row.id,
                force=force,
                include_story_images=include_story_images,
            )
            session.commit()
            if result.get("scored_count", 0) > 0:
                scored += 1
            else:
                skipped += 1
        except Exception as exc:
            session.rollback()
            errors.append({"article_id": row.id, "error": str(exc)})

    return {
        "processed": processed,
        "scored": scored,
        "skipped": skipped,
        "errors": errors,
    }
