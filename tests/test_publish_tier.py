"""Tests for publish tier shadow-mode computation (Phase 1a)."""
from __future__ import annotations

from services.ingestion.publish_tier import compute_publish_tier


def _cfg() -> dict:
    return {
        "publish_tier": {
            "viral_min_grade": "A",
            "industry_min_grade": "S",
            "industry_standard_grade": "A",
            "viral_low_grade": "B",
            "skip_industry_grade": "B",
            "skip_viral_grade": "C",
        }
    }


def test_viral_priority_when_viral_a_and_hook_passed():
    tier = compute_publish_tier(
        industry_grade="A",
        industry_total=84.0,
        viral_grade="A",
        hook_gate_passed=True,
        config=_cfg(),
    )
    assert tier == "viral_priority"


def test_industry_priority_when_s_grade_but_low_viral():
    tier = compute_publish_tier(
        industry_grade="S",
        industry_total=90.0,
        viral_grade="C",
        hook_gate_passed=True,
        config=_cfg(),
    )
    assert tier == "industry_priority"


def test_standard_for_a_grade():
    tier = compute_publish_tier(
        industry_grade="A",
        industry_total=75.0,
        viral_grade="B",
        hook_gate_passed=False,
        config=_cfg(),
    )
    assert tier == "standard"


def test_standard_for_high_score_even_if_b_grade():
    tier = compute_publish_tier(
        industry_grade="B",
        industry_total=82.0,
        viral_grade="C",
        hook_gate_passed=False,
        config=_cfg(),
    )
    assert tier == "standard"


def test_skip_for_low_both():
    tier = compute_publish_tier(
        industry_grade="C",
        industry_total=45.0,
        viral_grade="D",
        hook_gate_passed=False,
        config=_cfg(),
    )
    assert tier == "skip"
