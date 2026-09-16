"""Media pipeline eligibility and configuration."""
from __future__ import annotations

from typing import Any

from services.ingestion.article_scorer import grade_meets_minimum, load_scoring_config
from services.ingestion.render_templates import get_render_template

_FLAT_OVERRIDE_KEYS = (
    "skip_if_done",
    "score_images",
    "generate_content",
    "prepare_video",
    "render_video",
    "render_cover",
    "prepend_cover_intro",
    "include_story_images",
    "force_score_images",
    "select_top_by_rank",
    "max_selected_images",
    "random_bgm",
    "bgm_dir",
    "background_image",
    "clip_duration_sec",
    "cover_intro_frames",
    "cover_intro_duration_sec",
    "cover_width",
    "cover_height",
    "voiceover_min_chars",
    "voiceover_max_chars",
)


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def resolve_cover_intro_duration_sec(
    video: dict[str, Any] | None = None,
    canvas: dict[str, Any] | None = None,
    pipeline: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> float:
    """Cover intro length in seconds. ``cover_intro_frames`` wins over duration."""
    video = video or {}
    canvas = canvas or {}
    pipeline = pipeline or {}
    overrides = overrides or {}
    fps = float(overrides.get("fps") or canvas.get("fps") or 24)
    if fps <= 0:
        fps = 24.0
    frames = _first_present(
        overrides.get("cover_intro_frames"),
        pipeline.get("cover_intro_frames"),
        video.get("cover_intro_frames"),
    )
    if frames is not None:
        return max(1, int(frames)) / fps
    duration = _first_present(
        overrides.get("cover_intro_duration_sec"),
        pipeline.get("cover_intro_duration_sec"),
        video.get("cover_intro_duration_sec"),
    )
    if duration is not None:
        return float(duration)
    return 1.0 / fps


def _resolve_render_template(pipeline: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    requested = pipeline.get("render_template_id") or cfg.get("render_template_id")
    try:
        return get_render_template(requested)
    except ValueError:
        return get_render_template(None)


def load_media_pipeline_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    active = cfg or load_scoring_config()
    auto = active.get("post_score_automation") or {}
    pipeline = auto.get("media_pipeline") or {}
    trigger = pipeline.get("trigger") or {}
    template = _resolve_render_template(pipeline, active)
    video = template.get("video") or {}
    cover = template.get("cover") or {}
    canvas = template.get("canvas") or {}

    defaults = {
        "enabled": auto.get("enabled", True),
        "skip_if_done": auto.get("skip_if_done", True),
        "trigger": {
            "min_grade": trigger.get("min_grade", auto.get("min_grade", "S")),
            "min_score": float(trigger.get("min_score", 80)),
            "logic": trigger.get("logic", "or"),
        },
        "score_images": pipeline.get("score_images", auto.get("score_images", True)),
        "generate_content": pipeline.get("generate_content", auto.get("generate_content", True)),
        "prepare_video": pipeline.get("prepare_video", auto.get("prepare_video", True)),
        "render_video": pipeline.get("render_video", True),
        "include_story_images": pipeline.get(
            "include_story_images", auto.get("include_story_images", True)
        ),
        "max_selected_images": int(
            pipeline.get("max_selected_images") or video.get("max_selected_images") or 4
        ),
        "random_bgm": pipeline.get("random_bgm", video.get("random_bgm", True)),
        "bgm_dir": pipeline.get("bgm_dir") or video.get("bgm_dir") or "static/music",
        "background_image": (
            pipeline.get("background_image")
            or template.get("background_image")
            or "static/imgs/bg.png"
        ),
        "clip_duration_sec": float(
            pipeline.get("clip_duration_sec") or video.get("fallback_clip_sec") or 2.5
        ),
        "render_cover": pipeline.get("render_cover", cover.get("enabled", True)),
        "prepend_cover_intro": pipeline.get(
            "prepend_cover_intro", video.get("prepend_cover_intro", True)
        ),
        "cover_width": int(canvas.get("width") or cover.get("width") or 1080),
        "cover_height": int(canvas.get("height") or cover.get("height") or 1920),
        "render_template_id": template.get("id"),
        "layout_kind": template.get("layout_kind"),
        "render_template": template,
        "voiceover_min_chars": int(
            pipeline.get("voiceover_min_chars", auto.get("voiceover_min_chars", 40))
        ),
        "voiceover_max_chars": int(
            pipeline.get("voiceover_max_chars", auto.get("voiceover_max_chars", 90))
        ),
    }
    if cfg:
        for key in _FLAT_OVERRIDE_KEYS:
            if key in cfg:
                defaults[key] = cfg[key]
    defaults["cover_intro_duration_sec"] = resolve_cover_intro_duration_sec(
        video=video,
        canvas=canvas,
        pipeline=pipeline,
        overrides=cfg if cfg else {},
    )
    return defaults


def should_run_media_pipeline(
    *,
    final_grade: str,
    final_total: float,
    config: dict[str, Any] | None = None,
) -> bool:
    cfg = load_media_pipeline_config(config)
    if not cfg.get("enabled", True):
        return False
    trigger = cfg.get("trigger") or {}
    min_grade = str(trigger.get("min_grade", "S")).upper()
    min_score = float(trigger.get("min_score", 80))
    grade_ok = grade_meets_minimum(final_grade, min_grade)
    score_ok = float(final_total or 0) >= min_score
    logic = str(trigger.get("logic", "or")).lower()
    if logic == "and":
        return grade_ok and score_ok
    return grade_ok or score_ok


def build_manual_media_retry_config(
    *,
    include_story_images: bool,
    has_video_draft: bool,
    force_score_images: bool = False,
) -> dict[str, Any]:
    """Pipeline overrides for manual「重新出片」from the ingestion library."""
    return {
        "skip_if_done": False,
        "include_story_images": include_story_images,
        "force_score_images": bool(force_score_images),
        "select_top_by_rank": include_story_images,
        "generate_content": not has_video_draft,
    }
