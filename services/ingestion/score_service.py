"""Persist article scores (rules + optional LLM commentary and grade adjustment)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from services.ingestion.article_score_llm import generate_score_review
from services.ingestion.hot_radar_service import (
    ensure_fresh_hot_radar,
    load_hot_radar_config,
    match_article_hot_radar,
)
from services.ingestion.post_score_automation import maybe_run_post_score_automation
from services.ingestion.article_scorer import (
    grade_from_total,
    load_scoring_config,
    score_article,
)
from services.ingestion.publish_tier import compute_publish_tier
from services.ingestion.viral_scorer import score_viral_potential
from src.db.models.ingestion import ArticleImage, IngestedArticle, Story, StoryArticle

SA_GRADES = frozenset({"S", "A"})


def _prominence_score(rule_result) -> float:
    for dim in rule_result.dimensions:
        if dim.key == "prominence":
            return float(dim.score)
    return 0.0


def _build_dual_breakdown(
    *,
    rule_result,
    viral_result,
    rule_total: float,
    rule_grade: str,
    final_total: float,
    final_grade: str,
    adjusted_by: str,
    hot_radar_payload: dict[str, Any] | None = None,
    llm_payload: dict[str, Any] | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    industry = rule_result.to_dict()
    viral = viral_result.to_dict()
    publish_tier = compute_publish_tier(
        industry_grade=final_grade,
        industry_total=final_total,
        viral_grade=viral_result.grade,
        hook_gate_passed=viral_result.hook_gate.passed,
        config=cfg,
    )
    breakdown: dict[str, Any] = {
        "profile": industry.get("profile"),
        "industry": industry,
        "viral": viral,
        "rule": {"total": round(rule_total, 1), "grade": rule_grade},
        "final": {
            "industry_total": round(final_total, 1),
            "industry_grade": final_grade,
            "viral_total": round(viral_result.total, 1),
            "viral_grade": viral_result.grade,
            "publish_tier": publish_tier,
            "total": round(final_total, 1),
            "grade": final_grade,
            "adjusted_by": adjusted_by,
        },
        # backward compatibility for legacy readers
        "total": round(final_total, 1),
        "grade": final_grade,
        "dimensions": industry.get("dimensions", []),
        "bonuses": industry.get("bonuses", []),
        "penalties": industry.get("penalties", []),
        "recommendation": industry.get("recommendation"),
    }
    if hot_radar_payload is not None:
        breakdown["hot_radar"] = hot_radar_payload
    if llm_payload is not None:
        breakdown["llm"] = llm_payload
    return breakdown


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


def _merge_scoring_config() -> dict[str, Any]:
    cfg = load_scoring_config()
    radar_cfg = load_hot_radar_config()
    if radar_cfg.get("enabled", True):
        cfg = {**cfg, "hot_radar": radar_cfg}
    else:
        weights = dict(cfg.get("weights") or {})
        weights["hot_radar"] = 0.0
        cfg = {**cfg, "weights": weights}
    return cfg


def apply_score_to_article(
    db: Session,
    article: IngestedArticle,
    *,
    use_llm: bool = False,
    auto_llm_for_sa: bool = False,
) -> dict[str, Any]:
    cfg = _merge_scoring_config()
    radar_cfg = cfg.get("hot_radar") or {}
    hot_match = None
    if radar_cfg.get("enabled", True):
        ensure_fresh_hot_radar(db, config=radar_cfg)
        hot_match = match_article_hot_radar(
            db,
            title=article.title or "",
            url=article.canonical_url,
            config=radar_cfg,
            article_id=article.id,
        )

    rule_result = score_article(
        title=article.title or "",
        summary=article.summary,
        content_text=article.content_text,
        keywords=_load_keywords(article),
        published_at=article.published_at,
        view_count=article.view_count,
        story_article_count=_story_article_count(db, article),
        image_count=_image_count(db, article.id),
        hot_radar_match=hot_match,
        config=cfg,
    )

    story_count = _story_article_count(db, article)
    viral_result = score_viral_potential(
        title=article.title or "",
        summary=article.summary,
        content_text=article.content_text,
        prominence_score=_prominence_score(rule_result),
        story_article_count=story_count,
        hot_radar_match=hot_match,
        config=cfg,
    )

    rule_total = rule_result.total
    rule_grade = rule_result.grade
    final_total = rule_total
    final_grade = rule_grade

    hot_radar_payload: dict[str, Any] | None = None
    if hot_match is not None:
        hot_radar_payload = {
            "rank": hot_match.rank,
            "effective_rank": getattr(hot_match, "effective_rank", hot_match.rank),
            "confidence": getattr(hot_match, "confidence", 1.0),
            "heat_label": hot_match.heat_label,
            "heat_value": hot_match.heat_value,
            "hot_title": hot_match.hot_title,
            "match_method": hot_match.match_method,
            "board": hot_match.board,
            "source": hot_match.source,
            "board_id": hot_match.board_id,
            "board_name": hot_match.board_name,
            "board_display": hot_match.board_display,
            "inherited_from_article_id": getattr(hot_match, "inherited_from_article_id", None),
        }

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
            final_total, final_grade, llm_adjusted = _apply_llm_adjustment(
                rule_total, rule_grade, llm_payload, cfg
            )

    breakdown = _build_dual_breakdown(
        rule_result=rule_result,
        viral_result=viral_result,
        rule_total=rule_total,
        rule_grade=rule_grade,
        final_total=final_total,
        final_grade=final_grade,
        adjusted_by="llm" if llm_adjusted else "rule",
        hot_radar_payload=hot_radar_payload,
        llm_payload=llm_payload,
        cfg=cfg,
    )

    article.score_total = final_total
    article.score_grade = final_grade
    article.score_breakdown_json = json.dumps(breakdown, ensure_ascii=False)
    article.score_comment = (llm_payload or {}).get("comment") if llm_payload else None
    article.scored_at = datetime.utcnow()

    if article.story_id:
        from services.ingestion.story_primary import refresh_story_primary

        refresh_story_primary(db, article.story_id)

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
        "viral_score_total": viral_result.total,
        "viral_score_grade": viral_result.grade,
        "publish_tier": breakdown["final"]["publish_tier"],
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
