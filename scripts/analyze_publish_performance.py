"""Read-only before/after analysis of desktop publishing performance."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_HORIZONS = [24, 72]
PENDING_STATUSES = ("pending",)
COUNT_METRICS = ("like", "comment", "share", "favorite", "follow")

DateWindow = tuple[date, date]


def default_database_path() -> Path:
    """Return the desktop database path without creating it or its directory."""
    data_dir = os.getenv("AINEWS_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir).expanduser() / "ainews.db"
    roaming = os.getenv("APPDATA", "").strip()
    root = Path(roaming).expanduser() if roaming else Path.home() / "AppData" / "Roaming"
    return root / "AINews" / "ainews.db"


def parse_window(value: str) -> DateWindow:
    try:
        start_text, end_text = value.split(":", 1)
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("window must be START:END using ISO dates") from exc
    if start > end:
        raise ValueError("window start must not be after end")
    return start, end


def parse_horizons(value: str) -> list[int]:
    try:
        horizons = [int(part.strip()) for part in value.split(",") if part.strip()]
    except (AttributeError, ValueError) as exc:
        raise ValueError("horizons must be comma-separated positive integers") from exc
    if not horizons or any(hours <= 0 for hours in horizons):
        raise ValueError("horizons must be comma-separated positive integers")
    return list(dict.fromkeys(horizons))


def _readonly_connection(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"database does not exist: {resolved}")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _date_keys(window: DateWindow) -> list[str]:
    start, end = window
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def _window_bounds(window: DateWindow) -> tuple[str, str]:
    start, end = window
    return start.isoformat(), (end + timedelta(days=1)).isoformat()


def _selected_snapshots(
    connection: sqlite3.Connection,
    window: DateWindow,
    horizon_hours: int,
) -> list[sqlite3.Row]:
    start, end_exclusive = _window_bounds(window)
    modifier = f"+{horizon_hours} hours"
    return connection.execute(
        """
        WITH qualifying AS (
            SELECT
                a.platform,
                j.id AS job_id,
                s.view_count,
                s.like_count,
                s.comment_count,
                s.share_count,
                s.favorite_count,
                s.follow_count,
                s.completion_rate,
                s.avg_watch_sec,
                ROW_NUMBER() OVER (
                    PARTITION BY j.id
                    ORDER BY datetime(s.fetched_at), s.id
                ) AS maturity_rank
            FROM publish_jobs AS j
            JOIN publisher_accounts AS a ON a.id = j.account_id
            JOIN publish_post_metric_snapshots AS s ON s.job_id = j.id
            WHERE j.status = 'published'
              AND j.published_at IS NOT NULL
              AND datetime(j.published_at) >= datetime(?)
              AND datetime(j.published_at) < datetime(?)
              AND datetime(s.fetched_at) >= datetime(j.published_at, ?)
        )
        SELECT *
        FROM qualifying
        WHERE maturity_rank = 1
        ORDER BY platform, job_id
        """,
        (start, end_exclusive, modifier),
    ).fetchall()


def _mean_present(rows: Sequence[sqlite3.Row], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row[field] is not None]
    return statistics.fmean(values) if values else None


def _metric_summary(rows: Sequence[sqlite3.Row]) -> dict:
    views = [int(row["view_count"] or 0) for row in rows]
    total_views = sum(views)
    count_totals = {
        metric: sum(int(row[f"{metric}_count"] or 0) for row in rows)
        for metric in COUNT_METRICS
    }
    engagement_rates = {
        metric: (count_totals[metric] / total_views if total_views else None)
        for metric in COUNT_METRICS
    }
    engagement_rates["total"] = (
        sum(count_totals.values()) / total_views if total_views else None
    )
    return {
        "sample_size": len(rows),
        "median_views": statistics.median(views) if views else None,
        "mean_views": statistics.fmean(views) if views else None,
        "hit_rate_1k": sum(view >= 1_000 for view in views) / len(views) if views else None,
        "hit_rate_10k": sum(view >= 10_000 for view in views) / len(views) if views else None,
        "completion_rate": _mean_present(rows, "completion_rate"),
        "average_watch_seconds": _mean_present(rows, "avg_watch_sec"),
        "engagement_rates": engagement_rates,
    }


def _platform_metrics(
    connection: sqlite3.Connection,
    window: DateWindow,
    horizons: Sequence[int],
) -> dict[str, dict[str, dict]]:
    configured_platforms = [
        str(row["platform"])
        for row in connection.execute(
            """
            SELECT DISTINCT platform
            FROM publisher_accounts
            WHERE platform IS NOT NULL AND trim(platform) != ''
            ORDER BY platform
            """
        ).fetchall()
    ]
    platforms: dict[str, dict[str, dict]] = {
        platform: {
            f"{horizon}h": _metric_summary([])
            for horizon in horizons
        }
        for platform in configured_platforms
    }
    for horizon in horizons:
        rows = _selected_snapshots(connection, window, horizon)
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(str(row["platform"]), []).append(row)
        for platform, platform_rows in grouped.items():
            platforms.setdefault(platform, {})[f"{horizon}h"] = _metric_summary(platform_rows)
    return dict(sorted(platforms.items()))


def _daily_generated_counts(
    connection: sqlite3.Connection,
    window: DateWindow,
) -> dict[str, int]:
    start, end_exclusive = _window_bounds(window)
    counts = dict.fromkeys(_date_keys(window), 0)
    rows = connection.execute(
        """
        SELECT date(generated_video_at) AS day, COUNT(*) AS item_count
        FROM ingested_articles
        WHERE generated_video_path IS NOT NULL
          AND trim(generated_video_path) != ''
          AND datetime(generated_video_at) >= datetime(?)
          AND datetime(generated_video_at) < datetime(?)
        GROUP BY date(generated_video_at)
        """,
        (start, end_exclusive),
    ).fetchall()
    for row in rows:
        counts[str(row["day"])] = int(row["item_count"])
    return counts


def _daily_published_unique_counts(
    connection: sqlite3.Connection,
    window: DateWindow,
) -> dict[str, int]:
    start, end_exclusive = _window_bounds(window)
    counts = dict.fromkeys(_date_keys(window), 0)
    rows = connection.execute(
        """
        SELECT date(published_at) AS day, COUNT(DISTINCT video_path) AS item_count
        FROM publish_jobs
        WHERE status = 'published'
          AND published_at IS NOT NULL
          AND datetime(published_at) >= datetime(?)
          AND datetime(published_at) < datetime(?)
        GROUP BY date(published_at)
        """,
        (start, end_exclusive),
    ).fetchall()
    for row in rows:
        counts[str(row["day"])] = int(row["item_count"])
    return counts


def _window_report(
    connection: sqlite3.Connection,
    window: DateWindow,
    horizons: Sequence[int],
) -> dict:
    generated = _daily_generated_counts(connection, window)
    published = _daily_published_unique_counts(connection, window)
    return {
        "start": window[0].isoformat(),
        "end": window[1].isoformat(),
        "platforms": _platform_metrics(connection, window, horizons),
        "daily_generated_video_count": generated,
        "average_daily_generated_video_count": statistics.fmean(generated.values()),
        "daily_published_unique_video_count": published,
        "average_daily_published_unique_video_count": statistics.fmean(published.values()),
    }


def _pending_queue(
    connection: sqlite3.Connection,
    *,
    now: datetime,
    after_daily_published_rate: float,
) -> dict:
    placeholders = ",".join("?" for _ in PENDING_STATUSES)
    row = connection.execute(
        f"""
        SELECT
            COUNT(*) AS job_count,
            COUNT(DISTINCT video_path) AS unique_video_count,
            MIN(COALESCE(scheduled_at, created_at)) AS oldest_at
        FROM publish_jobs
        WHERE status IN ({placeholders})
        """,
        PENDING_STATUSES,
    ).fetchone()
    unique_videos = int(row["unique_video_count"] or 0)
    oldest_at = datetime.fromisoformat(row["oldest_at"]) if row["oldest_at"] else None
    oldest_age_days = (
        max(0.0, (now - oldest_at).total_seconds() / 86_400) if oldest_at else None
    )
    return {
        "job_count": int(row["job_count"] or 0),
        "unique_video_count": unique_videos,
        "oldest_age_days": oldest_age_days,
        "estimated_days_at_after_rate": (
            unique_videos / after_daily_published_rate if after_daily_published_rate else None
        ),
    }


def analyze_database(
    db_path: str | Path,
    *,
    before: DateWindow,
    after: DateWindow,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    now: datetime | None = None,
) -> dict:
    """Analyze a SQLite database without opening any writable connection."""
    path = Path(db_path)
    normalized_horizons = list(dict.fromkeys(int(hours) for hours in horizons))
    if not normalized_horizons or any(hours <= 0 for hours in normalized_horizons):
        raise ValueError("horizons must contain positive integers")

    with closing(_readonly_connection(path)) as connection:
        before_report = _window_report(connection, before, normalized_horizons)
        after_report = _window_report(connection, after, normalized_horizons)
        pending = _pending_queue(
            connection,
            now=now or datetime.utcnow(),
            after_daily_published_rate=after_report[
                "average_daily_published_unique_video_count"
            ],
        )
    return {
        "database": str(path.expanduser().resolve()),
        "horizons_hours": normalized_horizons,
        "windows": {"before": before_report, "after": after_report},
        "pending_queue": pending,
    }


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def _number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.{digits}f}"


def render_human(report: dict) -> str:
    lines = [
        f"Database: {report['database']}",
        f"Horizons: {', '.join(f'{item}h' for item in report['horizons_hours'])}",
    ]
    for label in ("before", "after"):
        window = report["windows"][label]
        lines.extend(
            [
                "",
                f"{label.upper()} {window['start']} through {window['end']}",
                "Daily generated videos: "
                + ", ".join(
                    f"{day}={count}"
                    for day, count in window["daily_generated_video_count"].items()
                ),
                "Daily published unique videos: "
                + ", ".join(
                    f"{day}={count}"
                    for day, count in window[
                        "daily_published_unique_video_count"
                    ].items()
                ),
            ]
        )
        for platform, horizons in window["platforms"].items():
            lines.append(f"  {platform}")
            for horizon, metrics in horizons.items():
                rates = metrics["engagement_rates"]
                lines.append(
                    "    "
                    f"{horizon}: n={metrics['sample_size']}, "
                    f"views median={_number(metrics['median_views'])}, "
                    f"mean={_number(metrics['mean_views'])}, "
                    f">=1k={_percent(metrics['hit_rate_1k'])}, "
                    f">=10k={_percent(metrics['hit_rate_10k'])}, "
                    f"completion={_number(metrics['completion_rate'])}, "
                    f"watch={_number(metrics['average_watch_seconds'])}s"
                )
                lines.append(
                    "      engagement: "
                    + ", ".join(
                        f"{name}={_percent(rates[name])}"
                        for name in (*COUNT_METRICS, "total")
                    )
                )
    queue = report["pending_queue"]
    lines.extend(
        [
            "",
            "Pending queue: "
            f"{queue['job_count']} jobs / {queue['unique_video_count']} unique videos; "
            f"oldest={_number(queue['oldest_age_days'])} days; "
            f"estimated={_number(queue['estimated_days_at_after_rate'])} days",
        ]
    )
    return "\n".join(lines)


def _window_argument(value: str) -> DateWindow:
    try:
        return parse_window(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _horizons_argument(value: str) -> list[int]:
    try:
        return parse_horizons(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_database_path())
    parser.add_argument("--before", type=_window_argument, required=True, metavar="START:END")
    parser.add_argument("--after", type=_window_argument, required=True, metavar="START:END")
    parser.add_argument(
        "--horizons",
        type=_horizons_argument,
        default=DEFAULT_HORIZONS,
        help="comma-separated hours (default: 24,72)",
    )
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = analyze_database(
            args.db,
            before=args.before,
            after=args.after,
            horizons=args.horizons,
        )
    except (FileNotFoundError, sqlite3.DatabaseError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(render_human(report))
    if args.json_out:
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
