"""Publish worker: QR login + publish job consumer."""
from __future__ import annotations

import os
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger
from sqlalchemy import func, or_

from services.ingestion.db_retry import run_with_sqlite_retry
from services.publishing.browser_lock import break_stale_browser_lock
from services.publishing.job_recovery import (
    has_active_publish_job,
    has_pending_qr_login,
    recover_stale_publish_jobs,
    recover_stale_qr_sessions,
)
from services.publishing.orchestrator import PublishOrchestrator
from services.publishing.qr_login import process_qr_session
from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import PublishJob, QrLoginSession
from src.utils.config import Config

HEARTBEAT_PATH = Config.DATA_DIR / "publish" / "worker_heartbeat"
ACTIVE_QR = ("pending", "processing")

# Set by web_server when PUBLISH_WORKER_MODE=embedded
_embedded_instance: "PublishWorker | None" = None


def get_publish_worker_mode() -> str:
    """embedded: poll inside web_server; separate: standalone process only."""
    mode = os.getenv("PUBLISH_WORKER_MODE", "embedded").strip().lower()
    return mode if mode in {"embedded", "separate"} else "embedded"


def is_embedded_worker_running() -> bool:
    worker = _embedded_instance
    return worker is not None and worker.scheduler.running


class PublishWorker:
    def __init__(self, *, embedded: bool) -> None:
        self.embedded = embedded
        if not embedded:
            init_db()
        self.session_factory = get_session_factory()
        from services.publishing.job_logging import install_publish_job_log_sink

        install_publish_job_log_sink()
        self._poll_lock = threading.Lock()
        self._qr_lock = threading.Lock()
        scheduler_cls = BackgroundScheduler if embedded else BlockingScheduler
        self.scheduler = scheduler_cls(timezone="Asia/Shanghai")

    def _register_poll_job(self) -> None:
        self._register_candidate_dispatch_job()
        self.scheduler.add_job(
            self._try_process_qr_login,
            "interval",
            seconds=2,
            id="poll_qr_login",
            max_instances=1,
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.poll,
            "interval",
            seconds=5,
            id="poll_publish",
            max_instances=1,
            replace_existing=True,
        )
        self._register_keepalive_job()
        self._register_metrics_sync_job()
        self._register_comment_reply_job()

    def _register_candidate_dispatch_job(self, config=None) -> None:
        from services.ingestion.article_scorer import load_scoring_config

        active = config or load_scoring_config()
        policy = active.get("publish_policy") or {}
        if not policy.get("enabled", False):
            return
        if any(
            job.id == "dispatch_publish_candidates"
            for job in self.scheduler.get_jobs()
        ):
            return
        seconds = max(15, int(policy.get("dispatch_interval_seconds", 60)))
        self.scheduler.add_job(
            self._run_candidate_dispatch,
            "interval",
            seconds=seconds,
            id="dispatch_publish_candidates",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Candidate dispatch scheduled every %s second(s)", seconds)

    def _register_comment_reply_job(self) -> None:
        from services.publishing.comment_reply.config import load_comment_reply_config

        cfg = load_comment_reply_config()
        if not cfg.get("enabled"):
            return
        cron = str(cfg.get("cron", "0 * * * *"))
        parts = cron.split()
        if len(parts) != 5:
            logger.warning("Invalid comment_reply.cron %r, using 0 * * * *", cron)
            parts = ["0", "*", "*", "*", "*"]
        minute, hour, day, month, day_of_week = parts
        self.scheduler.add_job(
            self._run_comment_reply_scan,
            "cron",
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            id="comment_reply_scan",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Comment reply scan scheduled: %s", cron)

    def _register_metrics_sync_job(self) -> None:
        from services.publishing.metrics.config import load_metrics_sync_config

        cfg = load_metrics_sync_config()
        if not cfg.get("enabled", True):
            return
        cron = str(cfg.get("cron", "0 6 * * *"))
        parts = cron.split()
        if len(parts) != 5:
            logger.warning("Invalid metrics_sync.cron %r, using 0 6 * * *", cron)
            parts = ["0", "6", "*", "*", "*"]
        minute, hour, day, month, day_of_week = parts
        self.scheduler.add_job(
            self._run_metrics_sync,
            "cron",
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            id="metrics_sync",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Publish metrics sync scheduled: %s", cron)

    def _register_keepalive_job(self) -> None:
        from services.publishing.session_keepalive import load_session_keepalive_config

        cfg = load_session_keepalive_config()
        if not cfg.get("enabled", True):
            return
        hours = max(1.0, float(cfg.get("interval_hours", 4)))
        self.scheduler.add_job(
            self._run_session_keepalive,
            "interval",
            hours=hours,
            id="session_keepalive",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Session keepalive scheduled every %s hour(s)", hours)

    def start_embedded(self) -> None:
        """Non-blocking: for web_server startup."""
        global _embedded_instance
        if self.scheduler.running:
            return
        self._register_poll_job()
        self.scheduler.start()
        _embedded_instance = self
        self._touch_heartbeat()
        logger.info("Publish worker started (embedded in web_server)")

    def shutdown(self) -> None:
        """Stop embedded scheduler on web_server shutdown."""
        global _embedded_instance
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Publish worker stopped (embedded)")
        if _embedded_instance is self:
            _embedded_instance = None

    def start(self) -> None:
        """Blocking: for `python -m services.publishing.worker`."""
        self._register_poll_job()
        logger.info("Publish worker started (separate process)")
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Publish worker stopped")

    def poll(self) -> None:
        """Scheduler tick: heartbeat + publish jobs (QR login uses a dedicated fast poll)."""
        self._touch_heartbeat()
        if not self._poll_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                self._poll_publish_jobs()
            finally:
                self._poll_lock.release()

        threading.Thread(target=_run, daemon=True, name="publish-poll").start()

    def _try_process_qr_login(self) -> None:
        """Pick up QR login without waiting for long-running publish jobs."""
        if not self._qr_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                with self.session_factory() as session:
                    recover_stale_qr_sessions(session)
                break_stale_browser_lock()
                qr_id = self._claim_pending_qr()
                if qr_id:
                    logger.info("Processing QR login session {}", qr_id)
                    process_qr_session(self.session_factory, qr_id)
            except Exception as exc:
                logger.exception("QR login tick failed: %s", exc)
            finally:
                self._qr_lock.release()

        threading.Thread(target=_run, daemon=True, name="qr-login").start()

    def _poll_publish_jobs(self) -> None:
        with self.session_factory() as session:
            recover_stale_publish_jobs(session)

        break_stale_browser_lock()

        while True:
            job_id = self._claim_pending_job()
            if not job_id:
                break
            logger.info("Publish worker processing job {} (serial queue)", job_id)
            PublishOrchestrator(self.session_factory).publish_job(job_id)

    def _run_session_keepalive(self) -> None:
        if not self._poll_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                from services.publishing.session_keepalive import run_session_keepalive

                summary = run_session_keepalive(self.session_factory)
                if summary.get("expired"):
                    logger.warning(
                        "Session keepalive: %s account(s) expired — re-login required in publish center",
                        summary["expired"],
                    )
            except Exception as exc:
                logger.exception("Session keepalive tick failed: %s", exc)
            finally:
                self._poll_lock.release()

        threading.Thread(target=_run, daemon=True, name="session-keepalive").start()

    def _run_metrics_sync(self) -> None:
        if not self._poll_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                from services.publishing.job_recovery import has_active_publish_job
                from services.publishing.metrics.sync_orchestrator import MetricsSyncOrchestrator

                with self.session_factory() as session:
                    if has_active_publish_job(session):
                        logger.info("Skip metrics sync: publish job in progress")
                        return
                run = MetricsSyncOrchestrator(self.session_factory).sync_all_accounts()
                logger.info(
                    "Metrics sync finished: status=%s synced=%s unmatched=%s failed=%s",
                    run.status,
                    run.posts_synced,
                    run.posts_unmatched,
                    run.posts_failed,
                )
            except Exception as exc:
                logger.exception("Metrics sync tick failed: %s", exc)
            finally:
                self._poll_lock.release()

        threading.Thread(target=_run, daemon=True, name="metrics-sync").start()

    def _run_comment_reply_scan(self) -> None:
        if not self._poll_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                from services.publishing.job_recovery import has_active_publish_job
                from services.publishing.comment_reply.orchestrator import CommentReplyOrchestrator

                with self.session_factory() as session:
                    if has_active_publish_job(session):
                        logger.info("Skip comment reply scan: publish job in progress")
                        return
                result = CommentReplyOrchestrator(self.session_factory).run_scheduled_cycle()
                if result is None:
                    return
                logger.info(
                    "Comment reply cycle finished: accounts=%s pending=%s auto=%s retried=%s",
                    result.accounts_total,
                    result.new_pending,
                    result.auto_sent,
                    result.retried,
                )
            except Exception as exc:
                logger.exception("Comment reply scan tick failed: %s", exc)
            finally:
                self._poll_lock.release()

        threading.Thread(target=_run, daemon=True, name="comment-reply-scan").start()

    def _run_candidate_dispatch(self) -> None:
        if not self._poll_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                from services.publishing.candidate_queue import dispatch_daily_candidates

                def dispatch():
                    with self.session_factory() as session:
                        result = dispatch_daily_candidates(session)
                        session.commit()
                        return result

                result = run_with_sqlite_retry(dispatch)
                if result.get("dispatched"):
                    logger.info(
                        "Candidate dispatch created %s publish job(s)",
                        len(result["dispatched"]),
                    )
            except Exception as exc:
                logger.exception("Candidate dispatch tick failed: %s", exc)
            finally:
                self._poll_lock.release()

        threading.Thread(
            target=_run,
            daemon=True,
            name="candidate-dispatch",
        ).start()

    def _poll_once(self) -> None:
        """Backward-compatible entry: QR first, then publish jobs."""
        with self.session_factory() as session:
            recover_stale_qr_sessions(session)
        break_stale_browser_lock()
        qr_id = self._claim_pending_qr()
        if qr_id:
            process_qr_session(self.session_factory, qr_id)
            return
        self._poll_publish_jobs()

    def _touch_heartbeat(self) -> None:
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_PATH.write_text(datetime.utcnow().isoformat(), encoding="utf-8")

    def _claim_pending_qr(self) -> str | None:
        def claim() -> str | None:
            with self.session_factory() as session:
                row = (
                    session.query(QrLoginSession)
                    .filter(QrLoginSession.status.in_(ACTIVE_QR))
                    .order_by(QrLoginSession.created_at.asc())
                    .first()
                )
                if row is None:
                    return None
                if row.status == "pending":
                    row.status = "processing"
                    row.started_at = datetime.utcnow()
                    session.commit()
                return row.id

        return run_with_sqlite_retry(claim)

    def _claim_pending_job(self) -> str | None:
        from services.ingestion.article_scorer import load_scoring_config
        from services.publishing.schedule import (
            INGESTION_SOURCE,
            in_quiet_hours,
            load_spacing_config,
            maybe_compact_pending_schedule,
        )

        active_config = load_scoring_config()
        policy_enabled = bool(
            (active_config.get("publish_policy") or {}).get("enabled", False)
        )
        spacing = load_spacing_config(active_config)

        def claim() -> str | None:
            with self.session_factory() as session:
                if has_active_publish_job(session):
                    return None
                if has_pending_qr_login(session):
                    return None
                if not policy_enabled:
                    maybe_compact_pending_schedule(session, config=spacing)
                    session.commit()
                now = datetime.utcnow()
                jobs = (
                    session.query(PublishJob)
                    .filter_by(status="pending")
                    .filter(
                        or_(
                            PublishJob.scheduled_at.is_(None),
                            PublishJob.scheduled_at <= now,
                        )
                    )
                    .order_by(
                        func.coalesce(PublishJob.scheduled_at, now).asc(),
                        PublishJob.created_at.asc(),
                    )
                    .all()
                )
                for job in jobs:
                    if job.source_type == INGESTION_SOURCE and in_quiet_hours(now, spacing):
                        continue
                    job.status = "uploading"
                    job.started_at = datetime.utcnow()
                    session.commit()
                    return job.id
                return None

        return run_with_sqlite_retry(claim)


def main() -> None:
    from src.utils.logger import configure_logging

    configure_logging()
    if get_publish_worker_mode() == "embedded":
        logger.warning(
            "PUBLISH_WORKER_MODE=embedded：发布任务由 web_server 内嵌处理，"
            "无需单独运行本进程。若需独立进程请设置 PUBLISH_WORKER_MODE=separate"
        )
    PublishWorker(embedded=False).start()


if __name__ == "__main__":
    main()
