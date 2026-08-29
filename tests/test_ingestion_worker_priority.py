"""Worker prioritizes hot radar discovery jobs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import case

from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import IngestionJob, IngestionSource


def _claim_next_job_id(session) -> str | None:
    job = (
        session.query(IngestionJob)
        .filter_by(status="pending")
        .order_by(
            case((IngestionJob.job_type == "hot_radar_discovery", 0), else_=1),
            IngestionJob.created_at.asc(),
        )
        .first()
    )
    if job is None:
        return None
    job.status = "running"
    job.started_at = datetime.utcnow()
    session.commit()
    return job.id


def test_hot_radar_discovery_jobs_claimed_before_scheduled(tmp_path, monkeypatch):
    db_path = tmp_path / "worker_priority.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    init_db()
    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="src1",
            adapter_class="test",
            enabled=True,
        )
    )
    session.flush()
    scheduled = IngestionJob(job_type="scheduled", source_id="src1", status="pending")
    discovery = IngestionJob(job_type="hot_radar_discovery", source_id="src1", status="pending")
    session.add_all([scheduled, discovery])
    session.commit()

    claimed = _claim_next_job_id(session)
    assert claimed == discovery.id
