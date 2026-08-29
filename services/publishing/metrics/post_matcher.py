"""Match published jobs to platform metrics rows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.post_id import extract_platform_post_id, is_synthetic_platform_post_id

MATCH_EXACT = "matched"
MATCH_FUZZY = "fuzzy_matched"
MATCH_UNMATCHED = "unmatched"


@dataclass
class JobMatchResult:
    status: str
    metrics: PostMetricsItem | None = None


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", "", (title or "")).lower()


def titles_fuzzy_match(job_title: str, item_title: str) -> bool:
    job_norm = normalize_title(job_title)
    item_norm = normalize_title(item_title)
    if not job_norm or not item_norm:
        return False
    if job_norm == item_norm:
        return True
    if job_norm in item_norm or item_norm in job_norm:
        return True
    first_line = normalize_title((item_title or "").split("\n")[0])
    if first_line and (job_norm == first_line or job_norm in first_line or first_line in job_norm):
        return True
    return False


def _within_hours(a: datetime | None, b: datetime | None, hours: int) -> bool:
    if a is None or b is None:
        return True
    return abs((a - b).total_seconds()) <= hours * 3600


def _effective_platform_post_id(job: dict, platform: str | None) -> str | None:
    resolved = str(job.get("resolved_post_id") or "").strip()
    if resolved and not is_synthetic_platform_post_id(resolved):
        return resolved
    post_id = str(job.get("platform_post_id") or "").strip() or None
    if post_id and not is_synthetic_platform_post_id(post_id):
        return post_id
    url = str(job.get("platform_post_url") or "").strip()
    if url and platform:
        extracted = extract_platform_post_id(platform, url)
        if extracted:
            return extracted
    return post_id


def match_jobs_to_metrics(
    jobs: list[dict],
    items: list[PostMetricsItem],
    *,
    fuzzy_hours: int = 24,
    platform: str | None = None,
) -> dict[str, JobMatchResult]:
    used_item_ids: set[str] = set()
    results: dict[str, JobMatchResult] = {}

    for job in jobs:
        job_id = job["id"]
        post_id = _effective_platform_post_id(job, platform)
        published_at = job.get("published_at")

        exact = None
        if post_id and not is_synthetic_platform_post_id(post_id):
            for item in items:
                if item.platform_post_id == post_id and item.platform_post_id not in used_item_ids:
                    exact = item
                    break

        if exact is not None:
            used_item_ids.add(exact.platform_post_id)
            results[job_id] = JobMatchResult(status=MATCH_EXACT, metrics=exact)
            continue

        fuzzy = None
        for item in items:
            if item.platform_post_id in used_item_ids:
                continue
            if not titles_fuzzy_match(job.get("title") or "", item.title):
                continue
            if not _within_hours(published_at, item.published_at, fuzzy_hours):
                continue
            fuzzy = item
            break

        if fuzzy is not None:
            used_item_ids.add(fuzzy.platform_post_id)
            results[job_id] = JobMatchResult(status=MATCH_FUZZY, metrics=fuzzy)
        else:
            results[job_id] = JobMatchResult(status=MATCH_UNMATCHED, metrics=None)

    _apply_time_sequence_matches(jobs, items, results, used_item_ids)

    return results


def _apply_time_sequence_matches(
    jobs: list[dict],
    items: list[PostMetricsItem],
    results: dict[str, JobMatchResult],
    used_item_ids: set[str],
    *,
    max_delta_minutes: int = 60,
) -> None:
    """Pair synthetic-ID jobs to metrics by publish-time order (platform title often differs)."""
    unmatched_jobs = [
        job
        for job in jobs
        if results.get(job["id"], JobMatchResult(MATCH_UNMATCHED)).status == MATCH_UNMATCHED
        and (
            str(job.get("platform_post_id") or "").startswith("ks_")
            or str(job.get("platform_post_id") or "").startswith("dy_")
            or str(job.get("platform_post_id") or "").startswith("wx_")
        )
        and job.get("published_at") is not None
    ]
    remaining_items = [
        item
        for item in items
        if item.platform_post_id not in used_item_ids and item.published_at is not None
    ]
    if not unmatched_jobs or not remaining_items:
        return

    unmatched_jobs.sort(key=lambda job: job["published_at"], reverse=True)
    remaining_items.sort(key=lambda item: item.published_at, reverse=True)

    for job, item in zip(unmatched_jobs, remaining_items):
        delta_sec = abs((job["published_at"] - item.published_at).total_seconds())
        if delta_sec > max_delta_minutes * 60:
            continue
        used_item_ids.add(item.platform_post_id)
        results[job["id"]] = JobMatchResult(status=MATCH_FUZZY, metrics=item)
