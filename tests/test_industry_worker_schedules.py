"""M0b: ingestion worker cron jobs follow effective pack-enabled sources."""
from __future__ import annotations

import pytest

import src.db.engine as engine_mod
from services.industry.config_loader import build_effective_config, write_effective_cache
from services.industry.constants import DEFAULT_INDUSTRY_ID
from services.ingestion.registry import sync_sources_to_db
from services.ingestion.worker import (
    IngestionWorker,
    SCHEDULE_RELOAD_FLAG,
    request_ingestion_schedule_reload,
)
from src.db.engine import get_session_factory, init_db


def _reset_db_engine() -> None:
    engine_mod._engine = None
    engine_mod._SessionLocal = None


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "ainews.db"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    _reset_db_engine()
    init_db()
    session = get_session_factory()()
    yield session
    session.close()
    _reset_db_engine()


def test_worker_registers_schedules_only_for_pack_enabled_sources(
    db_session, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        build_effective_config(DEFAULT_INDUSTRY_ID),
        manifest_hash="test",
    )
    sync_sources_to_db(db_session)

    worker = IngestionWorker(embedded=True)
    worker._register_schedules(db_session)

    job_ids = {job.id for job in worker.scheduler.get_jobs()}
    assert "schedule_kr36_ai" in job_ids
    assert "schedule_qbitai" in job_ids
    assert "schedule_aitnt_travel" not in job_ids


def test_refresh_schedules_rebuilds_jobs_after_effective_cache_changes(
    db_session, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        build_effective_config(DEFAULT_INDUSTRY_ID),
        manifest_hash="v1",
    )
    sync_sources_to_db(db_session)

    worker = IngestionWorker(embedded=True)
    worker.scheduler.start()
    try:
        worker._register_schedules(db_session)
        assert "schedule_aitnt_travel" not in {
            j.id for j in worker.scheduler.get_jobs()
        }

        effective = build_effective_config(DEFAULT_INDUSTRY_ID)
        for source in effective["ingestion"]["sources"]:
            source["enabled"] = source.get("id") == "kr36_ai"
        write_effective_cache(DEFAULT_INDUSTRY_ID, effective, manifest_hash="v2")
        sync_sources_to_db(db_session)
        worker.refresh_schedules()

        schedule_ids = {
            j.id for j in worker.scheduler.get_jobs() if j.id.startswith("schedule_")
        }
        assert schedule_ids == {"schedule_kr36_ai"}
        assert "poll_ingestion" in {j.id for j in worker.scheduler.get_jobs()}
    finally:
        worker.scheduler.shutdown(wait=False)


def test_poll_jobs_consumes_schedule_reload_flag(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)
    write_effective_cache(
        DEFAULT_INDUSTRY_ID,
        build_effective_config(DEFAULT_INDUSTRY_ID),
        manifest_hash="test",
    )
    sync_sources_to_db(db_session)
    if SCHEDULE_RELOAD_FLAG.is_file():
        SCHEDULE_RELOAD_FLAG.unlink()

    worker = IngestionWorker(embedded=True)
    worker.scheduler.start()
    try:
        worker._register_schedules(db_session)
        request_ingestion_schedule_reload()
        assert SCHEDULE_RELOAD_FLAG.is_file()
        worker.poll_jobs()
        assert not SCHEDULE_RELOAD_FLAG.is_file()
    finally:
        worker.scheduler.shutdown(wait=False)
