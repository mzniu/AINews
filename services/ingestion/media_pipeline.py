"""Execute media pipeline: image scoring, AI copy, prepare-video, render video."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from services.content_generation_service import generate_video_content
from services.copy_agent.drafts import draft_selectable, generate_one_draft
from services.copy_agent.settings_store import get_settings
from src.db.models.playbook import PlaybookVersion
from services.ingestion.bgm_picker import pick_random_bgm
from services.ingestion.cover_picker import pick_best_cover_image
from services.ingestion.cover_render_service import render_article_cover
from services.ingestion.cover_video_utils import prepend_cover_intro_to_video
from services.ingestion.bridge import (
    dedupe_image_entries,
    prepare_video_metadata,
    sort_images_by_relevance,
    supplement_story_images,
)
from services.ingestion.image_scorer import load_image_scoring_config
from services.ingestion.image_score_service import score_article_images
from services.ingestion.media_pipeline_trigger import load_media_pipeline_config
from services.ingestion.render_image_utils import filter_renderable_image_dicts
from services.ingestion.video_render_service import render_ingested_video, resolve_ingested_clip_durations
from services.ingestion.media_paths import restore_generated_media_paths
from services.ingestion.watermark_clean import clean_images_for_render
from src.db.models.ingestion import IngestedArticle
from src.utils.paths import to_data_url_path
from utils.title_units import resolve_short_title, truncate_han_equiv, MAIN_LINE1_MAX_UNITS


def _normalize_local_path(path: str | None) -> str:
    return to_data_url_path(path)


def _checkpoint(session: Session) -> None:
    """Commit progress so long-running steps do not hold SQLite write locks."""
    session.commit()


def _parse_existing_draft(article: IngestedArticle) -> dict[str, Any] | None:
    raw = article.video_draft_json
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and (data.get("main_line1") or data.get("title")):
        return data
    return None


def _fallback_draft(article: IngestedArticle) -> dict[str, Any]:
    title = (article.title or "未命名").strip()
    main_line1 = truncate_han_equiv(title, MAIN_LINE1_MAX_UNITS)
    return {
        "main_line1": main_line1,
        "short_title": resolve_short_title("", main_line1),
        "main_line2": "",
        "sub_title": "",
        "sub_title2": "",
        "summary": ((article.summary or title)[:80]),
        "tags": "",
        "highlight_keywords": [],
        "fallback": True,
    }


def playbook_rerender_config() -> dict[str, Any]:
    """Force a new copy. Does not change the manual retry helper."""
    return {
        "skip_if_done": False,
        "post_score_automation": {
            "media_pipeline": {
                "generate_content": True,
            }
        },
    }


def _current_auto_playbook(session: Session) -> PlaybookVersion | None:
    settings = get_settings(session)
    if not settings.auto_uses_current_playbook or not settings.current_playbook_version_id:
        return None
    version = session.get(PlaybookVersion, settings.current_playbook_version_id)
    if version is None or not (version.body or "").strip():
        return None
    return version


def _draft_selection_extras(copy) -> dict[str, Any]:
    try:
        sel = json.loads(copy.selection_json or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(sel, dict):
        return {}
    out: dict[str, Any] = {}
    if sel.get("cluster_key"):
        out["pattern_cluster_key"] = sel["cluster_key"]
    if sel.get("pattern_name"):
        out["pattern_name"] = sel["pattern_name"]
    if sel.get("confidence"):
        out["playbook_selection_confidence"] = sel["confidence"]
    if sel.get("reason"):
        out["playbook_selection_reason"] = sel["reason"]
    if "fallback" in sel:
        out["playbook_selection_fallback"] = bool(sel.get("fallback"))
    return out


def _mark_attribution(
    draft: dict[str, Any],
    attribution: str,
    *,
    version_id: str | None = None,
    copy_draft_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    draft["playbook_attribution"] = attribution
    draft["playbook_version_id"] = version_id
    draft["copy_draft_id"] = copy_draft_id
    if extra:
        draft.update(extra)
    return draft


def _generate_pipeline_draft(
    session: Session,
    article: IngestedArticle,
    content_text: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    common = {
        "title": article.title or "",
        "content": content_text,
        "voiceover_min_chars": int(cfg.get("voiceover_min_chars", 40)),
        "voiceover_max_chars": int(cfg.get("voiceover_max_chars", 90)),
    }
    version = _current_auto_playbook(session)
    if version is None:
        return generate_video_content(**common)

    def complete(_messages: list[dict]) -> str:
        produced = generate_video_content(**common, playbook_body=version.body)
        return json.dumps(produced, ensure_ascii=False)

    from services.copy_agent.pattern_ranking import production_rank_complete

    copy = generate_one_draft(
        session,
        title=common["title"],
        content=content_text,
        complete=complete,
        complete_rank=production_rank_complete,
        for_auto_pipeline=True,
        voiceover_min_chars=common["voiceover_min_chars"],
        voiceover_max_chars=common["voiceover_max_chars"],
    )
    if draft_selectable(copy):
        payload = json.loads(json.loads(copy.body_json)["text"])
        if not isinstance(payload, dict):
            raise ValueError("打法稿不是对象")
        extra = _draft_selection_extras(copy)
        return _mark_attribution(
            payload,
            "playbook",
            version_id=copy.playbook_version_id,
            copy_draft_id=copy.id,
            extra=extra,
        )
    fallback = generate_video_content(**common)
    return _mark_attribution(fallback, "fact_gate_fallback")


def run_media_pipeline(
    session: Session,
    article_id: str,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    article = session.get(IngestedArticle, article_id)
    if article is None:
        raise ValueError(f"Article not found: {article_id}")

    cfg = load_media_pipeline_config(config)
    article.media_pipeline_status = "running"
    session.flush()
    _checkpoint(session)

    started = datetime.utcnow()
    steps: dict[str, Any] = {}
    errors: list[str] = []
    draft: dict[str, Any] | None = None
    selected_images: list[dict[str, Any]] = []
    bgm_path: str | None = None
    video_path: str | None = None
    cover_path: str | None = None

    if cfg.get("score_images", True):
        try:
            img_result = score_article_images(
                session,
                article.id,
                force=bool(cfg.get("force_score_images", False)),
                include_story_images=bool(cfg.get("include_story_images", True)),
            )
            steps["score_images"] = {
                "scored_count": img_result.get("scored_count"),
                "from_cache": img_result.get("from_cache"),
            }
        except Exception as exc:
            logger.warning(f"media_pipeline score_images failed: {exc}")
            errors.append(f"score_images: {exc}")
            steps["score_images"] = {"error": str(exc)}
        else:
            _checkpoint(session)

    if cfg.get("generate_content", True):
        trying_playbook = _current_auto_playbook(session) is not None
        try:
            content_text = article.content_text or article.summary or ""
            if not content_text.strip():
                raise ValueError("文章无正文")
            draft = _generate_pipeline_draft(session, article, content_text, cfg)
            article.video_draft_json = json.dumps(draft, ensure_ascii=False)
            article.video_draft_generated_at = datetime.utcnow()
            steps["generate_content"] = {"model": draft.get("model")}
        except Exception as exc:
            logger.warning(f"media_pipeline generate_content failed: {exc}")
            errors.append(f"generate_content: {exc}")
            steps["generate_content"] = {"error": str(exc)}
            draft = _parse_existing_draft(article)
            if draft:
                steps["generate_content"]["reused_existing_draft"] = True
            else:
                draft = _fallback_draft(article)
                steps["generate_content"]["used_fallback_draft"] = True
            if trying_playbook and draft is not None:
                _mark_attribution(draft, "generation_fallback")
                article.video_draft_json = json.dumps(draft, ensure_ascii=False)
        else:
            _checkpoint(session)
    else:
        draft = _parse_existing_draft(article)
        if draft:
            steps["generate_content"] = {"skipped": True, "reused_existing_draft": True}

    if cfg.get("prepare_video", True):
        try:
            prep = prepare_video_metadata(
                session,
                article.id,
                include_story_images=bool(cfg.get("include_story_images", True)),
                sort_by_relevance=True,
                auto_select=True,
            )
            max_n = int(cfg.get("max_selected_images", 4))
            min_renderable = min(int(cfg.get("min_selected_images", 3)), max_n)
            pool = dedupe_image_entries(
                prep.get("images") or [],
                config=load_image_scoring_config(),
            )
            if cfg.get("select_top_by_rank"):
                candidates = [
                    img
                    for img in pool
                    if img.get("local_path") and img.get("success", True)
                ]
            else:
                candidates = dedupe_image_entries(
                    prep.get("auto_selected_images") or [],
                    config=load_image_scoring_config(),
                )
            selected_images = sort_images_by_relevance(
                filter_renderable_image_dicts(candidates)
            )[:max_n]
            if len(selected_images) < min_renderable:
                supplemented, added = supplement_story_images(
                    session,
                    article,
                    pool,
                    include_story_images=bool(cfg.get("include_story_images", True)),
                    min_renderable=min_renderable,
                )
                if added:
                    pool = supplemented
                if cfg.get("select_top_by_rank"):
                    candidates = [
                        img
                        for img in pool
                        if img.get("local_path") and img.get("success", True)
                    ]
                else:
                    candidates = dedupe_image_entries(
                        prep.get("auto_selected_images") or pool,
                        config=load_image_scoring_config(),
                    )
                selected_images = sort_images_by_relevance(
                    filter_renderable_image_dicts(candidates)
                )[:max_n]
            steps["prepare_video"] = {
                "auto_selected_count": len(selected_images),
                "selection_mode": "top_rank" if cfg.get("select_top_by_rank") else "auto_grade_by_rank",
                "metadata_path": prep.get("metadata_path"),
                "renderable_count": len(selected_images),
            }
            article.selected_images_json = json.dumps(selected_images, ensure_ascii=False)
        except Exception as exc:
            logger.warning(f"media_pipeline prepare_video failed: {exc}")
            errors.append(f"prepare_video: {exc}")
            steps["prepare_video"] = {"error": str(exc)}
        else:
            _checkpoint(session)

    cover_source = None
    if cfg.get("render_cover", True):
        try:
            cover_source = pick_best_cover_image(session, article.id)
        except Exception as exc:
            logger.warning(f"media_pipeline pick cover before clean failed: {exc}")

    clean_map: dict[str, Any] = {}
    try:
        pending_paths: list[str] = []
        seen_pending: set[str] = set()
        for img in selected_images:
            path = _normalize_local_path(img.get("local_path"))
            if path and path not in seen_pending:
                seen_pending.add(path)
                pending_paths.append(path)
        cover_local = _normalize_local_path((cover_source or {}).get("local_path"))
        if cover_local and cover_local not in seen_pending:
            pending_paths.append(cover_local)
        clean_map = clean_images_for_render(
            pending_paths,
            enabled=bool(cfg.get("auto_remove_watermark", True)),
        )
        for img in selected_images:
            key = _normalize_local_path(img.get("local_path"))
            cleaned = clean_map.get(key)
            if cleaned is None:
                continue
            img["cleaned_path"] = cleaned.cleaned_path
            img["watermark_clean"] = {
                "status": cleaned.status,
                "reason": cleaned.reason,
                "regions": [
                    {
                        "x": region.x,
                        "y": region.y,
                        "width": region.width,
                        "height": region.height,
                        "kind": region.kind,
                    }
                    for region in cleaned.regions
                ],
            }
        if selected_images:
            article.selected_images_json = json.dumps(selected_images, ensure_ascii=False)
        steps["clean_watermarks"] = {
            key: {"status": item.status, "reason": item.reason}
            for key, item in clean_map.items()
        }
    except Exception as exc:
        logger.warning(f"media_pipeline clean_watermarks failed: {exc}")
        steps["clean_watermarks"] = {"error": str(exc)}

    seen_render_paths: set[str] = set()
    image_paths: list[str] = []
    for img in selected_images:
        original = _normalize_local_path(img.get("local_path"))
        cleaned = clean_map.get(original)
        path = cleaned.path if cleaned is not None else original
        if not path or path in seen_render_paths:
            continue
        seen_render_paths.add(path)
        image_paths.append(path)

    if cfg.get("render_video", True) and draft and image_paths:
        if cfg.get("random_bgm", True):
            bgm_path = pick_random_bgm(cfg.get("bgm_dir", "static/music"))
            article.selected_bgm_path = bgm_path
        try:
            render_result = render_ingested_video(
                article_id=article.id,
                draft=draft,
                image_paths=image_paths,
                bgm_path=bgm_path or "static/music/background.mp3",
                background_image=str(cfg.get("background_image", "static/imgs/bg.png")),
                clip_duration_sec=float(cfg.get("clip_duration_sec", 2.5)),
                template=cfg.get("render_template"),
            )
            if render_result.get("success"):
                video_path = render_result.get("video_path")
                article.generated_video_path = video_path
                article.generated_video_at = datetime.utcnow()
                steps["render_video"] = {
                    "video_path": video_path,
                    "duration": render_result.get("duration"),
                    "clip_durations": resolve_ingested_clip_durations(len(image_paths)),
                    "image_count": len(image_paths),
                }
            else:
                errors.append(f"render_video: {render_result.get('error')}")
                steps["render_video"] = render_result
        except Exception as exc:
            logger.warning(f"media_pipeline render_video failed: {exc}")
            errors.append(f"render_video: {exc}")
            steps["render_video"] = {"error": str(exc)}
        else:
            _checkpoint(session)
    elif cfg.get("render_video", True):
        reason = "missing_draft" if not draft else "missing_images"
        errors.append(f"render_video: skipped ({reason})")
        steps["render_video"] = {
            "skipped": True,
            "image_count": len(image_paths),
            "reason": reason,
        }

    if cfg.get("render_cover", True) and draft:
        try:
            if cover_source:
                cover_key = _normalize_local_path(cover_source.get("local_path"))
                cleaned_cover = clean_map.get(cover_key)
                cover_image_path = (
                    cleaned_cover.path
                    if cleaned_cover is not None
                    else cover_source["local_path"]
                )
                cover_result = render_article_cover(
                    article_id=article.id,
                    draft=draft,
                    image_path=cover_image_path,
                    background_image=str(cfg.get("background_image", "static/imgs/bg.png")),
                    width=int(cfg.get("cover_width", 1080)),
                    height=int(cfg.get("cover_height", 1920)),
                    template=cfg.get("render_template"),
                )
                if cover_result.get("success"):
                    cover_path = cover_result.get("cover_path")
                    article.generated_cover_path = cover_path
                    steps["render_cover"] = cover_result
                else:
                    errors.append(f"render_cover: {cover_result.get('error')}")
                    steps["render_cover"] = cover_result
            else:
                steps["render_cover"] = {"skipped": True, "reason": "no_scored_cover_image"}
        except Exception as exc:
            logger.warning(f"media_pipeline render_cover failed: {exc}")
            errors.append(f"render_cover: {exc}")
            steps["render_cover"] = {"error": str(exc)}
        else:
            _checkpoint(session)

    if (
        cfg.get("prepend_cover_intro", True)
        and video_path
        and cover_path
    ):
        try:
            intro_result = prepend_cover_intro_to_video(
                video_path=video_path,
                cover_path=cover_path,
                intro_duration=float(cfg.get("cover_intro_duration_sec", 1.0 / 24)),
            )
            if intro_result.get("success"):
                video_path = str(intro_result.get("video_path") or video_path)
                article.generated_video_path = video_path
                steps["prepend_cover_intro"] = intro_result
            else:
                errors.append(f"prepend_cover_intro: {intro_result.get('error')}")
                steps["prepend_cover_intro"] = intro_result
        except Exception as exc:
            logger.warning(f"media_pipeline prepend_cover_intro failed: {exc}")
            errors.append(f"prepend_cover_intro: {exc}")
            steps["prepend_cover_intro"] = {"error": str(exc)}

    if video_path:
        article.generated_video_path = video_path
        if article.generated_video_at is None:
            article.generated_video_at = datetime.utcnow()
    if cover_path:
        article.generated_cover_path = cover_path

    video_ok = bool(video_path)
    partial_ok = bool(draft) and not video_ok
    success = video_ok or (partial_ok and not errors)

    status_payload = {
        "success": success,
        "video_rendered": video_ok,
        "started_at": started.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
        "steps": steps,
        "errors": errors,
        "render_template_id": cfg.get("render_template_id"),
        "layout_kind": cfg.get("layout_kind"),
        "canvas": (cfg.get("render_template") or {}).get("canvas"),
        "default_template_id": cfg.get("render_template_id"),
    }
    article.video_prep_status_json = json.dumps(status_payload, ensure_ascii=False)
    restore_generated_media_paths(article)
    if video_ok:
        article.video_prep_at = datetime.utcnow()
        article.media_pipeline_status = "succeeded"
        try:
            from services.publishing.auto_publish import maybe_enqueue_auto_publish_jobs

            auto_publish = maybe_enqueue_auto_publish_jobs(session, article)
            status_payload["auto_publish"] = auto_publish
        except Exception as exc:
            logger.exception(f"auto_publish failed article={article.id}: {exc}")
            status_payload["auto_publish"] = {"success": False, "error": str(exc)}
    elif partial_ok:
        article.media_pipeline_status = "failed"
    else:
        article.media_pipeline_status = "failed"

    session.flush()
    return status_payload
