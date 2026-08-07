"""Job recovery tests."""
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.engine import Base
from src.db.models.ingestion import CrawlRun, IngestionJob, IngestionSource
from services.ingestion.job_recovery import recover_stale_jobs


def test_recovers_running_job_when_crawl_finished():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        IngestionSource(
            id="kr36_ai",
            slug="kr36_ai",
            display_name="36kr",
            adapter_class="kr36_news",
            config_json="{}",
        )
    )
    job = IngestionJob(id="job1", job_type="verify", source_id="kr36_ai", status="running")
    session.add(job)
    session.add(
        CrawlRun(
            job_id="job1",
            source_id="kr36_ai",
            status="succeeded",
            finished_at=datetime.utcnow(),
            stats_json='{"new": 1}',
        )
    )
    session.commit()

    assert recover_stale_jobs(session) == 1
    session.refresh(job)
    assert job.status == "succeeded"
    assert job.payload_json == '{"new": 1}'


def test_marks_stale_running_job_failed():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        IngestionSource(
            id="kr36_ai",
            slug="kr36_ai",
            display_name="36kr",
            adapter_class="kr36_news",
            config_json="{}",
        )
    )
    job = IngestionJob(
        id="job2",
        job_type="manual",
        source_id="kr36_ai",
        status="running",
        created_at=datetime.utcnow() - timedelta(hours=2),
    )
    session.add(job)
    session.commit()

    assert recover_stale_jobs(session, stale_minutes=30) == 1
    session.refresh(job)
    assert job.status == "failed"
    assert "回收" in (job.error_message or "")
