"""Tests for score service LLM grade adjustment."""
from datetime import datetime, timedelta

from services.ingestion.score_service import _apply_llm_adjustment


def test_llm_downgrades_overrated_article():
    cfg = {"grades": {"S": 85, "A": 70, "B": 55, "C": 40}}
    total, grade, adjusted = _apply_llm_adjustment(
        88.0,
        "S",
        {
            "adjusted_grade": "B",
            "adjusted_score": 62,
            "grade_adjust_reason": "旧闻翻炒",
        },
        cfg,
    )
    assert adjusted is True
    assert grade == "B"
    assert total == 62


def test_llm_keeps_rule_when_same_grade():
    cfg = {"grades": {"S": 85, "A": 70, "B": 55, "C": 40}}
    total, grade, adjusted = _apply_llm_adjustment(
        82.0,
        "A",
        {
            "adjusted_grade": "A",
            "adjusted_score": 82,
            "grade_adjust_reason": "维持规则评级",
        },
        cfg,
    )
    assert grade == "A"
    assert total == 82
    assert adjusted is False
