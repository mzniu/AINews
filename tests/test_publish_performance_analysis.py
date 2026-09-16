from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

import scripts.analyze_publish_performance as performance_analysis
from scripts.analyze_publish_performance import (
    analyze_database,
    default_database_path,
    parse_horizons,
    parse_window,
)


@pytest.fixture()
def performance_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "ainews.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE publisher_accounts (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL
        );
        CREATE TABLE publish_jobs (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            video_path TEXT NOT NULL,
            status TEXT NOT NULL,
            published_at TEXT,
            created_at TEXT,
            scheduled_at TEXT
        );
        CREATE TABLE publish_post_metric_snapshots (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            view_count INTEGER,
            like_count INTEGER,
            comment_count INTEGER,
            share_count INTEGER,
            favorite_count INTEGER,
            follow_count INTEGER,
            completion_rate REAL,
            avg_watch_sec REAL,
            fetched_at TEXT NOT NULL
        );
        CREATE TABLE ingested_articles (
            id TEXT PRIMARY KEY,
            generated_video_path TEXT,
            generated_video_at TEXT
        );
        """
    )
    connection.executemany(
        "INSERT INTO publisher_accounts (id, platform) VALUES (?, ?)",
        [("wx", "wechat_channels"), ("dy", "douyin")],
    )
    connection.executemany(
        """
        INSERT INTO publish_jobs
            (id, account_id, video_path, status, published_at, created_at, scheduled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("before-wx-1", "wx", "videos/shared.mp4", "published", "2026-01-01 00:00:00", "2025-12-31 12:00:00", None),
            ("before-wx-2", "wx", "videos/wx-2.mp4", "published", "2026-01-02 00:00:00", "2026-01-01 12:00:00", None),
            ("before-dy", "dy", "videos/dy.mp4", "published", "2026-01-02 06:00:00", "2026-01-02 05:00:00", None),
            ("after-wx", "wx", "videos/shared.mp4", "published", "2026-01-03 00:00:00", "2026-01-02 12:00:00", None),
            ("immature", "wx", "videos/immature.mp4", "published", "2026-01-04 00:00:00", "2026-01-03 12:00:00", None),
            ("pending-1", "wx", "videos/pending.mp4", "pending", None, "2026-01-05 00:00:00", "2026-01-06 00:00:00"),
            ("pending-2", "dy", "videos/pending.mp4", "pending", None, "2026-01-06 00:00:00", "2026-01-07 00:00:00"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO publish_post_metric_snapshots
            (id, job_id, snapshot_date, view_count, like_count, comment_count,
             share_count, favorite_count, follow_count, completion_rate,
             avg_watch_sec, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            # snapshot_date ordering deliberately disagrees with fetched_at maturity.
            ("wx1-early", "before-wx-1", "2026-01-02", 9999, 999, 0, 0, 0, 0, 1.0, 1.0, "2026-01-01 23:59:59"),
            ("wx1-d1", "before-wx-1", "2026-01-01", 1000, 100, 10, 5, 2, 1, 40.0, 8.0, "2026-01-02 00:00:00"),
            ("wx1-later", "before-wx-1", "2026-01-03", 9000, 900, 90, 45, 18, 9, 80.0, 16.0, "2026-01-02 06:00:00"),
            ("wx1-d3", "before-wx-1", "2026-01-04", 10000, 1000, 100, 50, 20, 10, 60.0, 12.0, "2026-01-04 00:00:00"),
            ("wx2-d1", "before-wx-2", "2026-01-03", 3000, 150, 30, 15, 6, 3, 20.0, 4.0, "2026-01-03 00:00:01"),
            ("dy-d1", "before-dy", "2026-01-03", 11000, 110, 11, 5, 2, 1, 50.0, 10.0, "2026-01-03 06:00:00"),
            ("after-d1", "after-wx", "2026-01-04", 500, 25, 5, 0, 0, 0, 10.0, 2.0, "2026-01-04 00:00:00"),
            ("immature-only", "immature", "2026-01-05", 50000, 1, 1, 1, 1, 1, 99.0, 99.0, "2026-01-04 23:59:59"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO ingested_articles (id, generated_video_path, generated_video_at)
        VALUES (?, ?, ?)
        """,
        [
            ("article-1", "videos/one.mp4", "2026-01-01 10:00:00"),
            ("article-2", "videos/two.mp4", "2026-01-01 11:00:00"),
            ("article-3", "videos/three.mp4", "2026-01-03 10:00:00"),
            ("not-generated", None, "2026-01-03 11:00:00"),
        ],
    )
    connection.commit()
    connection.close()
    return db_path


def test_selects_first_snapshot_at_exact_fetched_at_horizon_and_excludes_immature(
    performance_db: Path,
) -> None:
    report = analyze_database(
        performance_db,
        before=parse_window("2026-01-01:2026-01-02"),
        after=parse_window("2026-01-03:2026-01-04"),
        horizons=[24, 72],
        now=datetime(2026, 1, 10),
    )

    before = report["windows"]["before"]["platforms"]["wechat_channels"]
    assert before["24h"]["sample_size"] == 2
    assert before["24h"]["median_views"] == 2000
    assert before["24h"]["mean_views"] == 2000
    assert before["72h"]["sample_size"] == 1
    assert before["72h"]["median_views"] == 10000

    after = report["windows"]["after"]["platforms"]["wechat_channels"]["24h"]
    assert after["sample_size"] == 1
    assert after["median_views"] == 500


def test_includes_complete_platform_horizon_matrix_for_empty_samples(
    performance_db: Path,
) -> None:
    report = analyze_database(
        performance_db,
        before=parse_window("2026-01-01:2026-01-02"),
        after=parse_window("2026-01-03:2026-01-04"),
        horizons=[24, 72],
        now=datetime(2026, 1, 10),
    )

    for window in report["windows"].values():
        assert set(window["platforms"]) == {"wechat_channels", "douyin"}
        for platform in window["platforms"].values():
            assert set(platform) == {"24h", "72h"}

    empty = report["windows"]["after"]["platforms"]["douyin"]["24h"]
    assert empty["sample_size"] == 0
    assert empty["median_views"] is None
    assert empty["mean_views"] is None
    assert empty["hit_rate_1k"] is None
    assert empty["hit_rate_10k"] is None
    assert empty["completion_rate"] is None
    assert empty["average_watch_seconds"] is None
    assert all(value is None for value in empty["engagement_rates"].values())


def test_groups_platforms_windows_and_calculates_rates_and_daily_counts(
    performance_db: Path,
) -> None:
    report = analyze_database(
        performance_db,
        before=parse_window("2026-01-01:2026-01-02"),
        after=parse_window("2026-01-03:2026-01-04"),
        horizons=[24],
        now=datetime(2026, 1, 10),
    )

    before = report["windows"]["before"]
    assert set(before["platforms"]) == {"wechat_channels", "douyin"}
    assert before["platforms"]["douyin"]["24h"]["median_views"] == 11000
    wechat = before["platforms"]["wechat_channels"]["24h"]
    assert wechat["hit_rate_1k"] == 1.0
    assert wechat["hit_rate_10k"] == 0.0
    assert wechat["completion_rate"] == 30.0
    assert wechat["average_watch_seconds"] == 6.0
    assert wechat["engagement_rates"]["like"] == pytest.approx(0.0625)
    assert wechat["engagement_rates"]["total"] == pytest.approx(0.0805)
    assert before["daily_generated_video_count"] == {
        "2026-01-01": 2,
        "2026-01-02": 0,
    }
    assert before["daily_published_unique_video_count"] == {
        "2026-01-01": 1,
        "2026-01-02": 2,
    }
    assert report["windows"]["after"]["daily_published_unique_video_count"] == {
        "2026-01-03": 1,
        "2026-01-04": 1,
    }
    assert report["pending_queue"]["job_count"] == 2
    assert report["pending_queue"]["unique_video_count"] == 1
    assert report["pending_queue"]["oldest_age_days"] == 4.0
    assert report["pending_queue"]["estimated_days_at_after_rate"] == 1.0


def test_default_queue_age_uses_utcnow_for_naive_utc_timestamps(
    performance_db: Path,
    monkeypatch,
) -> None:
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("local datetime.now() must not be used")

        @classmethod
        def utcnow(cls):
            return cls(2026, 1, 10)

    monkeypatch.setattr(performance_analysis, "datetime", FakeDateTime)

    report = performance_analysis.analyze_database(
        performance_db,
        before=parse_window("2026-01-01:2026-01-02"),
        after=parse_window("2026-01-03:2026-01-04"),
        horizons=[24],
    )

    assert report["pending_queue"]["oldest_age_days"] == 4.0


def test_read_only_analysis_does_not_mutate_database(performance_db: Path) -> None:
    before_bytes = performance_db.read_bytes()

    analyze_database(
        performance_db,
        before=parse_window("2026-01-01:2026-01-02"),
        after=parse_window("2026-01-03:2026-01-04"),
        horizons=[24],
        now=datetime(2026, 1, 10),
    )

    assert performance_db.read_bytes() == before_bytes
    assert not performance_db.with_name(f"{performance_db.name}-wal").exists()
    assert not performance_db.with_name(f"{performance_db.name}-shm").exists()


def test_cli_value_parsers_and_default_database_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    assert default_database_path() == tmp_path / "ainews.db"
    assert parse_horizons("24,72") == [24, 72]
    with pytest.raises(ValueError):
        parse_horizons("24,0")
    with pytest.raises(ValueError):
        parse_window("2026-01-03:2026-01-01")
