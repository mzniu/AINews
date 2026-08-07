"""Tests for view count parsing."""
from services.ingestion.view_count import parse_view_count


def test_parse_click_count():
    assert parse_view_count("8706点击 2026-07-31 21:54") == 8706
    assert parse_view_count("8706 点击    2026-07-31") == 8706


def test_parse_read_count():
    assert parse_view_count("1.2万阅读") == 12000
    assert parse_view_count("浏览量：12,345") == 12345


def test_parse_missing_returns_none():
    assert parse_view_count("no metrics here") is None
    assert parse_view_count("") is None
