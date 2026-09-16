"""Look up which ingested articles already have a published job."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from src.db.models.publishing import PublishJob

INGESTION_SOURCE_TYPE = "ingestion"


def published_ingestion_ids(db: Session, article_ids: Iterable[str]) -> set[str]:
    ids = [str(aid).strip() for aid in article_ids if str(aid or "").strip()]
    if not ids:
        return set()
    rows = (
        db.query(PublishJob.source_id)
        .filter(
            PublishJob.source_type == INGESTION_SOURCE_TYPE,
            PublishJob.source_id.in_(ids),
            PublishJob.status == "published",
        )
        .distinct()
        .all()
    )
    return {str(row.source_id) for row in rows if row.source_id}
