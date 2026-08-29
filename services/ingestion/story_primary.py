"""Story primary election and one-pipeline-per-story gates."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.ingestion import IngestedArticle, MediaGenerationJob, Story, StoryArticle


def _member_articles(session: Session, story_id: str) -> list[IngestedArticle]:
    member_ids = [
        row.article_id
        for row in session.query(StoryArticle).filter_by(story_id=story_id).all()
    ]
    articles: list[IngestedArticle] = []
    for article_id in member_ids:
        article = session.get(IngestedArticle, article_id)
        if article is not None:
            articles.append(article)
    return articles


def elect_primary_article(articles: list[IngestedArticle]) -> IngestedArticle | None:
    """Higher score_total wins; earlier created_at wins ties."""
    if not articles:
        return None
    return sorted(
        articles,
        key=lambda row: (
            -(float(row.score_total or 0)),
            row.created_at or datetime.max,
        ),
    )[0]


def refresh_story_primary(session: Session, story_id: str) -> str | None:
    articles = _member_articles(session, story_id)
    primary = elect_primary_article(articles)
    if primary is None:
        return None

    story = session.get(Story, story_id)
    if story is None:
        return None

    story.primary_article_id = primary.id
    story.updated_at = datetime.utcnow()
    for link in session.query(StoryArticle).filter_by(story_id=story_id):
        link.role = "primary" if link.article_id == primary.id else "related"
    session.flush()
    return primary.id


def _sibling_has_completed_pipeline(session: Session, story_id: str, *, exclude_id: str) -> str | None:
    for article in _member_articles(session, story_id):
        if article.id == exclude_id:
            continue
        if article.media_pipeline_status == "succeeded" and article.generated_video_path:
            return article.id
        active = (
            session.query(MediaGenerationJob)
            .filter(
                MediaGenerationJob.article_id == article.id,
                MediaGenerationJob.status.in_(("pending", "running")),
            )
            .first()
        )
        if active is not None:
            return article.id
    return None


def load_story_gate_config(config: dict[str, Any] | None = None) -> dict[str, bool]:
    from services.ingestion.article_scorer import load_scoring_config

    active = config or load_scoring_config()
    auto = active.get("post_score_automation") or {}
    gate = auto.get("story_gate") or {}
    return {
        "enabled": bool(gate.get("enabled", True)),
        "require_primary": bool(gate.get("require_primary", True)),
        "one_pipeline_per_story": bool(gate.get("one_pipeline_per_story", True)),
    }


def check_story_media_pipeline_gate(
    session: Session,
    article: IngestedArticle,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return skip payload when article must not enter media pipeline."""
    gate = load_story_gate_config(config)
    if not gate.get("enabled", True):
        return None
    if not article.story_id:
        return None

    story = session.get(Story, article.story_id)
    if story is None:
        return None

    if gate.get("require_primary", True):
        if story.primary_article_id and story.primary_article_id != article.id:
            return {
                "skipped": True,
                "reason": "not_story_primary",
                "story_id": story.id,
                "primary_article_id": story.primary_article_id,
            }

    if gate.get("one_pipeline_per_story", True):
        sibling_id = _sibling_has_completed_pipeline(
            session, story.id, exclude_id=article.id
        )
        if sibling_id:
            return {
                "skipped": True,
                "reason": "story_pipeline_active_or_done",
                "story_id": story.id,
                "sibling_article_id": sibling_id,
            }
    return None
