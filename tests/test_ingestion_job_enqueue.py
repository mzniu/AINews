"""Tests for ingestion job enqueue helpers."""
from __future__ import annotations

from services.ingestion.job_enqueue import enqueue_ingestion_job, find_active_ingestion_job
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestionJob, IngestionSource


def test_enqueue_ingestion_job_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "enqueue.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="Test",
            adapter_class="test",
            enabled=True,
        )
    )
    session.commit()

    job1, created1 = enqueue_ingestion_job(session, source_id="src1", job_type="scheduled")
    job2, created2 = enqueue_ingestion_job(session, source_id="src1", job_type="scheduled")

    assert created1 is True
    assert created2 is False
    assert job1 is not None and job2 is not None
    assert job1.id == job2.id
    assert session.query(IngestionJob).filter_by(source_id="src1").count() == 1
    assert find_active_ingestion_job(session, "src1") is not None
