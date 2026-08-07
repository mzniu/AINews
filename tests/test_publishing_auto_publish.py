from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.publishing.auto_publish import (
    SOURCE_TYPE,
    load_auto_publish_config,
    maybe_enqueue_auto_publish_jobs,
)
from src.db.engine import init_db
from src.db.models.ingestion import IngestedArticle, IngestionSource
from src.db.models.publishing import PublishJob, PublisherAccount


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "auto_publish.db"
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


def _seed_video(tmp_path: Path, article_id: str) -> str:
    video_dir = tmp_path / "data" / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / f"ingested_{article_id}.mp4"
    video_path.write_bytes(b"fake")
    return f"data/videos/{video_path.name}"


def _seed_cover(tmp_path: Path, article_id: str) -> str:
    cover_dir = tmp_path / "data" / "publish" / "covers"
    cover_dir.mkdir(parents=True, exist_ok=True)
    cover_path = cover_dir / f"{article_id}_cover.jpg"
    cover_path.write_bytes(b"fake")
    return f"data/publish/covers/{cover_path.name}"


def _add_account(session, *, account_id: str, platform: str) -> PublisherAccount:
    session_path = f"data/publish/sessions/{account_id}.json"
    account = PublisherAccount(
        id=account_id,
        platform=platform,
        nickname=f"{platform}-nick",
        session_path=session_path,
        status="active",
    )
    session.add(account)
    session.flush()
    return account


def test_load_auto_publish_config_defaults_enabled():
    cfg = load_auto_publish_config({"post_score_automation": {"auto_publish": {}}})
    assert cfg["enabled"] is True
    assert cfg["skip_if_exists"] is True


def test_auto_publish_enqueues_all_platform_accounts(db_session, tmp_path):
    article = IngestedArticle(
        id="art_auto",
        source_id="src1",
        canonical_url="https://example.com/a",
        title="DeepSeek 发布新模型",
        generated_video_path=_seed_video(tmp_path, "art_auto"),
        generated_cover_path=_seed_cover(tmp_path, "art_auto"),
        video_draft_json=json.dumps(
            {
                "main_line1": "突发！DeepSeek 发布",
                "main_line2": "副标题",
                "summary": "摘要内容",
                "tags": "AI,大模型",
            },
            ensure_ascii=False,
        ),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_wx", platform="wechat_channels")
    _add_account(db_session, account_id="acc_dy", platform="douyin")
    _add_account(db_session, account_id="acc_ks", platform="kuaishou")
    _add_account(db_session, account_id="acc_xhs", platform="xiaohongshu")
    db_session.commit()

    result = maybe_enqueue_auto_publish_jobs(db_session, article)
    db_session.commit()

    assert result["enqueued"] is True
    assert len(result["jobs"]) == 4
    jobs = db_session.query(PublishJob).filter_by(source_id="art_auto").all()
    assert len(jobs) == 4
    assert {job.source_type for job in jobs} == {SOURCE_TYPE}
    assert all(job.status == "pending" for job in jobs)


def test_auto_publish_skips_when_disabled(db_session, tmp_path):
    article = IngestedArticle(
        id="art_off",
        source_id="src1",
        canonical_url="https://example.com/b",
        title="标题",
        generated_video_path=_seed_video(tmp_path, "art_off"),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_dy", platform="douyin")
    db_session.commit()

    result = maybe_enqueue_auto_publish_jobs(
        db_session,
        article,
        config={"post_score_automation": {"auto_publish": {"enabled": False}}},
    )
    assert result["skipped"] is True
    assert result["reason"] == "disabled"
    assert db_session.query(PublishJob).count() == 0


def test_auto_publish_skips_duplicate_jobs(db_session, tmp_path):
    article = IngestedArticle(
        id="art_dup",
        source_id="src1",
        canonical_url="https://example.com/c",
        title="标题",
        generated_video_path=_seed_video(tmp_path, "art_dup"),
        video_draft_json=json.dumps({"main_line1": "标题"}, ensure_ascii=False),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_dy", platform="douyin")
    db_session.commit()

    first = maybe_enqueue_auto_publish_jobs(db_session, article)
    db_session.commit()
    second = maybe_enqueue_auto_publish_jobs(db_session, article)
    db_session.commit()

    assert first["enqueued"] is True
    assert second["skipped"] is True
    assert db_session.query(PublishJob).count() == 1
