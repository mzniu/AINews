"""Media pipeline eligibility and configuration."""
from __future__ import annotations

from typing import Any

from services.ingestion.article_scorer import load_scoring_config


def load_media_pipeline_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    active = cfg or load_scoring_config()
    auto = active.get("post_score_automation") or {}
    pipeline = auto.get("media_pipeline") or {}
    trigger = pipeline.get("trigger") or {}

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
        "max_selected_images": int(pipeline.get("max_selected_images", 4)),
        "random_bgm": pipeline.get("random_bgm", True),
        "bgm_dir": pipeline.get("bgm_dir", "static/music"),
        "background_image": pipeline.get("background_image", "static/imgs/bg.png"),
        "clip_duration_sec": float(pipeline.get("clip_duration_sec", 2.5)),
        "render_cover": pipeline.get("render_cover", True),
        "prepend_cover_intro": pipeline.get("prepend_cover_intro", True),
        "cover_intro_duration_sec": float(pipeline.get("cover_intro_duration_sec", 1.0)),
        "cover_width": int(pipeline.get("cover_width", 1080)),
        "cover_height": int(pipeline.get("cover_height", 1440)),
        "voiceover_min_chars": int(
            pipeline.get("voiceover_min_chars", auto.get("voiceover_min_chars", 40))
        ),
        "voiceover_max_chars": int(
            pipeline.get("voiceover_max_chars", auto.get("voiceover_max_chars", 90))
        ),
    }
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
    grade_ok = str(final_grade or "").upper() == min_grade
    score_ok = float(final_total or 0) >= min_score
    logic = str(trigger.get("logic", "or")).lower()
    if logic == "and":
        return grade_ok and score_ok
    return grade_ok or score_ok
