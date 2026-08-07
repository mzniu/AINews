"""Pick the best-scored image for video cover."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.ingestion import ArticleImage, ImageRelevanceEvaluation, StoryAsset


def _cover_fit_score(evaluation: ImageRelevanceEvaluation) -> float:
    if not evaluation.breakdown_json:
        return 0.0
    try:
        breakdown = json.loads(evaluation.breakdown_json)
    except json.JSONDecodeError:
        return 0.0
    dims = breakdown.get("dimensions") or {}
    cover = dims.get("cover_fit") or {}
    try:
        return float(cover.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _resolve_local_path(
    session: Session,
    evaluation: ImageRelevanceEvaluation,
    article_images: dict[str, ArticleImage],
) -> str | None:
    if evaluation.source_type == "article_image":
        row = article_images.get(evaluation.source_id)
        if row and row.download_status == "ok" and row.local_path:
            return row.local_path
        return None
    if evaluation.source_type == "story_asset":
        asset = session.get(StoryAsset, evaluation.source_id)
        if asset and asset.local_path:
            return asset.local_path
    return None


def pick_best_cover_image(session: Session, article_id: str) -> dict[str, Any] | None:
    evaluations = (
        session.query(ImageRelevanceEvaluation)
        .filter_by(article_id=article_id)
        .order_by(ImageRelevanceEvaluation.relevance_rank.asc())
        .all()
    )
    if not evaluations:
        return None

    article_images = {
        row.id: row
        for row in session.query(ArticleImage).filter_by(article_id=article_id).all()
    }
    candidates: list[dict[str, Any]] = []
    for evaluation in evaluations:
        local_path = _resolve_local_path(session, evaluation, article_images)
        if not local_path:
            continue
        candidates.append(
            {
                "local_path": local_path,
                "cover_fit_score": _cover_fit_score(evaluation),
                "relevance_score": float(evaluation.relevance_score or 0),
                "relevance_grade": evaluation.relevance_grade,
                "source_type": evaluation.source_type,
                "source_id": evaluation.source_id,
            }
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item["cover_fit_score"],
            item["relevance_score"],
        ),
        reverse=True,
    )
    return candidates[0]
