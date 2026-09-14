"""Backtest dual-dimension scoring against 1万+ published posts (Phase 1a)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Iterable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ingestion.article_scorer import score_article
from services.ingestion.publish_tier import compute_publish_tier
from services.ingestion.viral_scorer import score_viral_potential

DB = Path("data/ainews.db")
REPORT = Path("data/publish/phase1a_backtest.json")
THRESHOLD = 10_000
MEGA_THRESHOLD = 100_000
Period = tuple[date, date]


def _prominence(dimensions: list) -> float:
    for d in dimensions:
        if d.key == "prominence":
            return float(d.score)
    return 0.0


@contextmanager
def _score_at_publish_time(published_at: datetime | None):
    """Score timeliness as if evaluated shortly after article publication."""
    if published_at is None:
        yield
        return
    as_of = published_at + timedelta(hours=3)
    with patch("services.ingestion.article_scorer.datetime") as mock_dt:
        mock_dt.utcnow.return_value = as_of
        yield


def _parse_published_at(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def parse_period(value: str) -> Period:
    try:
        start_text, end_text = value.split(":", 1)
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except (AttributeError, ValueError) as exc:
        raise ValueError("period must be START:END using ISO dates") from exc
    if start > end:
        raise ValueError("period start must not be after end")
    return start, end


def validate_chronological_periods(train: Period, holdout: Period) -> None:
    if train[1] >= holdout[0]:
        raise ValueError("train period must end before holdout period starts")


def select_period(rows: Iterable[dict], period: Period) -> list[dict]:
    start, end = period
    selected: list[dict] = []
    for row in rows:
        published_at = _parse_published_at(row.get("published_at"))
        if published_at is not None and start <= published_at.date() <= end:
            selected.append(row)
    return selected


def precision_at_k(
    rows: Iterable[dict],
    score_key: str,
    k: int,
    *,
    view_threshold: int = THRESHOLD,
) -> float | None:
    if k <= 0:
        raise ValueError("k must be positive")
    ranked = sorted(
        rows,
        key=lambda row: (
            -float(row.get(score_key) or 0),
            _parse_published_at(row.get("published_at")) or datetime.max,
            str(row.get("title") or ""),
        ),
    )
    selected = ranked[:k]
    if not selected:
        return None
    return sum(int(row.get("views") or 0) >= view_threshold for row in selected) / len(
        selected
    )


def summarize_period(rows: Iterable[dict]) -> dict:
    samples = list(rows)
    sample_count = len(samples)
    hits_10k = sum(int(row.get("views") or 0) >= THRESHOLD for row in samples)
    hits_100k = sum(int(row.get("views") or 0) >= MEGA_THRESHOLD for row in samples)

    def rate(numerator: int) -> float | None:
        return numerator / sample_count if sample_count else None

    return {
        "sample_count": sample_count,
        "industry_grade_distribution": dict(
            Counter(str(row["industry_grade"]) for row in samples)
        ),
        "viral_grade_distribution": dict(
            Counter(str(row["viral_grade"]) for row in samples)
        ),
        "industry_s_rate": rate(
            sum(row.get("industry_grade") == "S" for row in samples)
        ),
        "viral_s_rate": rate(sum(row.get("viral_grade") == "S" for row in samples)),
        "precision_at_k": {
            "industry": {
                str(k): precision_at_k(samples, "industry_total", k) for k in (5, 10)
            },
            "viral": {
                str(k): precision_at_k(samples, "viral_total", k) for k in (5, 10)
            },
        },
        "hits_10k": hits_10k,
        "hit_rate_10k": rate(hits_10k),
        "hits_100k": hits_100k,
        "hit_rate_100k": rate(hits_100k),
    }


def _readonly_connection(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"database does not exist: {resolved}")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _load_jobs(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            WITH latest_snapshots AS (
                SELECT ranked.*
                FROM (
                    SELECT s.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY s.job_id
                               ORDER BY s.snapshot_date DESC, s.fetched_at DESC, s.id DESC
                           ) AS snapshot_rank
                    FROM publish_post_metric_snapshots s
                ) ranked
                WHERE ranked.snapshot_rank = 1
            )
            SELECT j.title AS publish_title, ia.title, ia.summary, ia.content_text,
                   ia.keywords_json, ia.published_at, ia.view_count AS art_views,
                   s.view_count, s.platform
            FROM publish_jobs j
            JOIN ingested_articles ia ON ia.id = j.source_id
            JOIN latest_snapshots s ON s.job_id = j.id
            WHERE j.status = 'published' AND j.metrics_match_status = 'matched'
            """
        )
    )


