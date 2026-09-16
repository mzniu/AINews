"""Orchestrate daily publish metrics sync."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.orm import sessionmaker

from services.publishing.metrics.config import load_metrics_sync_config
from services.publishing.metrics.adapters.base import PostMetricsItem
from services.publishing.metrics.post_id import (
    build_platform_post_url,
    extract_platform_post_id,
    is_synthetic_platform_post_id,
)
from services.publishing.metrics.post_matcher import MATCH_EXACT, MATCH_FUZZY, MATCH_UNMATCHED, match_jobs_to_metrics
from services.publishing.metrics.registry import fetch_platform_metrics_items, fetch_platform_post_metrics
from services.publishing.metrics.snapshot_store import upsert_metric_snapshot
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models.publishing_metrics import PublishMetricsSyncRun
from src.utils.paths import resolve_data_path

SNAPSHOT_TZ = ZoneInfo("Asia/Shanghai")


def resolve_job_post_id(platform: str, job: PublishJob) -> str | None:
    post_id = (job.platform_post_id or "").strip() or None
    if post_id and not is_synthetic_platform_post_id(post_id):
        return post_id
    url = (job.platform_post_url or "").strip()
    if url:
        extracted = extract_platform_post_id(platform, url)
        if extracted:
            return extracted
    return post_id


def _is_real_post_id(post_id: str | None) -> bool:
    return bool(post_id) and not is_synthetic_platform_post_id(post_id)


@dataclass
class AccountSyncResult:
    posts_synced: int = 0
    posts_unmatched: int = 0
    posts_failed: int = 0
    error: str | None = None


@dataclass
class MetricsSyncRunResult:
    id: str
    status: str
    accounts_total: int
    posts_synced: int
    posts_unmatched: int
    posts_failed: int
    error_summary: str | None
    started_at: datetime
    finished_at: datetime | None


def snapshot_date_for_now(now: datetime | None = None) -> date:
    dt = now or datetime.now(SNAPSHOT_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SNAPSHOT_TZ).date()


class MetricsSyncOrchestrator:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory
        self.config = load_metrics_sync_config()

    def sync_all_accounts(self, *, snapshot_date: date | None = None) -> MetricsSyncRunResult:
        snap_date = snapshot_date or snapshot_date_for_now()
        with self.session_factory() as session:
            run = PublishMetricsSyncRun(status="running", started_at=datetime.utcnow())
            session.add(run)
            session.commit()
            run_id = run.id

        accounts: list[PublisherAccount] = []
        with self.session_factory() as session:
            accounts = (
                session.query(PublisherAccount)
                .filter(PublisherAccount.status == "active")
                .order_by(PublisherAccount.platform.asc())
                .all()
            )
            account_ids = [a.id for a in accounts]

        total_synced = 0
        total_unmatched = 0
        total_failed = 0
        errors: list[str] = []

        for index, account_id in enumerate(account_ids):
            try:
                result = self.sync_account(account_id, snapshot_date=snap_date)
                total_synced += result.posts_synced
                total_unmatched += result.posts_unmatched
                total_failed += result.posts_failed
                if result.error:
                    errors.append(result.error)
            except Exception as exc:
                logger.exception("Metrics sync failed for account {}: {}", account_id, exc)
                total_failed += 1
                errors.append(f"{account_id}: {exc}")
            if index < len(account_ids) - 1:
                time.sleep(self.config["per_account_delay_sec"])

        with self.session_factory() as session:
            run = session.get(PublishMetricsSyncRun, run_id)
            if run is None:
                raise RuntimeError("sync run missing")
            run.status = "partial" if errors else "success"
            run.accounts_total = len(account_ids)
            run.posts_synced = total_synced
            run.posts_unmatched = total_unmatched
            run.posts_failed = total_failed
            run.error_summary = "; ".join(errors[:5]) if errors else None
            run.finished_at = datetime.utcnow()
            session.commit()

        try:
            from services.ingestion.article_scorer import load_scoring_config
            from services.publishing.metrics.mature_metrics import get_mature_platform_metrics
            from services.publishing.rollout_guard import maybe_apply_kill_switches

            with self.session_factory() as session:
                mature = get_mature_platform_metrics(
                    session,
                    platforms=["wechat_channels", "douyin", "kuaishou"],
                    horizons=(24,),
                    published_after=datetime.utcnow() - timedelta(days=14),
                )
            applied = maybe_apply_kill_switches(
                mature,
                config=load_scoring_config(),
            )
            if applied:
                logger.warning("Publish policy kill-switch applied: {}", applied)
        except Exception as exc:
            logger.exception("Kill-switch evaluation failed: {}", exc)

        with self.session_factory() as session:
            run = session.get(PublishMetricsSyncRun, run_id)
            if run is None:
                raise RuntimeError("sync run missing")
            return MetricsSyncRunResult(
                id=run.id,
                status=run.status,
                accounts_total=run.accounts_total,
                posts_synced=run.posts_synced,
                posts_unmatched=run.posts_unmatched,
                posts_failed=run.posts_failed,
                error_summary=run.error_summary,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )

    def sync_account(self, account_id: str, *, snapshot_date: date | None = None) -> AccountSyncResult:
        snap_date = snapshot_date or snapshot_date_for_now()
        result = AccountSyncResult()

        with self.session_factory() as session:
            account = session.get(PublisherAccount, account_id)
            if account is None:
                result.error = f"account {account_id} not found"
                result.posts_failed = 1
                return result
            if account.status != "active":
                result.error = f"account {account_id} not active"
                return result

            since_days = self.config["since_days"]
            cutoff = datetime.utcnow() - timedelta(days=since_days)
            jobs = (
                session.query(PublishJob)
                .filter(
                    PublishJob.account_id == account_id,
                    PublishJob.status == "published",
                    PublishJob.published_at.isnot(None),
                    PublishJob.published_at >= cutoff,
                )
                .order_by(PublishJob.published_at.desc())
                .all()
            )
            if not jobs:
                return result

            platform = account.platform
            session_path = resolve_data_path(account.session_path)
            job_dicts = []
            needed_post_ids: set[str] = set()
            for job in jobs:
                resolved_id = resolve_job_post_id(platform, job)
                if _is_real_post_id(resolved_id):
                    needed_post_ids.add(resolved_id)
                job_dicts.append(
                    {
                        "id": job.id,
                        "title": job.title,
                        "platform_post_id": job.platform_post_id,
                        "platform_post_url": job.platform_post_url,
                        "published_at": job.published_at,
                        "metrics_match_status": job.metrics_match_status,
                        "resolved_post_id": resolved_id,
                    }
                )

        try:
            items = fetch_platform_metrics_items(
                platform,
                session_path,
                since_days=since_days,
                limit=self.config["max_posts_per_account"],
                needed_post_ids=needed_post_ids or None,
            )
        except Exception as exc:
            result.error = f"{platform}/{account_id}: {exc}"
            result.posts_failed = len(job_dicts)
            return result

        matches = match_jobs_to_metrics(
            job_dicts,
            items,
            fuzzy_hours=self.config["fuzzy_match_hours"],
            platform=platform,
        )

        detail_by_job: dict[str, PostMetricsItem] = {}
        for job_dict in job_dicts:
            resolved_id = job_dict.get("resolved_post_id")
            bound = _is_real_post_id(resolved_id)
            match = matches.get(job_dict["id"])
            metrics = match.metrics if match is not None else None
            status = match.status if match is not None else MATCH_UNMATCHED
            if metrics is not None and status != MATCH_UNMATCHED:
                if not (bound and status == MATCH_FUZZY and metrics.platform_post_id != resolved_id):
                    continue
            if not bound:
                continue
            try:
                detail = fetch_platform_post_metrics(
                    platform,
                    session_path,
                    platform_post_id=resolved_id,
                    post_url=job_dict.get("platform_post_url"),
                )
            except Exception as exc:
                logger.warning("Metrics detail fetch failed for {}: {}", job_dict["id"], exc)
                detail = None
            if detail is not None:
                detail_by_job[job_dict["id"]] = detail

        with self.session_factory() as session:
            for job_dict in job_dicts:
                job = session.get(PublishJob, job_dict["id"])
                if job is None:
                    continue
                match = matches.get(job.id)
                resolved_id = job_dict.get("resolved_post_id")
                bound = _is_real_post_id(resolved_id)
                metrics = match.metrics if match is not None else None
                status = match.status if match is not None else MATCH_UNMATCHED
                if job.id in detail_by_job:
                    metrics = detail_by_job[job.id]
                    status = MATCH_EXACT
                elif (
                    bound
                    and status == MATCH_FUZZY
                    and metrics is not None
                    and metrics.platform_post_id != resolved_id
                ):
                    metrics = None
                    status = MATCH_UNMATCHED

                if metrics is None:
                    if not bound:
                        job.metrics_match_status = MATCH_UNMATCHED
                    result.posts_unmatched += 1
                    continue

                job.metrics_match_status = status
                job.metrics_last_synced_at = datetime.utcnow()
                if is_synthetic_platform_post_id(job.platform_post_id) or status == MATCH_FUZZY:
                    job.platform_post_id = metrics.platform_post_id
                if metrics.post_url:
                    job.platform_post_url = metrics.post_url
                else:
                    built_url = build_platform_post_url(platform, metrics.platform_post_id)
                    if built_url:
                        job.platform_post_url = built_url

                upsert_metric_snapshot(
                    session,
                    job_id=job.id,
                    account_id=account_id,
                    platform=platform,
                    snapshot_date=snap_date,
                    metrics=metrics,
                )
                result.posts_synced += 1
            session.commit()

        return result
