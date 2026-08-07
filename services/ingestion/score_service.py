"""Persist article scores (rules + optional LLM commentary and grade adjustment)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from services.ingestion.article_score_llm import generate_score_review
from services.ingestion.post_score_automation import maybe_run_post_score_automation
from services.ingestion.article_scorer import (
    grade_from_total,
    load_scoring_config,
    score_article,
)
from src.db.models.ingestion import ArticleImage, IngestedArticle, Story, StoryArticle

SA_GRADES = frozenset({"S", "A"})


def _story_article_count(db: Session, article: IngestedArticle) -> int:
    if not article.story_id:
        return 1
    story = db.get(Story, article.story_id)
    if story and story.article_count:
        return story.article_count
    return (
        db.query(StoryArticle)
        .filter_by(story_id=article.story_id)
        .count()
        or 1
    )


def _image_count(db: Session, article_id: str) -> int:
    return (
        db.query(ArticleImage)
        .filter_by(article_id=article_id, download_status="ok")
        .count()
    )


def _load_keywords(article: IngestedArticle) -> list[str]:
    try:
        data = json.loads(article.keywords_json or "[]")
        return [str(x) for x in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _apply_llm_adjustment(
    rule_total: float,
    rule_grade: str,
    llm_payload: dict[str, Any],
    cfg: dict[str, Any],
) -> tuple[float, str, bool]:
    final_total = rule_total
    final_grade = rule_grade
    adjusted = False

    adj_grade = llm_payload.get("adjusted_grade")
    adj_score = llm_payload.get("adjusted_score")

    if adj_score is not None:
        final_total = float(adj_score)
        adjusted = abs(final_total - rule_total) > 0.5

    if adj_grade:
        if adj_grade != rule_grade:
            adjusted = True
        final_grade = adj_grade
    elif adj_score is not None:
        final_grade = grade_from_total(final_total, cfg)

    # Keep grade and score consistent when only grade was adjusted
    if adj_grade and adj_score is None:
        thresholds = cfg.get("grades") or {}
        grade_floors = {
            "S": float(thresholds.get("S", 85)),
            "A": float(thresholds.get("A", 70)),
            "B": float(thresholds.get("B", 55)),
            "C": float(thresholds.get("C", 40)),
            "D": 0.0,
        }
        floor = grade_floors.get(final_grade, 0.0)
        if final_total < floor:
            final_total = floor
            adjusted = True

    return final_total, final_grade, adjusted


def apply_score_to_article(
    db: Session,
    article: IngestedArticle,
    *,
    use_llm: bool = False,
    auto_llm_for_sa: bool = False,
) -> dict[str, Any]:
    cfg = load_scoring_config()
    rule_result = score_article(
        title=article.title or "",
        summary=article.summary,
        content_text=article.content_text,
        keywords=_load_keywords(article),
        published_at=article.published_at,
        view_count=article.view_count,
        story_article_count=_story_article_count(db, article),
        image_count=_image_count(db, article.id),
        config=cfg,
    )

    rule_total = rule_result.total
    rule_grade = rule_result.grade
    final_total = rule_total
    final_grade = rule_grade

    breakdown = rule_result.to_dict()
    breakdown["rule"] = {"total": round(rule_total, 1), "grade": rule_grade}

    llm_payload: dict[str, Any] | None = None
    llm_adjusted = False
    should_llm = use_llm or (auto_llm_for_sa and rule_grade in SA_GRADES)

    if should_llm:
        llm_payload = generate_score_review(
            title=article.title or "",
            summary=article.summary,
            source_id=article.source_id,
            rule_result=rule_result,
            content_excerpt=article.content_text,
        )
        if llm_payload:
            breakdown["llm"] = llm_payload
            final_total, final_grade, llm_adjusted = _apply_llm_adjustment(
                rule_total, rule_grade, llm_payload, cfg
            )

    breakdown["final"] = {
        "total": round(final_total, 1),
        "grade": final_grade,
        "adjusted_by": "llm" if llm_adjusted else "rule",
    }

    article.score_total = final_total
    article.score_grade = final_grade
    article.score_breakdown_json = json.dumps(breakdown, ensure_ascii=False)
    article.score_comment = (llm_payload or {}).get("comment") if llm_payload else None
    article.scored_at = datetime.utcnow()

    automation = maybe_run_post_score_automation(
        db,
        article,
        final_grade=final_grade,
        final_total=final_total,
        config=cfg,
    )

    return {
        "article_id": article.id,
        "score_total": article.score_total,
        "score_grade": article.score_grade,
        "rule_grade": rule_grade,
        "rule_total": rule_total,
        "score_breakdown": breakdown,
        "score_comment": article.score_comment,
        "llm_used": bool(llm_payload),
        "llm_adjusted": llm_adjusted,
        "post_score_automation": automation,
    }


def score_article_by_id(
    db: Session,
    article_id: str,
    *,
    use_llm: bool = False,
    auto_llm_for_sa: bool = False,
) -> dict[str, Any]:
    article = db.get(IngestedArticle, article_id)
    if article is None:
        raise ValueError(f"Article not found: {article_id}")
    return apply_score_to_article(
        db,
        article,
        use_llm=use_llm,
        auto_llm_for_sa=auto_llm_for_sa,
    )
