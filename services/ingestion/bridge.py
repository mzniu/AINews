"""Bridge ingested articles to legacy fetch-url metadata shape."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from services.ingestion.image_dedupe import dedupe_image_entries, normalize_image_url
from services.ingestion.image_scorer import ImageScoreResult, load_image_scoring_config, pick_auto_selected
from src.db.models.ingestion import ArticleImage, ImageRelevanceEvaluation, IngestedArticle, StoryAsset


def _evaluation_extra_fields(evaluation: ImageRelevanceEvaluation | None) -> dict:
    if evaluation is None or not evaluation.breakdown_json:
        return {}
    try:
        breakdown = json.loads(evaluation.breakdown_json)
    except json.JSONDecodeError:
        return {}
    dims = breakdown.get("dimensions") or {}
    cover = dims.get("cover_fit") or {}
    figure = dims.get("figure_prominence") or {}
    flash = dims.get("flash_fit") or {}
    width = int(breakdown.get("width") or 0)
    height = int(breakdown.get("height") or 0)
    orientation = None
    if width > 0 and height > 0:
        ratio = width / height
        if ratio >= 1.25:
            orientation = "landscape"
        elif ratio <= 1.0:
            orientation = "portrait"
        else:
            orientation = "square"
    return {
        "cover_fit_score": cover.get("score"),
        "figure_prominence_score": figure.get("score"),
        "flash_fit_score": flash.get("score"),
        "orientation": orientation,
        "width": width or None,
        "height": height or None,
        "is_animated": bool(breakdown.get("is_animated")),
    }


def _resolve_content_description(evaluation: ImageRelevanceEvaluation | None) -> str | None:
    if evaluation is None:
        return None
    if evaluation.content_description:
        return evaluation.content_description.strip()
    if evaluation.caption:
        return evaluation.caption.strip()
    if evaluation.breakdown_json:
        try:
            breakdown = json.loads(evaluation.breakdown_json)
            value = breakdown.get("content_description") or breakdown.get("caption")
            return str(value).strip() if value else None
        except json.JSONDecodeError:
            return None
    return None


def _evaluation_snapshot(evaluation: ImageRelevanceEvaluation | None) -> dict | None:
    if evaluation is None:
        return None
    breakdown = None
    if evaluation.breakdown_json:
        try:
            breakdown = json.loads(evaluation.breakdown_json)
        except json.JSONDecodeError:
            breakdown = None
    return {
        "source_type": evaluation.source_type,
        "source_id": evaluation.source_id,
        "relevance_score": evaluation.relevance_score,
        "relevance_grade": evaluation.relevance_grade,
        "relevance_rank": evaluation.relevance_rank,
        "caption": evaluation.caption,
        "content_description": _resolve_content_description(evaluation),
        "verdict": evaluation.verdict,
        "breakdown": breakdown,
        "scored_at": evaluation.scored_at.isoformat() if evaluation.scored_at else None,
        "scorer_version": evaluation.scorer_version,
        "vision_profile_id": evaluation.vision_profile_id,
    }


def _image_entry(
    url: str,
    local_path: str | None,
    *,
    source: str = "article",
    source_type: str | None = None,
    source_id: str | None = None,
    evaluation: ImageRelevanceEvaluation | None = None,
    auto_selected: bool = False,
) -> dict:
    entry = {
        "url": url,
        "local_path": f"/{local_path.lstrip('/')}" if local_path else None,
        "success": bool(local_path),
        "source": source,
        "auto_selected": auto_selected,
    }
    if source_type:
        entry["source_type"] = source_type
    if source_id:
        entry["source_id"] = source_id
    if evaluation is not None:
        content_description = _resolve_content_description(evaluation)
        entry.update(
            {
                "source_type": evaluation.source_type,
                "source_id": evaluation.source_id,
                "relevance_score": evaluation.relevance_score,
                "relevance_grade": evaluation.relevance_grade,
                "relevance_rank": evaluation.relevance_rank,
                "caption": evaluation.caption,
                "content_description": content_description,
                "verdict": evaluation.verdict,
                "evaluation": _evaluation_snapshot(evaluation),
                **_evaluation_extra_fields(evaluation),
            }
        )
    return entry


def _load_evaluations(session: Session, article_id: str) -> dict[tuple[str, str], ImageRelevanceEvaluation]:
    rows = session.query(ImageRelevanceEvaluation).filter_by(article_id=article_id).all()
    return {(row.source_type, row.source_id): row for row in rows}


def _article_images(
    session: Session,
    article_id: str,
    evaluations: dict[tuple[str, str], ImageRelevanceEvaluation],
) -> list[dict]:
    rows = (
        session.query(ArticleImage)
        .filter_by(article_id=article_id)
        .order_by(ArticleImage.sort_order)
        .all()
    )
    images: list[dict] = []
    seen_urls: set[str] = set()
    for img in rows:
        url = str(img.original_url or "").strip()
        norm_url = normalize_image_url(url)
        if norm_url and norm_url in seen_urls:
            continue
        if norm_url:
            seen_urls.add(norm_url)
        images.append(
            _image_entry(
                url,
                img.local_path,
                source="article",
                source_type="article_image",
                source_id=img.id,
                evaluation=evaluations.get(("article_image", img.id)),
            )
        )
    return images


def _story_merged_images(
    session: Session,
    story_id: str,
    *,
    exclude_article_id: str,
    evaluations: dict[tuple[str, str], ImageRelevanceEvaluation],
) -> list[dict]:
    assets = (
        session.query(StoryAsset)
        .filter_by(story_id=story_id, asset_type="image", is_selected=True)
        .order_by(StoryAsset.sort_order)
        .all()
    )
    merged: list[dict] = []
    seen_urls: set[str] = set()
    for asset in assets:
        if asset.source_article_id == exclude_article_id:
            continue
        try:
            payload = json.loads(asset.payload_json or "{}")
        except json.JSONDecodeError:
            continue
        url = str(payload.get("original_url") or "").strip()
        norm_url = normalize_image_url(url)
        if not norm_url or norm_url in seen_urls:
            continue
        seen_urls.add(norm_url)
        merged.append(
            _image_entry(
                url,
                payload.get("local_path"),
                source="story_related",
                source_type="story_asset",
                source_id=asset.id,
                evaluation=evaluations.get(("story_asset", asset.id)),
            )
        )
    return merged


def _sort_images_by_relevance(images: list[dict]) -> list[dict]:
    def sort_key(item: dict) -> tuple:
        rank = item.get("relevance_rank")
        score = item.get("relevance_score")
        return (
            0 if rank is not None else 1,
            rank if rank is not None else 9999,
            -(score if score is not None else -1),
        )

    return sorted(images, key=sort_key)


def _image_entries_to_results(images: list[dict]) -> list[ImageScoreResult]:
    results: list[ImageScoreResult] = []
    for item in images:
        source_id = str(item.get("source_id") or "").strip()
        if not source_id or not item.get("local_path"):
            continue
        results.append(
            ImageScoreResult(
                source_type=str(item.get("source_type") or "article_image"),
                source_id=source_id,
                original_url=str(item.get("url") or ""),
                local_path=str(item.get("local_path") or ""),
                total=float(item.get("relevance_score") or 0),
                grade=str(item.get("relevance_grade") or "D"),
                relevance_rank=int(item.get("relevance_rank") or 0),
                rank=int(item.get("relevance_rank") or 0),
            )
        )
    return results


def prepare_video_metadata(
    session: Session,
    article_id: str,
    *,
    include_story_images: bool = True,
    sort_by_relevance: bool = True,
    auto_select: bool = True,
) -> dict:
    article = session.get(IngestedArticle, article_id)
    if article is None:
        raise ValueError("Article not found")

    evaluations = _load_evaluations(session, article_id)
    image_paths = _article_images(session, article_id, evaluations)
    story_images: list[dict] = []
    if include_story_images and article.story_id:
        story_images = _story_merged_images(
            session,
            article.story_id,
            exclude_article_id=article.id,
            evaluations=evaluations,
        )
        image_paths = image_paths + story_images

    image_paths = dedupe_image_entries(image_paths, config=load_image_scoring_config())

    auto_selected_images: list[dict] = []
    if auto_select and evaluations:
        cfg = load_image_scoring_config()
        picked = pick_auto_selected(_image_entries_to_results(image_paths), config=cfg)
        auto_ids = {(p.source_type, p.source_id) for p in picked}
        for item in image_paths:
            key = (item.get("source_type"), item.get("source_id"))
            if key in auto_ids:
                item["auto_selected"] = True
                auto_selected_images.append(item)

    if sort_by_relevance and evaluations:
        image_paths = _sort_images_by_relevance(image_paths)

    content_preview = (article.content_text or article.summary or "")[:500]
    video_draft = None
    if article.video_draft_json:
        try:
            video_draft = json.loads(article.video_draft_json)
        except json.JSONDecodeError:
            video_draft = None

    metadata = {
        "url": article.canonical_url,
        "title": article.title,
        "source_id": article.source_id,
        "summary": article.summary,
        "theme": article.theme,
        "content_preview": content_preview,
        "images_count": len(image_paths),
        "images": image_paths,
        "auto_selected_images": auto_selected_images,
        "ingested_article_id": article.id,
        "story_id": article.story_id,
        "story_merged_image_count": len(story_images),
        "images_scored_at": article.images_scored_at.isoformat()
        if article.images_scored_at
        else None,
        "image_scores_available": bool(evaluations),
        "video_draft": video_draft,
        "video_draft_generated_at": article.video_draft_generated_at.isoformat()
        if article.video_draft_generated_at
        else None,
        "video_prep_at": article.video_prep_at.isoformat() if article.video_prep_at else None,
    }
    base_dir = Path("data/ingested") / article.source_id / article.id
    base_dir.mkdir(parents=True, exist_ok=True)
    meta_path = base_dir / "prepare_video_metadata.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "article_id": article.id,
        "metadata": metadata,
        "metadata_path": f"/{meta_path.as_posix()}",
        "content": article.content_text or article.summary or "",
        "title": article.title,
        "images": image_paths,
        "auto_selected_images": auto_selected_images,
        "story_id": article.story_id,
        "story_merged_images": story_images,
        "video_draft": video_draft,
        "generated_video_path": article.generated_video_path,
        "generated_cover_path": article.generated_cover_path,
        "generated_video_at": article.generated_video_at.isoformat()
        if article.generated_video_at
        else None,
        "selected_bgm_path": article.selected_bgm_path,
        "media_pipeline_status": article.media_pipeline_status,
        "generated_cover_path": article.generated_cover_path,
    }
