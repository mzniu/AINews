"""Story-level AI review: coherence check and merge suggestions."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from services.ingestion.story_cluster_config import load_story_cluster_config
from services.ingestion.story_cluster_llm import review_merge_stories, review_story_members
from services.ingestion.story_cluster_scoring import evaluate_pair_match
from src.db.models.ingestion import IngestedArticle, Story, StoryArticle


def _story_member_articles(session: Session, story_id: str) -> list[IngestedArticle]:
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


def _story_payload(session: Session, story: Story) -> dict[str, Any]:
    articles = _story_member_articles(session, story.id)
    primary = next((a for a in articles if a.id == story.primary_article_id), None)
    if primary is None and articles:
        primary = articles[0]
    return {
        "story_id": story.id,
        "canonical_title": story.canonical_title,
        "article_count": story.article_count,
        "primary_title": primary.title if primary else "",
        "articles": [
            {
                "id": article.id,
                "source_id": article.source_id,
                "title": article.title,
                "summary": (article.summary or "")[:200],
            }
            for article in articles[:8]
        ],
    }


def review_single_story(session: Session, story_id: str) -> dict[str, Any]:
    story = session.get(Story, story_id)
    if story is None:
        raise ValueError(f"Story not found: {story_id}")

    articles = _story_member_articles(session, story_id)
    if len(articles) < 2:
        return {
            "story_id": story_id,
            "skipped": True,
            "reason": "single_article_story",
        }

    llm_payload = [
        {
            "id": article.id,
            "source_id": article.source_id,
            "title": article.title,
            "summary": (article.summary or "")[:200],
        }
        for article in articles
    ]
    review = review_story_members(story_title=story.canonical_title, articles=llm_payload)
    suggestions: list[dict[str, Any]] = []
    if review and not review.get("coherent") and review.get("outlier_article_ids"):
        for article_id in review["outlier_article_ids"]:
            suggestions.append(
                {
                    "type": "split_article",
                    "article_id": article_id,
                    "confidence": review.get("confidence"),
                    "reason": review.get("reason"),
                }
            )

    return {
        "story_id": story_id,
        "article_count": len(articles),
        "review": review,
        "suggestions": suggestions,
    }


def _pair_blended_score(left: IngestedArticle, right: IngestedArticle, cfg: dict[str, Any]) -> float:
    result = evaluate_pair_match(left, right, config=cfg)
    return result.blended_score


def scan_merge_candidates(
    session: Session,
    *,
    limit: int = 30,
    hours_window: int = 72,
) -> list[dict[str, Any]]:
    cfg = load_story_cluster_config()
    review_cfg = cfg.get("review") or {}
    threshold = float(review_cfg.get("merge_candidate_threshold", 0.62))
    min_conf = float((cfg.get("llm") or {}).get("min_confidence", 0.7))

    window_start = datetime.utcnow() - timedelta(hours=hours_window)
    stories = (
        session.query(Story)
        .filter(Story.updated_at >= window_start, Story.article_count >= 1)
        .order_by(Story.updated_at.desc())
        .limit(limit * 2)
        .all()
    )

    candidates: list[dict[str, Any]] = []
    for index, left_story in enumerate(stories):
        left_articles = _story_member_articles(session, left_story.id)
        if not left_articles:
            continue
        left_primary = next(
            (a for a in left_articles if a.id == left_story.primary_article_id),
            left_articles[0],
        )
        for right_story in stories[index + 1 :]:
            if left_story.id == right_story.id:
                continue
            right_articles = _story_member_articles(session, right_story.id)
            if not right_articles:
                continue
            right_primary = next(
                (a for a in right_articles if a.id == right_story.primary_article_id),
                right_articles[0],
            )
            blended = _pair_blended_score(left_primary, right_primary, cfg)
            if blended < threshold:
                continue

            merge_review = review_merge_stories(
                story_a=_story_payload(session, left_story),
                story_b=_story_payload(session, right_story),
                blended_score=blended,
            )
            if merge_review is None:
                continue
            if not merge_review.get("should_merge"):
                continue
            if float(merge_review.get("confidence") or 0) < min_conf:
                continue

            candidates.append(
                {
                    "type": "merge_stories",
                    "story_id_a": left_story.id,
                    "story_id_b": right_story.id,
                    "title_a": left_story.canonical_title,
                    "title_b": right_story.canonical_title,
                    "blended_score": round(blended, 3),
                    "confidence": merge_review.get("confidence"),
                    "reason": merge_review.get("reason"),
                    "article_ids": [article.id for article in left_articles + right_articles],
                }
            )
            if len(candidates) >= limit:
                return candidates
    return candidates


def run_cluster_review(
    session: Session,
    *,
    limit: int = 30,
) -> dict[str, Any]:
    cfg = load_story_cluster_config()
    review_cfg = cfg.get("review") or {}
    if not review_cfg.get("enabled", True):
        return {"skipped": True, "reason": "review_disabled"}

    scan_limit = int(review_cfg.get("scan_limit", limit))
    hours_window = int(cfg.get("hours_window", 72))

    window_start = datetime.utcnow() - timedelta(hours=hours_window)
    stories = (
        session.query(Story)
        .filter(Story.updated_at >= window_start, Story.article_count >= 2)
        .order_by(Story.updated_at.desc())
        .limit(scan_limit)
        .all()
    )

    story_reviews = [review_single_story(session, story.id) for story in stories]
    merge_candidates = scan_merge_candidates(
        session,
        limit=min(20, scan_limit),
        hours_window=hours_window,
    )

    split_suggestions = []
    for item in story_reviews:
        split_suggestions.extend(item.get("suggestions") or [])

    return {
        "reviewed_stories": len(story_reviews),
        "incoherent_stories": sum(
            1 for item in story_reviews if item.get("review") and not item["review"].get("coherent", True)
        ),
        "story_reviews": story_reviews,
        "merge_suggestions": merge_candidates,
        "split_suggestions": split_suggestions,
    }
