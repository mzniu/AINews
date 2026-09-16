"""Ingestion worker: scheduler + job consumer (embedded or separate process)."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger
from sqlalchemy import case
from sqlalchemy.orm import Session

from services.ingestion.db_retry import run_with_sqlite_retry
from services.ingestion.job_recovery import recover_stale_jobs
from services.ingestion.orchestrator import IngestionOrchestrator
from services.ingestion.registry import sync_sources_to_db
from services.ingestion.settings import load_merged_ingestion_config
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestionJob, IngestionSource
from src.utils.config import Config

HEARTBEAT_PATH = Config.DATA_DIR / "ingestion" / "worker_heartbeat"

_embedded_instance: "IngestionWorker | None" = None


def get_ingestion_worker_mode() -> str:
    mode = os.getenv("INGESTION_WORKER_MODE", "embedded").strip().lower()
    return mode if mode in {"embedded", "separate"} else "embedded"


def is_embedded_ingestion_worker_running() -> bool:
    worker = _embedded_instance
    return worker is not None and worker.scheduler.running


class IngestionWorker:
    def __init__(self, *, embedded: bool) -> None:
        self.embedded = embedded
        if not embedded:
            init_db()
        self.session_factory = get_session_factory()
        self._poll_lock = threading.Lock()
        scheduler_cls = BackgroundScheduler if embedded else BlockingScheduler
        self.scheduler = scheduler_cls(timezone="Asia/Shanghai")

    def _poll_interval(self) -> int:
        cfg = load_merged_ingestion_config()
        return max(3, int((cfg.get("worker") or {}).get("poll_interval_sec", 5)))

    def _register_poll_job(self) -> None:
        interval = self._poll_interval()
        self.scheduler.add_job(
            self.poll_jobs,
            "interval",
            seconds=interval,
            id="poll_ingestion",
            max_instances=1,
            replace_existing=True,
        )

    def _register_schedules(self, session: Session) -> None:
        from apscheduler.triggers.cron import CronTrigger

        for source in session.query(IngestionSource).filter_by(enabled=True).all():
            cron = source.schedule_cron or "0 * * * *"
            self.scheduler.add_job(
                self._enqueue_scheduled,
                CronTrigger.from_crontab(cron),
                args=[source.id],
                id=f"schedule_{source.id}",
                replace_existing=True,
                max_instances=1,
            )
            logger.info(f"Registered ingestion schedule for {source.id}: {cron}")

    def _register_hot_radar_schedule(self) -> None:
        from apscheduler.triggers.cron import CronTrigger

        from services.ingestion.hot_radar_settings import load_hot_radar_config

        cfg = load_hot_radar_config()
        if not cfg.get("enabled", True):
            return
        cron = str(cfg.get("refresh_cron") or "0 8 * * *")
        self.scheduler.add_job(
            self._refresh_hot_radar,
            CronTrigger.from_crontab(cron),
            id="hot_radar_refresh",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"Registered hot radar refresh: {cron}")

    def _refresh_hot_radar(self) -> None:
        from services.ingestion.hot_radar_service import refresh_hot_radar

        try:
            with self.session_factory() as session:
                result = refresh_hot_radar(session, force=True)
                if result.get("status") == "refreshed":
                    logger.info(f"Hot radar refresh ok: {result.get('item_count')} items")
        except Exception as exc:
            logger.warning(f"Hot radar refresh job failed: {exc}")

    def refresh_schedules(self) -> None:
        if not self.scheduler.running:
            return
        for job in list(self.scheduler.get_jobs()):
            if job.id.startswith("schedule_") or job.id == "hot_radar_refresh":
                self.scheduler.remove_job(job.id)
        with self.session_factory() as session:
            sync_sources_to_db(session)
            self._register_schedules(session)
        self._register_hot_radar_schedule()
        self._register_poll_job()
        self._touch_heartbeat()
        logger.info("Ingestion worker schedules refreshed")

    def start_embedded(self) -> None:
        global _embedded_instance
        if self.scheduler.running:
            return
        with self.session_factory() as session:
            sync_sources_to_db(session)
            recovered = recover_stale_jobs(session)
            if recovered:
                logger.warning(f"Recovered {recovered} stale ingestion job(s)")
            self._register_schedules(session)
        self._register_hot_radar_schedule()
        self._register_poll_job()
        self.scheduler.start()
        _embedded_instance = self
        self._touch_heartbeat()
        logger.info("Ingestion worker started (embedded in web_server)")

    def shutdown(self) -> None:
        global _embedded_instance
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Ingestion worker stopped (embedded)")
        if _embedded_instance is self:
            _embedded_instance = None

    def start(self) -> None:
        """Blocking: for `python -m services.ingestion.worker`."""
        with self.session_factory() as session:
            sync_sources_to_db(session)
            recovered = recover_stale_jobs(session)
            if recovered:
                logger.warning(f"Recovered {recovered} stale ingestion job(s)")
            self._register_schedules(session)
        self._register_hot_radar_schedule()
        self._register_poll_job()
        logger.info("Ingestion worker started (separate process)")
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Ingestion worker stopped")

    def _touch_heartbeat(self) -> None:
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_PATH.write_text(datetime.utcnow().isoformat(), encoding="utf-8")

    def _enqueue_scheduled(self, source_id: str) -> None:
        from services.ingestion.job_enqueue import enqueue_ingestion_job

        try:
            with self.session_factory() as session:
                job, created = enqueue_ingestion_job(
                    session,
                    source_id=source_id,
                    job_type="scheduled",
                )
                if created and job is not None:
                    logger.info(f"Enqueued scheduled job for {source_id}")
        except Exception as exc:
            logger.warning(f"Scheduled enqueue failed for {source_id}: {exc}")

    def poll_jobs(self) -> None:
        """Fast scheduler tick: heartbeat + kick off background work if idle."""
        self._touch_heartbeat()
        if not self._poll_lock.acquire(blocking=False):
            return

        def _run() -> None:
            try:
                self._poll_media_jobs()
                self._process_next_ingestion_job()
            finally:
                self._poll_lock.release()

        threading.Thread(target=_run, daemon=True, name="ingestion-poll").start()

    def _process_next_ingestion_job(self) -> None:
        job_id: str | None = None
        source_id: str | None = None

        def claim_job() -> tuple[str, str, str, str] | None:
            with self.session_factory() as session:
                recover_stale_jobs(session)
                job = (
                    session.query(IngestionJob)
                    .filter_by(status="pending")
                    .order_by(
                        case(
                            (IngestionJob.job_type.in_(("hot_radar_discovery", "article_recrawl")), 0),
                            else_=1,
                        ),
                        IngestionJob.created_at.asc(),
                    )
                    .first()
                )
                if not job:
                    return None
                job.status = "running"
                job.started_at = datetime.utcnow()
                session.commit()
                return job.id, job.source_id, job.job_type, job.payload_json

        claimed = run_with_sqlite_retry(claim_job)
        if not claimed:
            return
        job_id, source_id, job_type, payload_json = claimed

        try:
            with self.session_factory() as session:
                if job_type == "hot_radar_discovery":
                    payload = json.loads(payload_json or "{}")
                    stats = IngestionOrchestrator(session).ingest_url(
                        payload.get("source_id") or source_id,
                        payload.get("url") or "",
                        title=payload.get("title"),
                        job_id=job_id,
                    )
                elif job_type == "article_recrawl":
                    payload = json.loads(payload_json or "{}")
                    stats = IngestionOrchestrator(session).recrawl_article(
                        payload.get("article_id") or "",
                        job_id=job_id,
                    )
                else:
                    stats = IngestionOrchestrator(session).run_source(source_id, job_id=job_id)

            def mark_finished() -> None:
                with self.session_factory() as session:
                    job = session.get(IngestionJob, job_id)
                    if job:
                        failed = job_type in ("hot_radar_discovery", "article_recrawl") and bool(
                            stats.get("failed")
                        )
                        job.status = "failed" if failed else "succeeded"
                        job.finished_at = datetime.utcnow()
                        if failed:
                            errors = stats.get("errors") or []
                            if errors and isinstance(errors[0], dict):
                                job.error_message = str(errors[0].get("error") or errors[0])
                            elif errors:
                                job.error_message = str(errors[0])
                        try:
                            original = json.loads(payload_json or "{}")
                        except json.JSONDecodeError:
                            original = {}
                        if isinstance(original, dict):
                            original["result"] = stats
                            job.payload_json = json.dumps(original, ensure_ascii=False)
                        else:
                            job.payload_json = json.dumps(stats, ensure_ascii=False)
                        session.commit()

            run_with_sqlite_retry(mark_finished)
            logger.info(f"Ingestion job {job_id} done: {stats}")
        except Exception as exc:
            logger.exception(f"Ingestion job {job_id} failed: {exc}")

            def mark_failed() -> None:
                with self.session_factory() as session:
                    job = session.get(IngestionJob, job_id)
                    if job:
                        job.status = "failed"
                        job.finished_at = datetime.utcnow()
                        job.error_message = str(exc)
                        session.commit()

            try:
                run_with_sqlite_retry(mark_failed)
            except Exception as mark_exc:
                logger.exception(f"Failed to mark ingestion job {job_id} as failed: {mark_exc}")

    def _poll_media_jobs(self) -> None:
        from services.ingestion.media_job_service import process_next_media_job

        def run_one() -> dict | None:
            with self.session_factory() as session:
                return process_next_media_job(session)

        try:
            while True:
                result = run_with_sqlite_retry(run_one)
                if not result:
                    break
                logger.info(f"Media job finished: {result}")
        except Exception as exc:
            logger.exception(f"Media job poll failed: {exc}")


def main() -> None:
    from src.utils.logger import configure_logging

    configure_logging()
    IngestionWorker(embedded=False).start()


if __name__ == "__main__":
    main()
