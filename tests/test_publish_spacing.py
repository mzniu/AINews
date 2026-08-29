"""Tests for auto-publish spacing and quiet hours."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.publishing.auto_publish import maybe_enqueue_auto_publish_jobs
from services.publishing.schedule import (
    INGESTION_SOURCE,
    PublishSpacingConfig,
    clamp_quiet_hours,
    in_quiet_hours,
    load_spacing_config,
    next_auto_slot,
    reschedule_publish_job,
    reshuffle_jobs_in_quiet_window,
)
from services.publishing.worker import PublishWorker
from src.db.engine import Base, init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource
from src.db.models.publishing import PublishJob, PublisherAccount

_AUTO_PUBLISH_CFG = {
    "post_score_automation": {
        "auto_publish": {
            "enabled": True,
            "skip_if_exists": True,
            "min_grade": "S",
            "interval_minutes": 60,
            "quiet_hours": {"enabled": False, "start": "23:00", "end": "07:00"},
        },
        "story_gate": {"enabled": False},
    }
}


def _cfg(**kwargs) -> PublishSpacingConfig:
    return PublishSpacingConfig(
        interval_minutes=kwargs.get("interval_minutes", 60),
        quiet_hours_enabled=kwargs.get("quiet_hours_enabled", False),
        quiet_hours_start=kwargs.get("quiet_hours_start", "23:00"),
        quiet_hours_end=kwargs.get("quiet_hours_end", "07:00"),
    )


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "spacing.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    init_db()
    from src.db.engine import get_session_factory

    session = get_session_factory()()
    session.add(
        IngestionSource(
            id="src1",
            slug="src1",
            display_name="Test",
            adapter_class="aitnt_news",
            enabled=True,
            schedule_cron="0 * * * *",
        )
    )
    session.commit()
    yield session
    session.close()


def _add_account(session, *, account_id: str, platform: str = "douyin") -> PublisherAccount:
    account = PublisherAccount(
        id=account_id,
        platform=platform,
        nickname="nick",
        session_path=f"data/publish/sessions/{account_id}.enc",
        status="active",
    )
    session.add(account)
    session.flush()
    return account


def _seed_video(tmp_path: Path, article_id: str) -> str:
    video_dir = tmp_path / "data" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / f"ingested_{article_id}.mp4"
    video_path.write_bytes(b"fake")
    return f"data/videos/{video_path.name}"


def test_clamp_quiet_cross_midnight_moves_to_next_morning():
    slot = datetime(2026, 8, 28, 15, 30, 0)  # 23:30 Beijing
    out = clamp_quiet_hours(slot, _cfg(quiet_hours_enabled=True))
    assert out == datetime(2026, 8, 28, 23, 0, 0)  # 07:00 Beijing next day


def test_clamp_quiet_same_day_window():
    slot = datetime(2026, 8, 28, 4, 10, 0)  # 12:10 Beijing
    cfg = _cfg(quiet_hours_enabled=True, quiet_hours_start="12:00", quiet_hours_end="13:00")
    assert clamp_quiet_hours(slot, cfg) == datetime(2026, 8, 28, 5, 0, 0)


def test_in_quiet_hours_left_closed_right_open():
    cfg = _cfg(quiet_hours_enabled=True)
    assert in_quiet_hours(datetime(2026, 8, 28, 15, 0, 0), cfg) is True  # 23:00 Beijing
    assert in_quiet_hours(datetime(2026, 8, 28, 23, 0, 0), cfg) is False  # 07:00 Beijing


def test_next_auto_slot_empty_queue_returns_now(db_session):
    now = datetime(2026, 8, 28, 10, 0, 0)
    slot = next_auto_slot(db_session, config=_cfg(), now=now)
    assert slot == now


def test_next_auto_slot_respects_pending_article(db_session):
    t0 = datetime(2026, 8, 28, 8, 0, 0)
    _add_account(db_session, account_id="a1")
    db_session.add(
        PublishJob(
            account_id="a1",
            video_path="data/videos/a.mp4",
            title="A",
            status="pending",
            source_type=INGESTION_SOURCE,
            source_id="art-a",
            scheduled_at=t0,
        )
    )
    db_session.commit()
    slot = next_auto_slot(db_session, config=_cfg(interval_minutes=60), now=t0)
    assert slot >= t0 + timedelta(minutes=60)


def test_next_auto_slot_after_last_success(db_session):
    t0 = datetime(2026, 8, 28, 8, 0, 0)
    _add_account(db_session, account_id="a1")
    db_session.add(
        PublishJob(
            account_id="a1",
            video_path="data/videos/a.mp4",
            title="A",
            status="published",
            published_at=t0,
            source_type=INGESTION_SOURCE,
            source_id="art-old",
        )
    )
    db_session.commit()
    slot = next_auto_slot(
        db_session,
        config=_cfg(interval_minutes=60),
        now=t0 + timedelta(minutes=30),
    )
    assert slot == t0 + timedelta(minutes=60)


def test_quiet_hours_enqueue_spacing(db_session):
    cfg = _cfg(quiet_hours_enabled=True, interval_minutes=60)
    night = datetime(2026, 8, 28, 15, 30, 0)  # 23:30 Beijing
    first = next_auto_slot(db_session, config=cfg, now=night)
    assert first == datetime(2026, 8, 28, 23, 0, 0)
    _add_account(db_session, account_id="a1")
    db_session.add(
        PublishJob(
            account_id="a1",
            video_path="data/videos/a.mp4",
            title="A",
            status="pending",
            source_type=INGESTION_SOURCE,
            source_id="art-1",
            scheduled_at=first,
        )
    )
    db_session.commit()
    second = next_auto_slot(db_session, config=cfg, now=night)
    assert second == datetime(2026, 8, 29, 0, 0, 0)  # 08:00 Beijing


def test_load_spacing_config_defaults():
    cfg = load_spacing_config(_AUTO_PUBLISH_CFG)
    assert cfg.interval_minutes == 60
    assert cfg.quiet_hours_enabled is False


def test_auto_enqueue_sets_scheduled_at(db_session, tmp_path):
    article = IngestedArticle(
        id="art_slot",
        source_id="src1",
        canonical_url="https://example.com/s",
        title="标题",
        score_grade="S",
        score_total=90.0,
        generated_video_path=_seed_video(tmp_path, "art_slot"),
        video_draft_json=json.dumps({"main_line1": "标题"}, ensure_ascii=False),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_dy")
    db_session.commit()

    result = maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
    jobs = db_session.query(PublishJob).filter_by(source_id="art_slot").all()
    assert result.get("enqueued")
    assert jobs
    assert all(job.scheduled_at is not None for job in jobs)
    assert len({job.scheduled_at for job in jobs}) == 1


def test_auto_enqueue_staggered_articles(db_session, tmp_path, monkeypatch):
    fixed_now = datetime(2026, 8, 28, 10, 0, 0)
    monkeypatch.setattr("services.publishing.schedule.datetime", type("DT", (), {
        "utcnow": staticmethod(lambda: fixed_now),
        "combine": staticmethod(datetime.combine),
    }))

    _add_account(db_session, account_id="acc_dy")
    for idx in ("art1", "art2"):
        article = IngestedArticle(
            id=idx,
            source_id="src1",
            canonical_url=f"https://example.com/{idx}",
            title=idx,
            score_grade="S",
            score_total=90.0,
            generated_video_path=_seed_video(tmp_path, idx),
            video_draft_json=json.dumps({"main_line1": idx}, ensure_ascii=False),
        )
        db_session.add(article)
        db_session.commit()
        maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
        db_session.commit()

    slots = [
        row[0]
        for row in db_session.query(PublishJob.scheduled_at)
        .filter(PublishJob.source_id.in_(("art1", "art2")))
        .distinct()
        .all()
    ]
    assert len(slots) == 2
    assert max(slots) - min(slots) >= timedelta(minutes=60)


def test_reschedule_cascade(db_session):
    _add_account(db_session, account_id="a1")
    now = datetime.utcnow()
    t1 = now + timedelta(hours=1)
    t2 = now + timedelta(hours=2)
    j1 = PublishJob(
        account_id="a1",
        video_path="data/videos/1.mp4",
        title="1",
        status="pending",
        source_type=INGESTION_SOURCE,
        source_id="art-1",
        scheduled_at=t1,
    )
    j2 = PublishJob(
        account_id="a1",
        video_path="data/videos/2.mp4",
        title="2",
        status="pending",
        source_type=INGESTION_SOURCE,
        source_id="art-2",
        scheduled_at=t2,
    )
    db_session.add_all([j1, j2])
    db_session.commit()

    new_t1 = now + timedelta(hours=4)
    result = reschedule_publish_job(
        db_session,
        j1,
        new_t1,
        config=_cfg(),
        cascade=True,
    )
    db_session.commit()
    assert result["job_id"] == j1.id
    j2_slot = (
        db_session.query(PublishJob.scheduled_at)
        .filter_by(source_id="art-2")
        .scalar()
    )
    assert j2_slot >= new_t1 + timedelta(minutes=60)


def test_worker_skips_ingestion_in_quiet_hours(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    session.add(
        PublisherAccount(
            id="acc1",
            platform="douyin",
            nickname="n",
            session_path="data/publish/sessions/acc1.enc",
            status="active",
        )
    )
    session.add(
        PublishJob(
            id="auto1",
            account_id="acc1",
            video_path="data/videos/a.mp4",
            title="auto",
            status="pending",
            source_type=INGESTION_SOURCE,
            source_id="art-1",
            scheduled_at=datetime.utcnow() - timedelta(minutes=1),
        )
    )
    session.add(
        PublishJob(
            id="manual1",
            account_id="acc1",
            video_path="data/videos/b.mp4",
            title="manual",
            status="pending",
            scheduled_at=datetime.utcnow() - timedelta(minutes=1),
        )
    )
    session.commit()
    session.close()

    monkeypatch.setattr(
        "services.publishing.schedule.in_quiet_hours",
        lambda _now, _cfg: True,
    )
    worker = PublishWorker(embedded=True)
    worker.session_factory = factory
    claimed = worker._claim_pending_job()
    assert claimed == "manual1"


def test_settings_interval_validation(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    from services.ingestion.scoring_settings import save_auto_publish_settings

    with pytest.raises(ValueError):
        save_auto_publish_settings(interval_minutes=5)


def test_reshuffle_jobs_in_quiet_window(db_session):
    _add_account(db_session, account_id="a1")
    inside = datetime(2026, 8, 28, 16, 0, 0)  # 00:00 Beijing
    db_session.add(
        PublishJob(
            account_id="a1",
            video_path="data/videos/a.mp4",
            title="A",
            status="pending",
            source_type=INGESTION_SOURCE,
            source_id="art-night",
            scheduled_at=inside,
        )
    )
    db_session.commit()
    cfg = _cfg(quiet_hours_enabled=True)
    updated = reshuffle_jobs_in_quiet_window(db_session, config=cfg)
    db_session.flush()
    assert updated
    new_slot = (
        db_session.query(PublishJob.scheduled_at)
        .filter_by(source_id="art-night")
        .scalar()
    )
    assert new_slot is not None
    assert not in_quiet_hours(new_slot, cfg)
