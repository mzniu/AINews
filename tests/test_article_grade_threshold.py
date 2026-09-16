"""Tests for article grade threshold helpers."""
from services.ingestion.article_scorer import grade_meets_minimum


def test_grade_meets_minimum_s_only():
    assert grade_meets_minimum("S", "S")
    assert not grade_meets_minimum("A", "S")
    assert not grade_meets_minimum("B", "S")


def test_grade_meets_minimum_a_and_above():
    assert grade_meets_minimum("S", "A")
    assert grade_meets_minimum("A", "A")
    assert not grade_meets_minimum("B", "A")


def test_grade_meets_minimum_missing_grade():
    assert not grade_meets_minimum(None, "A")
    assert not grade_meets_minimum("", "S")
