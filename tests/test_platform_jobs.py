from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.publishing.auto_publish import maybe_enqueue_auto_publish_jobs
from services.publishing.platform_jobs import update_job_platforms
from src.db.engine import init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource
from src.db.models.publishing import PublishJob, PublisherAccount

_AUTO_PUBLISH_CFG = {
    "post_score_automation": {
        "auto_publish": {"enabled": True, "skip_if_exists": True, "min_grade": "S"},
        "story_gate": {"enabled": False},
    }
}


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "platform_jobs.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
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


def _seed_video(tmp_path: Path, article_id: str) -> str:
    video_dir = tmp_path / "data" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / f"ingested_{article_id}.mp4"
    video_path.write_bytes(b"fake")
    return f"data/videos/{video_path.name}"


def _add_account(session, *, account_id: str, platform: str, status: str = "active") -> PublisherAccount:
    account = PublisherAccount(
        id=account_id,
        platform=platform,
        nickname=f"{platform}-nick",
        session_path=f"data/publish/sessions/{account_id}.json",
        status=status,
    )
    session.add(account)
    session.flush()
    return account


def test_auto_publish_legacy_path_excludes_expired_account(db_session, tmp_path):
    article = IngestedArticle(
        id="art_expired",
        source_id="src1",
        canonical_url="https://example.com/a",
        title="标题",
        score_grade="S",
        score_total=90.0,
        generated_video_path=_seed_video(tmp_path, "art_expired"),
        video_draft_json=json.dumps({"main_line1": "标题"}, ensure_ascii=False),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_dy", platform="douyin", status="expired")
    db_session.commit()

    result = maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
    db_session.commit()

    assert result == {"skipped": True, "reason": "no_active_accounts"}
    assert db_session.query(PublishJob).count() == 0


def test_update_job_platforms_adds_and_removes(db_session, tmp_path):
    article = IngestedArticle(
        id="art_platforms",
        source_id="src1",
        canonical_url="https://example.com/b",
        title="多平台文章",
        score_grade="S",
        score_total=90.0,
        generated_video_path=_seed_video(tmp_path, "art_platforms"),
        video_draft_json=json.dumps({"main_line1": "多平台文章"}, ensure_ascii=False),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_dy", platform="douyin")
    _add_account(db_session, account_id="acc_wx", platform="wechat_channels")
    _add_account(db_session, account_id="acc_ks", platform="kuaishou")
    db_session.commit()

    enqueue = maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
    db_session.commit()
    assert enqueue["enqueued"] is True

    jobs = db_session.query(PublishJob).filter_by(source_id="art_platforms").all()
    assert len(jobs) == 3
    reference_job = jobs[0]

    result = update_job_platforms(
        db_session,
        reference_job.id,
        ["douyin", "wechat_channels"],
    )
    db_session.commit()

    assert set(result["kept"]) == {"douyin", "wechat_channels"}
    assert result["cancelled"] == ["kuaishou"]
    active = (
        db_session.query(PublishJob)
        .filter(PublishJob.source_id == "art_platforms", PublishJob.status.in_(("pending", "uploading")))
        .all()
    )
    assert len(active) == 2

    add_back = update_job_platforms(
        db_session,
        reference_job.id,
        ["douyin", "wechat_channels", "kuaishou"],
    )
    db_session.commit()
    assert len(add_back["created"]) == 1
    assert add_back["created"][0]["platform"] == "kuaishou"
