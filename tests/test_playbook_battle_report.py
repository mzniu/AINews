"""Battle report: 72h snapshot, zero likes kept, learn-again is playbook only."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services.copy_agent.battle_report import build_battle_report
from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import PublishJob, PublisherAccount
from src.db.models.publishing_metrics import PublishPostMetricSnapshot


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "battle.db"
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


def _job(session, job_id, attribution, version_id, *, published_at):
    session.add(
        PublishJob(
            id=job_id,
            account_id="acc",
            video_path="data/videos/a.mp4",
            title=job_id,
            playbook_attribution=attribution,
            playbook_version_id=version_id,
            copy_draft_id="draft" if version_id else None,
            published_at=published_at,
            status="published",
        )
    )


def test_zero_likes_stay_and_learn_again_is_playbook_only(db_session):
    published = datetime(2026, 9, 1, 8, 0, 0)
    _job(db_session, "play", "playbook", "ver1", published_at=published)
    _job(db_session, "edit", "edited", "ver1", published_at=published)
    _job(db_session, "fall", "fact_gate_fallback", None, published_at=published)
    db_session.add(
        PublishPostMetricSnapshot(
            job_id="play",
            account_id="acc",
            platform="douyin",
            snapshot_date=published.date(),
            share_count=4,
            like_count=0,
            fetched_at=published + timedelta(hours=10),
        )
    )
    db_session.add(
        PublishPostMetricSnapshot(
            job_id="edit",
            account_id="acc",
            platform="douyin",
            snapshot_date=published.date(),
            share_count=5,
            like_count=10,
            fetched_at=published + timedelta(hours=80),
        )
    )
    db_session.commit()

    report = build_battle_report(db_session)
    by_attr = {row["attribution"]: row for row in report["rows"]}
    assert set(by_attr) == {"playbook", "edited", "fact_gate_fallback"}
    assert by_attr["playbook"]["ratio"] is None
    assert by_attr["playbook"]["ratio_note"] == "无赞，未算比率"
    assert by_attr["playbook"]["share_count"] == 4
    assert by_attr["edited"]["share_count"] is None
    assert [row["attribution"] for row in report["learn_again"]] == ["playbook"]
