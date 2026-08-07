"""Tests for scheduled publish job claiming."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.worker import PublishWorker
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublisherAccount


def test_claim_pending_job_skips_future_scheduled():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    session.add(
        PublisherAccount(
            id="acc1",
            platform="wechat_channels",
            nickname="测试",
            platform_uid="uid1",
            session_path="data/publish/sessions/acc1.enc",
        )
    )
    session.add(
        PublishJob(
            id="future",
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="定时",
            status="pending",
            scheduled_at=datetime.utcnow() + timedelta(hours=2),
        )
    )
    session.add(
        PublishJob(
            id="due",
            account_id="acc1",
            video_path="data/videos/b.mp4",
            title="立即",
            status="pending",
            scheduled_at=datetime.utcnow() - timedelta(minutes=1),
        )
    )
    session.commit()
    session.close()

    worker = PublishWorker(embedded=True)
    worker.session_factory = factory
    claimed = worker._claim_pending_job()
    assert claimed == "due"


def test_claim_pending_job_includes_no_schedule():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    session.add(
        PublisherAccount(
            id="acc1",
            platform="wechat_channels",
            nickname="测试",
            platform_uid="uid1",
            session_path="data/publish/sessions/acc1.enc",
        )
    )
    session.add(
        PublishJob(
            id="now",
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="立即",
            status="pending",
        )
    )
    session.commit()
    session.close()

    worker = PublishWorker(embedded=True)
    worker.session_factory = factory
    assert worker._claim_pending_job() == "now"


def test_claim_pending_job_skips_when_another_uploading():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    session.add(
        PublisherAccount(
            id="acc1",
            platform="wechat_channels",
            nickname="测试",
            platform_uid="uid1",
            session_path="data/publish/sessions/acc1.enc",
        )
    )
    session.add(
        PublishJob(
            id="uploading",
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="进行中",
            status="uploading",
            started_at=datetime.utcnow(),
        )
    )
    session.add(
        PublishJob(
            id="pending",
            account_id="acc1",
            video_path="data/videos/b.mp4",
            title="等待",
            status="pending",
        )
    )
    session.commit()
    session.close()

    worker = PublishWorker(embedded=True)
    worker.session_factory = factory
    assert worker._claim_pending_job() is None
