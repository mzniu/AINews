"""Global search across ingestion library and published posts."""
from __future__ import annotations

from typing import Generator, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.db.engine import get_session_factory
from src.db.models.ingestion import IngestedArticle
from src.db.models.publishing import PublishJob, PublisherAccount

router = APIRouter(prefix="/api", tags=["search"])


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.get("/search")
def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    like = f"%{q.strip()}%"
    article_rows = (
        db.query(IngestedArticle)
        .filter(IngestedArticle.title.like(like))
        .order_by(IngestedArticle.published_at.desc().nullslast())
        .limit(limit)
        .all()
    )
    post_rows = (
        db.query(PublishJob, PublisherAccount)
        .join(PublisherAccount, PublishJob.account_id == PublisherAccount.id)
        .filter(PublishJob.status == "published")
        .filter(PublishJob.title.like(like))
        .order_by(PublishJob.published_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "success": True,
        "query": q,
        "articles": [
            {
                "id": row.id,
                "title": row.title,
                "source_id": row.source_id,
                "score_grade": row.score_grade,
                "href": f"/ingestion-library?article={row.id}",
            }
            for row in article_rows
        ],
        "published_posts": [
            {
                "job_id": job.id,
                "title": job.title,
                "platform": account.platform,
                "account_nickname": account.nickname,
                "published_at": job.published_at.isoformat() if job.published_at else None,
                "href": "/publish-metrics",
            }
            for job, account in post_rows
        ],
    }
