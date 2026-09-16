"""Tests for publisher account deletion."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.publishing.account_delete import AccountDeleteError, delete_publisher_account
from src.db.engine import Base
from src.db.models.publishing import PublishJob, PublishLog, PublisherAccount
from src.db.models.publishing_metrics import PublishPostMetricSnapshot


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_account_with_job(session) -> str:
    account_id = "acc_del"
    session.add(
        PublisherAccount(
            id=account_id,
            platform="wechat_channels",
            platform_uid="wx1",
            session_path="data/publish/sessions/acc_del.enc",
        )
    )
    job = PublishJob(
        id="job_del",
        account_id=account_id,
        video_path="data/videos/x.mp4",
        title="测试",
        status="published",
        published_at=datetime.utcnow(),
    )
    session.add(job)
    session.add(
        PublishLog(job_id="job_del", message="done"),
    )
    session.add(
        PublishPostMetricSnapshot(
            job_id="job_del",
            account_id=account_id,
            platform="wechat_channels",
            snapshot_date=datetime.utcnow().date(),
            view_count=10,
        )
    )
    session.commit()
    return account_id


def test_delete_publisher_account_cascades_jobs_and_metrics():
    session = _session()
    account_id = _seed_account_with_job(session)

    summary = delete_publisher_account(session, account_id)

    assert summary["jobs_deleted"] == 1
    assert summary["metrics_deleted"] >= 1
    assert session.get(PublisherAccount, account_id) is None
    assert session.get(PublishJob, "job_del") is None
    assert session.query(PublishLog).count() == 0


def test_delete_publisher_account_blocks_uploading_job():
    session = _session()
    account_id = _seed_account_with_job(session)
    job = session.get(PublishJob, "job_del")
    job.status = "uploading"
    session.commit()

    with pytest.raises(AccountDeleteError, match="发布任务进行中"):
        delete_publisher_account(session, account_id)

    assert session.get(PublisherAccount, account_id) is not None


def test_delete_publisher_account_not_found():
    session = _session()
    with pytest.raises(AccountDeleteError, match="不存在"):
        delete_publisher_account(session, "missing")
