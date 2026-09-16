"""Compare baseline (pre Phase-1a) vs current dual-dimension scoring on 1万+ posts."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ingestion.article_scorer import load_scoring_config, score_article
from services.ingestion.publish_tier import compute_publish_tier
from services.ingestion.viral_scorer import score_viral_potential

DB = ROOT / "data" / "ainews.db"
REPORT = ROOT / "data" / "publish" / "scoring_10k_comparison.json"
THRESHOLD = 10_000


def _git_show(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8")


def _load_baseline_scorer():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        scorer_path = tmp_path / "baseline_article_scorer.py"
        scorer_path.write_text(_git_show("services/ingestion/article_scorer.py"), encoding="utf-8")
        cfg_path = tmp_path / "article_scoring.yaml"
        cfg_path.write_text(_git_show("config/article_scoring.yaml"), encoding="utf-8")

        spec = importlib.util.spec_from_file_location("baseline_article_scorer", scorer_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("failed to load baseline scorer")
        module = importlib.util.module_from_spec(spec)
        sys.modules["baseline_article_scorer"] = module
        spec.loader.exec_module(module)

        cfg = module.load_scoring_config(cfg_path)
        return module.score_article, cfg


@contextmanager
def _score_at_publish_time(published_at: datetime | None):
    if published_at is None:
        yield
        return
    as_of = published_at + timedelta(hours=3)
    with patch("services.ingestion.article_scorer.datetime") as mock_dt:
        mock_dt.utcnow.return_value = as_of
        with patch("baseline_article_scorer.datetime", mock_dt):
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


def _prominence(dimensions) -> float:
    for dimension in dimensions:
        if dimension.key == "prominence":
            return float(dimension.score)
    return 0.0


def _summarize(rows: list[dict], *, label: str) -> dict:
    hits = [row for row in rows if row["views"] >= THRESHOLD]
    mega = [row for row in rows if row["views"] >= 100_000]
    return {
        "label": label,
        "hits_10k": len(hits),
        "hits_100k": len(mega),
        "median_total_10k": round(median([row["total"] for row in hits]), 3) if hits else 0.0,
        "grade_10k": dict(Counter(row["grade"] for row in hits)),
        "median_total_100k": round(median([row["total"] for row in mega]), 3) if mega else 0.0,
        "grade_100k": dict(Counter(row["grade"] for row in mega)),
        "s_rate_10k": round(sum(1 for row in hits if row["grade"] == "S") / len(hits), 3) if hits else 0.0,
        "s_rate_100k": round(sum(1 for row in mega if row["grade"] == "S") / len(mega), 3) if mega else 0.0,
    }


def main() -> None:
    baseline_score_article, baseline_cfg = _load_baseline_scorer()
    current_cfg = load_scoring_config()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    jobs = list(
        con.execute(
            """
            SELECT j.title AS publish_title, ia.title, ia.summary, ia.content_text,
                   ia.keywords_json, ia.published_at, ia.view_count AS art_views,
                   s.view_count
            FROM publish_jobs j
            JOIN ingested_articles ia ON ia.id = j.source_id
            JOIN (
                SELECT s1.* FROM publish_post_metric_snapshots s1
                JOIN (
                    SELECT job_id, MAX(snapshot_date) AS d
                    FROM publish_post_metric_snapshots
                    GROUP BY job_id
                ) t ON t.job_id = s1.job_id AND t.d = s1.snapshot_date
            ) s ON s.job_id = j.id
            WHERE j.status = 'published' AND j.metrics_match_status = 'matched'
            """
        )
    )

    baseline_rows: list[dict] = []
    industry_rows: list[dict] = []
    viral_rows: list[dict] = []
    current_rows: list[dict] = []
    paired_hits: list[dict] = []

    for job in jobs:
        keywords: list[str] = []
        try:
            keywords = json.loads(job["keywords_json"] or "[]")
        except json.JSONDecodeError:
            pass
        published_at = _parse_published_at(job["published_at"])
        title = job["title"] or ""
        views = int(job["view_count"] or 0)
        kwargs = dict(
            title=title,
            summary=job["summary"],
            content_text=job["content_text"],
            keywords=keywords if isinstance(keywords, list) else [],
            published_at=published_at,
            view_count=job["art_views"],
        )

        with _score_at_publish_time(published_at):
            baseline = baseline_score_article(**kwargs, config=baseline_cfg)
            industry = score_article(**kwargs, config=current_cfg)
        viral = score_viral_potential(
            title=title,
            summary=job["summary"],
            content_text=job["content_text"],
            prominence_score=_prominence(industry.dimensions),
            config=current_cfg,
        )
        publish_tier = compute_publish_tier(
            industry_grade=industry.grade,
            industry_total=industry.total,
            viral_grade=viral.grade,
            hook_gate_passed=viral.hook_gate.passed,
        )

        baseline_rows.append({"views": views, "total": baseline.total, "grade": baseline.grade, "title": title})
        industry_rows.append({"views": views, "total": industry.total, "grade": industry.grade, "title": title})
        viral_rows.append({"views": views, "total": viral.total, "grade": viral.grade, "title": title})
        current_rows.append(
            {
                "views": views,
                "industry_total": industry.total,
                "industry_grade": industry.grade,
                "viral_total": viral.total,
                "viral_grade": viral.grade,
                "publish_tier": publish_tier,
                "title": title,
            }
        )
        if views >= THRESHOLD:
            paired_hits.append(
                {
                    "views": views,
                    "title": title,
                    "baseline_grade": baseline.grade,
                    "baseline_total": round(baseline.total, 1),
                    "industry_grade": industry.grade,
                    "industry_total": round(industry.total, 1),
                    "industry_delta": round(industry.total - baseline.total, 1),
                    "viral_grade": viral.grade,
                    "viral_total": round(viral.total, 1),
                    "publish_tier": publish_tier,
                    "upgraded_to_s": baseline.grade != "S" and industry.grade == "S",
                    "viral_s": viral.grade == "S",
                }
            )

    baseline_summary = _summarize(baseline_rows, label="baseline_single_score")
    industry_summary = _summarize(industry_rows, label="current_industry")
    viral_summary = _summarize(viral_rows, label="current_viral")

    hits = [row for row in paired_hits]
    mega = [row for row in hits if row["views"] >= 100_000]
    comparison = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "threshold_views": THRESHOLD,
        "dataset": {
            "matched_posts": len(jobs),
            "hits_10k": len(hits),
            "hits_100k": len(mega),
        },
        "baseline": baseline_summary,
        "current_industry": industry_summary,
        "current_viral": viral_summary,
        "publish_tier_10k": dict(Counter(row["publish_tier"] for row in hits)),
        "publish_tier_100k": dict(Counter(row["publish_tier"] for row in mega)),
        "hit_upgrades": {
            "industry_baseline_to_s": sum(1 for row in hits if row["upgraded_to_s"]),
            "industry_median_delta_10k": round(
                median(row["industry_delta"] for row in hits), 3
            ),
            "viral_s_on_hits": sum(1 for row in hits if row["viral_s"]),
            "viral_s_on_100k": sum(1 for row in mega if row["viral_s"]),
            "both_s_on_100k": sum(
                1
                for row in mega
                if row["industry_grade"] == "S" and row["viral_grade"] == "S"
            ),
            "viral_priority_on_100k": sum(
                1 for row in mega if row["publish_tier"] == "viral_priority"
            ),
        },
        "hits": sorted(hits, key=lambda row: row["views"], reverse=True),
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 1万+ 评分对比（baseline vs 当前） ===")
    print(f"样本: 已匹配 {comparison['dataset']['matched_posts']} 篇, 1万+ {comparison['dataset']['hits_10k']} 篇, 10万+ {comparison['dataset']['hits_100k']} 篇")
    print()
    print("指标                 baseline    当前行业    当前传播")
    print("-" * 58)
    print(
        f"10K+ 中位数          {baseline_summary['median_total_10k']:>8.1f}    "
        f"{industry_summary['median_total_10k']:>8.1f}    {viral_summary['median_total_10k']:>8.1f}"
    )
    print(
        f"10K+ S级占比          {baseline_summary['s_rate_10k'] * 100:>7.1f}%    "
        f"{industry_summary['s_rate_10k'] * 100:>7.1f}%    {viral_summary['s_rate_10k'] * 100:>7.1f}%"
    )
    print(
        f"10万+ S级占比         {baseline_summary['s_rate_100k'] * 100:>7.1f}%    "
        f"{industry_summary['s_rate_100k'] * 100:>7.1f}%    {viral_summary['s_rate_100k'] * 100:>7.1f}%"
    )
    print(
        f"10万+ S级篇数         {baseline_summary['grade_100k'].get('S', 0):>8}    "
        f"{industry_summary['grade_100k'].get('S', 0):>8}    {viral_summary['grade_100k'].get('S', 0):>8}"
    )
    print()
    print("10K+ 等级分布 (baseline → 行业 / 传播)")
    print("  baseline:", baseline_summary["grade_10k"])
    print("  industry:", industry_summary["grade_10k"])
    print("  viral:   ", viral_summary["grade_10k"])
    print()
    print("发布分层 publish_tier (10K+):", comparison["publish_tier_10k"])
    print("升级统计:")
    for key, value in comparison["hit_upgrades"].items():
        print(f"  {key}: {value}")
    print("Wrote", REPORT)


if __name__ == "__main__":
    main()
