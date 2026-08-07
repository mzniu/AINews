"""Story clustering: title similarity + keywords + time window."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from src.db.models.ingestion import (
    ArticleImage,
    IngestedArticle,
    Story,
    StoryArticle,
    StoryAsset,
)

TITLE_NOISE = re.compile(
    r"(独家|刚刚|重磅|突发|首发|深度|原创|快讯|丨|｜|\||!|！|\?|？|…)"
)
DEFAULT_THRESHOLD = 0.72
DEFAULT_HOURS_WINDOW = 72


def normalize_title(title: str) -> str:
    text = (title or "").strip().lower()
    text = TITLE_NOISE.sub("", text)
    text = re.sub(r"\s+", "", text)
    return text


def title_similarity(left: str, right: str) -> float:
    a = normalize_title(left)
    b = normalize_title(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def keywords_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a = {k.strip().lower() for k in left if k and str(k).strip()}
    b = {k.strip().lower() for k in right if k and str(k).strip()}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_keywords(article: IngestedArticle) -> List[str]:
    try:
        data = json.loads(article.keywords_json or "[]")
        return [str(x) for x in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


@dataclass
class ClusterMatch:
    story_id: str
    score: float
    article_id: str


def score_pair(article: IngestedArticle, other: IngestedArticle) -> float:
    t_score = title_similarity(article.title, other.title)
    k_score = keywords_jaccard(load_keywords(article), load_keywords(other))
    theme_bonus = 0.1 if article.theme and article.theme == other.theme else 0.0
    return t_score * 0.6 + k_score * 0.3 + theme_bonus


def find_best_story_match(
    session: Session,
    article: IngestedArticle,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    hours_window: int = DEFAULT_HOURS_WINDOW,
) -> Optional[ClusterMatch]:
    if article.story_id:
        return ClusterMatch(story_id=article.story_id, score=1.0, article_id=article.id)

    window_start = None
    if article.published_at:
        window_start = article.published_at - timedelta(hours=hours_window)
        window_end = article.published_at + timedelta(hours=hours_window)
    else:
        window_end = None

    q = session.query(IngestedArticle).filter(IngestedArticle.id != article.id)
    if window_start and window_end:
        q = q.filter(
            IngestedArticle.published_at.isnot(None),
            IngestedArticle.published_at >= window_start,
            IngestedArticle.published_at <= window_end,
        )
    candidates = q.order_by(IngestedArticle.published_at.desc()).limit(200).all()

    best: Optional[ClusterMatch] = None
    for other in candidates:
        score = score_pair(article, other)
        if score < threshold:
            continue
        story_id = other.story_id
        if not story_id:
            continue
        if best is None or score > best.score:
            best = ClusterMatch(story_id=story_id, score=score, article_id=other.id)
    return best


def assign_article_to_story(
    session: Session,
    article: IngestedArticle,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    hours_window: int = DEFAULT_HOURS_WINDOW,
) -> Optional[str]:
    if article.story_id:
        return article.story_id

    match = find_best_story_match(
        session, article, threshold=threshold, hours_window=hours_window
    )
    if match:
        story = session.get(Story, match.story_id)
        if story is None:
            return None
        article.story_id = story.id
        role = "related"
        existing_primary = (
            session.query(StoryArticle)
            .filter_by(story_id=story.id, role="primary")
            .first()
        )
        if existing_primary is None:
            role = "primary"
        link = StoryArticle(
            story_id=story.id,
            article_id=article.id,
            role=role,
            similarity_score=match.score,
        )
        session.add(link)
        story.article_count = (story.article_count or 0) + 1
        story.updated_at = datetime.utcnow()
        expand_story_assets(session, story.id)
        return story.id

    story = Story(
        canonical_title=article.title,
        topic_keywords_json=json.dumps(load_keywords(article), ensure_ascii=False),
        cluster_method="rule",
        cluster_score=1.0,
        article_count=1,
    )
    session.add(story)
    session.flush()
    article.story_id = story.id
    session.add(
        StoryArticle(
            story_id=story.id,
            article_id=article.id,
            role="primary",
            similarity_score=1.0,
        )
    )
    expand_story_assets(session, story.id)
    return story.id


def expand_story_assets(session: Session, story_id: str) -> int:
    """Merge images from all member articles into story_assets (dedupe by URL)."""
    session.query(StoryAsset).filter_by(story_id=story_id, asset_type="image").delete()
    member_ids = [
        row.article_id
        for row in session.query(StoryArticle).filter_by(story_id=story_id).all()
    ]
    if not member_ids:
        return 0

    seen_urls: Set[str] = set()
    added = 0
    sort_order = 0
    for article_id in member_ids:
        images = (
            session.query(ArticleImage)
            .filter_by(article_id=article_id)
            .order_by(ArticleImage.sort_order)
            .all()
        )
        for image in images:
            key = image.original_url.strip()
            if not key or key in seen_urls:
                continue
            seen_urls.add(key)
            sort_order += 1
            payload = {
                "original_url": image.original_url,
                "local_path": image.local_path,
                "download_status": image.download_status,
            }
            session.add(
                StoryAsset(
                    story_id=story_id,
                    asset_type="image",
                    source_article_id=article_id,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    is_selected=True,
                    sort_order=sort_order,
                )
            )
            added += 1

    story = session.get(Story, story_id)
    if story:
        story.updated_at = datetime.utcnow()
    return added


def merge_articles_into_story(session: Session, article_ids: List[str]) -> str:
    articles = [session.get(IngestedArticle, aid) for aid in article_ids]
    articles = [a for a in articles if a is not None]
    if not articles:
        raise ValueError("No valid articles")

    primary = articles[0]
    story_id = primary.story_id
    if not story_id:
        story = Story(
            canonical_title=primary.title,
            topic_keywords_json=json.dumps(load_keywords(primary), ensure_ascii=False),
            cluster_method="manual",
            cluster_score=1.0,
            article_count=0,
        )
        session.add(story)
        session.flush()
        story_id = story.id

    story = session.get(Story, story_id)
    assert story is not None
    for index, article in enumerate(articles):
        if article.story_id and article.story_id != story_id:
            session.query(StoryArticle).filter_by(article_id=article.id).delete()
        article.story_id = story_id
        exists = (
            session.query(StoryArticle)
            .filter_by(story_id=story_id, article_id=article.id)
            .first()
        )
        if not exists:
            session.add(
                StoryArticle(
                    story_id=story_id,
                    article_id=article.id,
                    role="primary" if index == 0 else "related",
                    similarity_score=1.0 if index == 0 else 0.9,
                )
            )
    story.article_count = (
        session.query(StoryArticle).filter_by(story_id=story_id).count()
    )
    story.updated_at = datetime.utcnow()
    expand_story_assets(session, story_id)
    return story_id
