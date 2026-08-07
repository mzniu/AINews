"""Publish worker: QR login + publish job consumer."""
from __future__ import annotations

import os
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger
from sqlalchemy import or_

from services.ingestion.db_retry import run_with_sqlite_retry
from services.publishing.browser_lock import browser_lock
from services.publishing.job_recovery import (
    has_active_publish_job,
    load_publish_lock_timeout_sec,
    recover_stale_publish_jobs,
    recover_stale_qr_sessions,
)
from services.publishing.orchestrator import PublishOrchestrator
from services.publishing.qr_login import process_qr_session
from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import PublishJob, QrLoginSession
from src.utils.config import Config

HEARTBEAT_PATH = Config.ROOT_DIR / "data" / "publish" / "worker_heartbeat"
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
        scheduler_cls = BackgroundScheduler if embedded else BlockingScheduler
        self.scheduler = scheduler_cls(timezone="Asia/Shanghai")

    def _register_poll_job(self) -> None:
        self.scheduler.add_job(
            self.poll,
            "interval",
            seconds=5,
            id="poll_publish",
            max_instances=1,
            replace_existing=True,
        )
        self._register_keepalive_job()

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
        """Scheduler tick: heartbeat + run Playwright work off the asyncio loop."""
        self._touch_heartbeat()
        if not self._poll_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                self._poll_once()
            finally:
                self._poll_lock.release()

        threading.Thread(target=_run, daemon=True, name="publish-poll").start()

    def _run_session_keepalive(self) -> None:
        if not self._poll_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                from services.publishing.session_keepalive import run_session_keepalive

                with browser_lock(timeout_sec=load_publish_lock_timeout_sec()):
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

    def _poll_once(self) -> None:
        with self.session_factory() as session:
            recover_stale_publish_jobs(session)
            recover_stale_qr_sessions(session)

        from services.publishing.browser_lock import break_stale_browser_lock

        break_stale_browser_lock()

        qr_id = self._claim_pending_qr()
        lock_timeout = load_publish_lock_timeout_sec()
        if qr_id:
            with browser_lock(timeout_sec=lock_timeout):
                process_qr_session(self.session_factory, qr_id)
            return

        with browser_lock(timeout_sec=lock_timeout):
            while True:
                job_id = self._claim_pending_job()
                if not job_id:
                    break
                logger.info("Publish worker processing job %s (serial queue)", job_id)
                PublishOrchestrator(self.session_factory).publish_job(job_id)

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
        def claim() -> str | None:
            with self.session_factory() as session:
                if has_active_publish_job(session):
                    return None
                now = datetime.utcnow()
                job = (
                    session.query(PublishJob)
                    .filter_by(status="pending")
                    .filter(
                        or_(
                            PublishJob.scheduled_at.is_(None),
                            PublishJob.scheduled_at <= now,
                        )
                    )
                    .order_by(PublishJob.created_at.asc())
                    .first()
                )
                if job is None:
                    return None
                job.status = "uploading"
                job.started_at = datetime.utcnow()
                session.commit()
                return job.id

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
