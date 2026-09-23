"""PublishJob playbook columns and stamp_playbook."""
from __future__ import annotations

import pytest

from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import PublishJob, PublisherAccount


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "stamp.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    init_db()
    session = get_session_factory()()
    session.add(
        PublisherAccount(
            id="acc",
            platform="douyin",
            session_path="data/publish/sessions/acc.json",
            status="active",
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_publish_job_inserts_with_null_playbook_columns(db_session):
    job = PublishJob(
        account_id="acc",
        video_path="data/videos/a.mp4",
        title="标题",
    )
    db_session.add(job)
    db_session.commit()
    assert job.playbook_version_id is None
    assert job.copy_draft_id is None
    assert job.playbook_attribution is None


def test_stamp_playbook_keeps_edited_version():
    from services.publishing.playbook_stamp import stamp_playbook

    job = PublishJob(account_id="a", video_path="v.mp4", title="t")
    stamp_playbook(
        job,
        {
            "playbook_attribution": "edited",
            "playbook_version_id": "ver1",
            "copy_draft_id": "draft1",
        },
    )
    assert job.playbook_attribution == "edited"
    assert job.playbook_version_id == "ver1"
    assert job.copy_draft_id == "draft1"


def test_stamp_rejects_constitution_string():
    from services.publishing.playbook_stamp import stamp_playbook

    job = PublishJob(account_id="a", video_path="v.mp4", title="t")
    with pytest.raises(ValueError):
        stamp_playbook(job, {"playbook_version_id": "constitution"})


def test_stamp_fact_gate_fallback_has_null_version():
    from services.publishing.playbook_stamp import stamp_playbook

    job = PublishJob(account_id="a", video_path="v.mp4", title="t")
    stamp_playbook(job, {"playbook_attribution": "fact_gate_fallback"})
    assert job.playbook_version_id is None
    assert job.copy_draft_id is None
    assert job.playbook_attribution == "fact_gate_fallback"


def test_stamp_playbook_requires_draft_id():
    from services.publishing.playbook_stamp import stamp_playbook

    job = PublishJob(account_id="a", video_path="v.mp4", title="t")
    with pytest.raises(ValueError):
        stamp_playbook(
            job,
            {"playbook_attribution": "playbook", "playbook_version_id": "ver1"},
        )
