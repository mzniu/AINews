"""Publish tier computation for shadow-mode automation (Phase 1a)."""
from __future__ import annotations

from typing import Any

from services.ingestion.article_scorer import GRADE_RANK, VALID_GRADES


def _grade_rank(grade: str | None) -> int:
    current = str(grade or "").strip().upper()
    return GRADE_RANK.get(current, 0)


def _meets(grade: str | None, min_grade: str) -> bool:
    current = str(grade or "").strip().upper()
    minimum = str(min_grade or "S").strip().upper()
    if current not in VALID_GRADES or minimum not in VALID_GRADES:
        return False
    return _grade_rank(current) >= _grade_rank(minimum)


def load_publish_tier_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from services.ingestion.article_scorer import load_scoring_config

    active = cfg or load_scoring_config()
    defaults = {
        "viral_min_grade": "A",
        "industry_min_grade": "S",
        "industry_standard_grade": "A",
        "viral_low_grade": "B",
        "skip_industry_grade": "B",
        "skip_viral_grade": "C",
        "standard_min_score": 80.0,
    }
    tier_cfg = active.get("publish_tier") or {}
    return {**defaults, **tier_cfg}


def compute_publish_tier(
    *,
    industry_grade: str,
    industry_total: float,
    viral_grade: str,
    hook_gate_passed: bool,
    config: dict[str, Any] | None = None,
) -> str:
    """Return publish tier label (shadow mode — not used for gating in Phase 1a)."""
    tier_cfg = load_publish_tier_config(config)

    if (
        not _meets(industry_grade, tier_cfg["skip_industry_grade"])
        and not _meets(viral_grade, tier_cfg["skip_viral_grade"])
    ):
        return "skip"

    if _meets(viral_grade, tier_cfg["viral_min_grade"]) and hook_gate_passed:
        return "viral_priority"

    if _meets(industry_grade, tier_cfg["industry_min_grade"]) and not _meets(
        viral_grade, tier_cfg["viral_low_grade"]
    ):
        return "industry_priority"

    if _meets(industry_grade, tier_cfg["industry_standard_grade"]):
        return "standard"

    if float(industry_total or 0) >= float(tier_cfg.get("standard_min_score", 80.0)):
        return "standard"

    if _meets(viral_grade, tier_cfg["viral_low_grade"]):
        return "standard"

    return "skip"