def score_jobs(jobs: Iterable[sqlite3.Row]) -> list[dict]:
    results: list[dict] = []
    for job in jobs:
        keywords = []
        try:
            keywords = json.loads(job["keywords_json"] or "[]")
        except json.JSONDecodeError:
            pass
        published_at = _parse_published_at(job["published_at"])
        title = job["title"] or ""
        with _score_at_publish_time(published_at):
            industry = score_article(
                title=title,
                summary=job["summary"],
                content_text=job["content_text"],
                keywords=keywords if isinstance(keywords, list) else [],
                published_at=published_at,
                view_count=job["art_views"],
            )
        viral = score_viral_potential(
            title=title,
            summary=job["summary"],
            content_text=job["content_text"],
            prominence_score=_prominence(industry.dimensions),
        )
        tier = compute_publish_tier(
            industry_grade=industry.grade,
            industry_total=industry.total,
            viral_grade=viral.grade,
            hook_gate_passed=viral.hook_gate.passed,
        )
        results.append(
            {
                "views": job["view_count"] or 0,
                "title": title,
                "published_at": published_at,
                "platform": job["platform"],
                "industry_grade": industry.grade,
                "industry_total": industry.total,
                "viral_grade": viral.grade,
                "viral_total": viral.total,
                "publish_tier": tier,
            }
        )
    return results


def _legacy_summary(results: list[dict]) -> dict:
    hits = [r for r in results if r["views"] >= THRESHOLD]
    viral_priority = [r for r in hits if r["publish_tier"] == "viral_priority"]
    mega = [r for r in results if r["views"] >= MEGA_THRESHOLD]
    return {
        "total_matched": len(results),
        "hits_10k": len(hits),
        "hits_100k": len(mega),
        "viral_priority_in_10k": len(viral_priority),
        "viral_priority_in_100k": sum(
            1 for r in mega if r["publish_tier"] == "viral_priority"
        ),
        "tier_distribution_10k": dict(Counter(r["publish_tier"] for r in hits)),
        "industry_grade_10k": dict(Counter(r["industry_grade"] for r in hits)),
        "viral_grade_10k": dict(Counter(r["viral_grade"] for r in hits)),
        "median_industry_total_10k": (
            median([r["industry_total"] for r in hits]) if hits else None
        ),
        "median_viral_total_10k": (
            median([r["viral_total"] for r in hits]) if hits else None
        ),
    }


def analyze_database(
    db_path: Path,
    *,
    train: Period | None = None,
    holdout: Period | None = None,
) -> dict:
    if train is not None and holdout is not None:
        validate_chronological_periods(train, holdout)
    with closing(_readonly_connection(db_path)) as connection:
        results = score_jobs(_load_jobs(connection))

    periods: dict[str, dict] = {}
    if train is None and holdout is None:
        periods["all"] = {"window": None, **summarize_period(results)}
    else:
        for name, period in (("train", train), ("holdout", holdout)):
            if period is None:
                continue
            periods[name] = {
                "window": {
                    "start": period[0].isoformat(),
                    "end": period[1].isoformat(),
                },
                **summarize_period(select_period(results, period)),
            }

    return {
        "database": str(db_path.expanduser().resolve()),
        "summary": _legacy_summary(results),
        "periods": periods,
        "hits": [row for row in results if row["views"] >= THRESHOLD],
    }


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB, help="SQLite database path")
    parser.add_argument("--train", help="inclusive training period START:END")
    parser.add_argument("--holdout", help="inclusive holdout period START:END")
    parser.add_argument("--report", type=Path, default=REPORT, help="JSON report path")
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        train = parse_period(args.train) if args.train else None
        holdout = parse_period(args.holdout) if args.holdout else None
        report = analyze_database(args.db, train=train, holdout=holdout)
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        parser.error(str(exc))

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    print("=== Phase 1a Backtest ===")
    for name, period_summary in report["periods"].items():
        print(f"[{name}]")
        for key, value in period_summary.items():
            print(key, value)
    print("Wrote", args.report)


if __name__ == "__main__":
    main()
