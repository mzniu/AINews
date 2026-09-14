"""Backtest benchmark thresholds for Phase 1a scoring (shadow mode)."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import pytest

import scripts.backtest_phase1a_scoring as backtest

REPORT = Path("data/publish/phase1a_backtest.json")


@pytest.fixture(scope="module")
def backtest_summary() -> dict:
    if not REPORT.exists():
        pytest.skip("Run scripts/backtest_phase1a_scoring.py first")
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    return data["summary"]


def test_viral_priority_covers_100k_baseline(backtest_summary):
    hits_100k = backtest_summary["hits_100k"]
    if hits_100k == 0:
        pytest.skip("no 100k hits in dataset")
    ratio = backtest_summary["viral_priority_in_100k"] / hits_100k
    # Phase 1a shadow baseline (tune in Phase 1b after threshold calibration)
    assert ratio >= 0.35


def test_10k_hits_mostly_actionable(backtest_summary):
    hits = backtest_summary["hits_10k"]
    skipped = backtest_summary["tier_distribution_10k"].get("skip", 0)
    actionable = hits - skipped
    assert actionable / hits >= 0.7


def test_viral_total_has_spread_over_industry(backtest_summary):
    assert backtest_summary["median_viral_total_10k"] != backtest_summary[
        "median_industry_total_10k"
    ]


def test_10k_hits_have_viral_priority_bucket(backtest_summary):
    assert backtest_summary["viral_priority_in_10k"] >= 5


@pytest.fixture()
def scored_rows() -> list[dict]:
    return [
        {
            "title": "train-hit",
            "published_at": datetime(2026, 1, 1, 8),
            "views": 20_000,
            "industry_total": 95,
            "industry_grade": "S",
            "viral_total": 60,
            "viral_grade": "A",
        },
        {
            "title": "train-miss",
            "published_at": datetime(2026, 1, 2, 8),
            "views": 500,
            "industry_total": 90,
            "industry_grade": "S",
            "viral_total": 80,
            "viral_grade": "S",
        },
        {
            "title": "holdout-mega",
            "published_at": datetime(2026, 2, 1, 8),
            "views": 120_000,
            "industry_total": 75,
            "industry_grade": "A",
            "viral_total": 96,
            "viral_grade": "S",
        },
    ]


def test_period_helpers_split_inclusive_dates_chronologically(scored_rows):
    train = backtest.parse_period("2026-01-01:2026-01-31")
    holdout = backtest.parse_period("2026-02-01:2026-02-28")
    backtest.validate_chronological_periods(train, holdout)

    assert [row["title"] for row in backtest.select_period(scored_rows, train)] == [
        "train-hit",
        "train-miss",
    ]
    assert [row["title"] for row in backtest.select_period(scored_rows, holdout)] == [
        "holdout-mega"
    ]
    with pytest.raises(ValueError):
        backtest.validate_chronological_periods(holdout, train)


def test_precision_at_k_ranks_scores_against_future_views(scored_rows):
    train_rows = backtest.select_period(
        scored_rows, (date(2026, 1, 1), date(2026, 1, 31))
    )
    assert backtest.precision_at_k(train_rows, "industry_total", 2) == 0.5
    assert backtest.precision_at_k(train_rows, "viral_total", 1) == 0.0
    assert backtest.precision_at_k([], "industry_total", 5) is None


def test_period_summary_reports_distribution_s_rates_precision_and_hits(scored_rows):
    summary = backtest.summarize_period(scored_rows)

    assert summary["sample_count"] == 3
    assert summary["industry_grade_distribution"] == {"S": 2, "A": 1}
    assert summary["viral_grade_distribution"] == {"A": 1, "S": 2}
    assert summary["industry_s_rate"] == pytest.approx(2 / 3)
    assert summary["viral_s_rate"] == pytest.approx(2 / 3)
    assert summary["precision_at_k"]["industry"]["5"] == pytest.approx(2 / 3)
    assert summary["precision_at_k"]["viral"]["10"] == pytest.approx(2 / 3)
    assert summary["hits_10k"] == 2
    assert summary["hit_rate_10k"] == pytest.approx(2 / 3)
    assert summary["hits_100k"] == 1
    assert summary["hit_rate_100k"] == pytest.approx(1 / 3)


def test_latest_metric_snapshot_is_loaded_from_database_read_only(tmp_path):
    db_path = tmp_path / "desktop.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE publish_jobs (
            id TEXT PRIMARY KEY, title TEXT, source_id TEXT, status TEXT,
            metrics_match_status TEXT
        );
        CREATE TABLE ingested_articles (
            id TEXT PRIMARY KEY, title TEXT, summary TEXT, content_text TEXT,
            keywords_json TEXT, published_at TEXT, view_count INTEGER
        );
        CREATE TABLE publish_post_metric_snapshots (
            id TEXT PRIMARY KEY, job_id TEXT, snapshot_date TEXT,
            fetched_at TEXT, view_count INTEGER, platform TEXT
        );
        INSERT INTO publish_jobs VALUES
            ('job-1', 'published title', 'article-1', 'published', 'matched');
        INSERT INTO ingested_articles VALUES
            ('article-1', 'article title', 'summary', 'content', '[]',
             '2026-01-01 08:00:00', 123);
        INSERT INTO publish_post_metric_snapshots VALUES
            ('old', 'job-1', '2026-01-02', '2026-01-02 09:00:00', 500, 'douyin'),
            ('new', 'job-1', '2026-01-03', '2026-01-03 09:00:00', 20000, 'douyin');
        """
    )
    connection.commit()
    connection.close()
    before = db_path.read_bytes()

    with closing(backtest._readonly_connection(db_path)) as readonly:
        jobs = backtest._load_jobs(readonly)

    assert len(jobs) == 1
    assert jobs[0]["view_count"] == 20_000
    assert db_path.read_bytes() == before
    assert not db_path.with_name(f"{db_path.name}-wal").exists()
    assert not db_path.with_name(f"{db_path.name}-shm").exists()


def test_cli_accepts_database_and_train_holdout_periods(tmp_path):
    args = backtest._parser().parse_args(
        [
            "--db",
            str(tmp_path / "desktop.db"),
            "--train",
            "2026-01-01:2026-01-31",
            "--holdout",
            "2026-02-01:2026-02-28",
        ]
    )
    assert args.db == tmp_path / "desktop.db"
    assert args.train == "2026-01-01:2026-01-31"
    assert args.holdout == "2026-02-01:2026-02-28"
