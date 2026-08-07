from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.job_recovery import recover_stale_publish_jobs, recover_stale_qr_sessions
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount, QrLoginSession


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_marks_stale_uploading_job_failed():
    session = _session()
    session.add(
        PublisherAccount(
            id="a1",
            platform="wechat_channels",
            platform_uid="u1",
            session_path="data/publish/sessions/a1.enc",
        )
    )
    job = PublishJob(
        id="j1",
        account_id="a1",
        video_path="data/videos/x.mp4",
        title="t",
        status="uploading",
        started_at=datetime.utcnow() - timedelta(minutes=20),
    )
    session.add(job)
    session.commit()
    assert recover_stale_publish_jobs(session, stale_minutes=15) == 1
    session.refresh(job)
    assert job.status == "failed"
    assert "重试" in (job.error_message or "")


def test_recent_uploading_job_not_recovered():
    session = _session()
    session.add(
        PublisherAccount(
            id="a1",
            platform="wechat_channels",
            platform_uid="u1",
            session_path="data/publish/sessions/a1.enc",
        )
    )
    job = PublishJob(
        id="j2",
        account_id="a1",
        video_path="data/videos/x.mp4",
        title="t",
        status="uploading",
        started_at=datetime.utcnow() - timedelta(minutes=2),
    )
    session.add(job)
    session.commit()
    assert recover_stale_publish_jobs(session, stale_minutes=15) == 0
    session.refresh(job)
    assert job.status == "uploading"


def test_marks_stale_qr_session_expired():
    session = _session()
    row = QrLoginSession(
        id="q1",
        platform="wechat_channels",
        status="processing",
        created_at=datetime.utcnow() - timedelta(minutes=10),
    )
    session.add(row)
    session.commit()
    assert recover_stale_qr_sessions(session, stale_minutes=5) == 1
    session.refresh(row)
    assert row.status == "expired"
