"""Orchestrate image relevance scoring: build candidates, rules, VL, persist."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from services.ingestion.db_retry import run_with_sqlite_retry
from services.ingestion.image_score_vl import score_images_batch
from services.ingestion.image_scorer import (
    ImageScoreResult,
    ScorableImage,
    _image_dimensions,
    compute_final_score,
    compute_media_bonuses,
    load_image_scoring_config,
    pick_auto_selected,
    prefilter_image,
    rank_evaluations,
)
from services.model_config.registry import get_active_vision_profile
from src.db.models.ingestion import (
    ArticleImage,
    ImageRelevanceEvaluation,
    IngestedArticle,
    StoryAsset,
)


def _load_keywords(article: IngestedArticle) -> list[str]:
    try:
        data = json.loads(article.keywords_json or "[]")
        return [str(x) for x in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def build_scorable_images(
    db: Session,
    article: IngestedArticle,
    *,
    include_story_images: bool = True,
) -> list[ScorableImage]:
    out: list[ScorableImage] = []
    seen_urls: set[str] = set()

    rows = (
        db.query(ArticleImage)
        .filter_by(article_id=article.id)
        .order_by(ArticleImage.sort_order)
        .all()
    )
    for row in rows:
        url = (row.original_url or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        out.append(
            ScorableImage(
                source_type="article_image",
                source_id=row.id,
                original_url=url,
                local_path=row.local_path,
                sort_order=row.sort_order,
                origin=row.origin or "article_body",
                download_status=row.download_status,
            )
        )

    if include_story_images and article.story_id:
        assets = (
            db.query(StoryAsset)
            .filter_by(story_id=article.story_id, asset_type="image", is_selected=True)
            .order_by(StoryAsset.sort_order)
            .all()
        )
        for asset in assets:
            if asset.source_article_id == article.id:
                continue
            try:
                payload = json.loads(asset.payload_json or "{}")
            except json.JSONDecodeError:
                continue
            url = str(payload.get("original_url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            out.append(
                ScorableImage(
                    source_type="story_asset",
                    source_id=asset.id,
                    original_url=url,
                    local_path=payload.get("local_path"),
                    sort_order=asset.sort_order,
                    origin="story_related",
                    download_status=str(payload.get("download_status") or "ok"),
                )
            )

    return out


def _has_fresh_cache(
    db: Session,
    article_id: str,
    scorer_version: str,
) -> bool:
    count = (
        db.query(ImageRelevanceEvaluation)
        .filter_by(article_id=article_id, scorer_version=scorer_version)
        .count()
    )
    return count > 0


def _load_cached_results(db: Session, article_id: str) -> list[ImageScoreResult]:
    rows = (
        db.query(ImageRelevanceEvaluation)
        .filter_by(article_id=article_id)
        .order_by(ImageRelevanceEvaluation.relevance_rank)
        .all()
    )
    results: list[ImageScoreResult] = []
    for row in rows:
        breakdown = None
        if row.breakdown_json:
            try:
                breakdown = json.loads(row.breakdown_json)
            except json.JSONDecodeError:
                breakdown = None
        results.append(
            ImageScoreResult(
                source_type=row.source_type,
                source_id=row.source_id,
                original_url=row.original_url,
                local_path=row.local_path,
                total=float(row.relevance_score or 0),
                grade=str(row.relevance_grade or "D"),
                relevance_rank=int(row.relevance_rank or 0),
                rank=int(row.relevance_rank or 0),
                caption=row.caption,
                verdict=row.verdict,
                breakdown=breakdown,
                is_animated=bool((breakdown or {}).get("is_animated")),
            )
        )
    return results


def _persist_evaluations(
    db: Session,
    article: IngestedArticle,
    results: list[ImageScoreResult],
    *,
    scorer_version: str,
    vision_profile_id: str | None,
) -> None:
    def _write() -> None:
        db.query(ImageRelevanceEvaluation).filter_by(article_id=article.id).delete()
        now = datetime.utcnow()
        for item in results:
            db.add(
                ImageRelevanceEvaluation(
                    article_id=article.id,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    original_url=item.original_url,
                    local_path=item.local_path,
                    relevance_score=item.total,
                    relevance_grade=item.grade,
                    relevance_rank=item.relevance_rank,
                    breakdown_json=json.dumps(item.breakdown, ensure_ascii=False)
                    if item.breakdown
                    else None,
                    caption=item.caption,
                    verdict=item.verdict,
                    vision_profile_id=vision_profile_id,
                    scorer_version=scorer_version,
                    scored_at=now,
                )
            )

        summary = {
            "grade_a": sum(1 for r in results if r.grade == "A"),
            "grade_b": sum(1 for r in results if r.grade == "B"),
            "grade_c": sum(1 for r in results if r.grade == "C"),
            "grade_d": sum(1 for r in results if r.grade == "D"),
        }
        article.images_scored_at = now
        article.images_score_summary_json = json.dumps(summary, ensure_ascii=False)
        db.flush()

    run_with_sqlite_retry(_write)


def _score_candidates(
    *,
    article_title: str,
    article_summary: str | None,
    keywords: list[str],
    content_excerpt: str,
    candidates: list[ScorableImage],
    cfg: dict[str, Any],
) -> tuple[list[ImageScoreResult], int, int]:
    """Return (results, vl_calls, skipped_count)."""
    vl_candidates: list[tuple[ScorableImage, Path, list[dict[str, Any]]]] = []
    results: list[ImageScoreResult] = []
    skipped = 0

    for image in candidates:
        local_file = Path(image.local_path) if image.local_path else None
        pre = prefilter_image(image, local_file=local_file, config=cfg)
        if pre.skip:
            skipped += 1
            continue
        if pre.skip_vl and pre.forced_grade:
            results.append(
                ImageScoreResult(
                    source_type=image.source_type,
                    source_id=image.source_id,
                    original_url=image.original_url,
                    local_path=image.local_path,
                    total=float(pre.forced_score or 20),
                    grade=pre.forced_grade,
                    sort_order=image.sort_order,
                    origin=image.origin,
                    breakdown={"prefilter": True, "penalties": pre.base_penalties},
                )
            )
            continue
        if local_file is None or not local_file.exists():
            skipped += 1
            continue
        vl_candidates.append((image, local_file, pre.base_penalties))

    vl_calls = 0
    if vl_candidates:
        batch_size = int((cfg.get("vl") or {}).get("batch_size", 4))
        excerpt = content_excerpt[
            : int((cfg.get("vl") or {}).get("content_excerpt_chars", 800))
        ]
        for start in range(0, len(vl_candidates), batch_size):
            chunk = vl_candidates[start : start + batch_size]
            batch_input = [(img.source_id, path) for img, path, _ in chunk]
            vl_payloads = score_images_batch(
                article_title=article_title,
                article_summary=article_summary,
                keywords=keywords,
                content_excerpt=excerpt,
                images=batch_input,
                config=cfg,
            )
            vl_calls += 1
            by_id = {str(p.get("source_id")): p for p in vl_payloads}
            for image, path, base_penalties in chunk:
                payload = by_id.get(image.source_id) or {
                    "source_id": image.source_id,
                    "dimensions": {},
                    "penalties": [],
                    "reject": True,
                    "reject_reason": "vl_missing_result",
                }
                img_w, img_h = _image_dimensions(path)
                media_bonuses = compute_media_bonuses(path, config=cfg)
                scored = compute_final_score(
                    payload,
                    extra_penalties=base_penalties,
                    extra_bonuses=media_bonuses,
                    width=img_w,
                    height=img_h,
                    config=cfg,
                )
                scored.is_animated = bool(media_bonuses) or bool(
                    (scored.breakdown or {}).get("is_animated")
                )
                scored.source_type = image.source_type
                scored.source_id = image.source_id
                scored.original_url = image.original_url
                scored.local_path = image.local_path
                scored.sort_order = image.sort_order
                scored.origin = image.origin
                results.append(scored)

    return results, vl_calls, skipped


def score_article_images(
    db: Session,
    article_id: str,
    *,
    force: bool = False,
    include_story_images: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    article = db.get(IngestedArticle, article_id)
    if article is None:
        raise ValueError(f"Article not found: {article_id}")

    cfg = load_image_scoring_config()
    scorer_version = str(cfg.get("scorer_version") or "1.0")
    vision_profile = get_active_vision_profile()
    vision_profile_id = str(vision_profile.get("id")) if vision_profile else None

    if not force and _has_fresh_cache(db, article_id, scorer_version):
        ranked = _load_cached_results(db, article_id)
        return _build_response(
            article_id=article_id,
            results=ranked,
            cfg=cfg,
            scored_count=len(ranked),
            skipped_count=0,
            vl_calls=0,
            duration_ms=int((time.perf_counter() - started) * 1000),
            vision_profile_id=vision_profile_id,
            scorer_version=scorer_version,
            from_cache=True,
        )

    candidates = build_scorable_images(db, article, include_story_images=include_story_images)
    article_id = article.id
    article_title = article.title or ""
    article_summary = article.summary
    keywords = _load_keywords(article)
    content_excerpt = article.content_text or article.summary or ""
    # Release SQLite read transaction before long-running VL API calls.
    db.commit()
    article = db.get(IngestedArticle, article_id)
    if article is None:
        raise ValueError(f"Article not found: {article_id}")

    results, vl_calls, skipped = _score_candidates(
        article_title=article_title,
        article_summary=article_summary,
        keywords=keywords,
        content_excerpt=content_excerpt,
        candidates=candidates,
        cfg=cfg,
    )
    ranked = rank_evaluations(results)
    _persist_evaluations(
        db,
        article,
        ranked,
        scorer_version=scorer_version,
        vision_profile_id=vision_profile_id,
    )
    db.commit()

    return _build_response(
        article_id=article_id,
        results=ranked,
        cfg=cfg,
        scored_count=len(ranked),
        skipped_count=skipped,
        vl_calls=vl_calls,
        duration_ms=int((time.perf_counter() - started) * 1000),
        vision_profile_id=vision_profile_id,
        scorer_version=scorer_version,
        from_cache=False,
    )


def _build_response(
    *,
    article_id: str,
    results: list[ImageScoreResult],
    cfg: dict[str, Any],
    scored_count: int,
    skipped_count: int,
    vl_calls: int,
    duration_ms: int,
    vision_profile_id: str | None,
    scorer_version: str,
    from_cache: bool,
) -> dict[str, Any]:
    auto_picked = pick_auto_selected(results, config=cfg)
    auto_ids = {item.source_id for item in auto_picked}
    images_out = []
    for item in results:
        payload = item.to_dict()
        payload["auto_selected"] = item.source_id in auto_ids
        images_out.append(payload)

    summary = {
        "grade_a": sum(1 for r in results if r.grade == "A"),
        "grade_b": sum(1 for r in results if r.grade == "B"),
        "grade_c": sum(1 for r in results if r.grade == "C"),
        "grade_d": sum(1 for r in results if r.grade == "D"),
        "auto_selected_ids": list(auto_ids),
    }
    return {
        "success": True,
        "article_id": article_id,
        "scored_count": scored_count,
        "skipped_count": skipped_count,
        "vl_calls": vl_calls,
        "duration_ms": duration_ms,
        "vision_profile_id": vision_profile_id,
        "scorer_version": scorer_version,
        "from_cache": from_cache,
        "images": images_out,
        "summary": summary,
    }
