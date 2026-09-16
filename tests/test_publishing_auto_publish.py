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

_AUTO_PUBLISH_CFG = {
    "post_score_automation": {
        "auto_publish": {"enabled": True, "skip_if_exists": True, "min_grade": "S"},
        "story_gate": {"enabled": False},
    }
}


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "auto_publish.db"
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
    assert cfg["min_grade"] == "S"


def test_auto_publish_enqueues_all_platform_accounts(db_session, tmp_path):
    article = IngestedArticle(
        id="art_auto",
        source_id="src1",
        canonical_url="https://example.com/a",
        title="DeepSeek 发布新模型",
        score_grade="S",
        score_total=88.0,
        generated_video_path=_seed_video(tmp_path, "art_auto"),
        generated_cover_path=_seed_cover(tmp_path, "art_auto"),
        video_draft_json=json.dumps(
            {
                "main_line1": "突发！DeepSeek 发布",
                "short_title": "DeepSeek发布",
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

    result = maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
    db_session.commit()

    assert result["enqueued"] is True
    assert len(result["jobs"]) == 4
    jobs = db_session.query(PublishJob).filter_by(source_id="art_auto").all()
    assert len(jobs) == 4
    assert {job.source_type for job in jobs} == {SOURCE_TYPE}
    assert all(job.status == "pending" for job in jobs)
    titles = {job.account_id: job.title for job in jobs}
    assert titles["acc_wx"] == "DeepSeek发布"
    assert titles["acc_dy"] == "突发！DeepSeek 发布"


def test_auto_publish_skips_when_disabled(db_session, tmp_path):
    article = IngestedArticle(
        id="art_off",
        source_id="src1",
        canonical_url="https://example.com/b",
        title="标题",
        score_grade="S",
        score_total=90.0,
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


def test_policy_disabled_legacy_path_skips_inactive_only_accounts(
    db_session, tmp_path
):
    article = IngestedArticle(
        id="art_inactive",
        source_id="src1",
        canonical_url="https://example.com/inactive",
        title="标题",
        score_grade="S",
        score_total=90.0,
        generated_video_path=_seed_video(tmp_path, "art_inactive"),
    )
    db_session.add(article)
    db_session.add(
        PublisherAccount(
            id="inactive-dy",
            platform="douyin",
            nickname="inactive",
            session_path="data/publish/sessions/inactive.json",
            status="expired",
        )
    )
    db_session.commit()

    result = maybe_enqueue_auto_publish_jobs(
        db_session, article, config=_AUTO_PUBLISH_CFG
    )

    assert result == {"skipped": True, "reason": "no_active_accounts"}
    assert db_session.query(PublishJob).count() == 0


def test_auto_publish_skips_duplicate_jobs(db_session, tmp_path):
    article = IngestedArticle(
        id="art_dup",
        source_id="src1",
        canonical_url="https://example.com/c",
        title="标题",
        score_grade="S",
        score_total=90.0,
        generated_video_path=_seed_video(tmp_path, "art_dup"),
        video_draft_json=json.dumps({"main_line1": "标题"}, ensure_ascii=False),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_dy", platform="douyin")
    db_session.commit()

    first = maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
    db_session.commit()
    second = maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
    db_session.commit()

    assert first["enqueued"] is True
    assert second["skipped"] is True
    assert db_session.query(PublishJob).count() == 1


def test_auto_publish_skips_below_min_grade(db_session, tmp_path):
    article = IngestedArticle(
        id="art_b",
        source_id="src1",
        canonical_url="https://example.com/d",
        title="B级文章",
        score_grade="B",
        score_total=60.0,
        generated_video_path=_seed_video(tmp_path, "art_b"),
        video_draft_json=json.dumps({"main_line1": "标题"}, ensure_ascii=False),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_dy", platform="douyin")
    db_session.commit()

    result = maybe_enqueue_auto_publish_jobs(
        db_session,
        article,
        config={"post_score_automation": {"auto_publish": {"enabled": True, "min_grade": "A"}}},
    )
    assert result["skipped"] is True
    assert result["reason"] == "grade_below_threshold"
    assert db_session.query(PublishJob).count() == 0


def test_auto_publish_allows_grade_at_threshold(db_session, tmp_path):
    article = IngestedArticle(
        id="art_a",
        source_id="src1",
        canonical_url="https://example.com/e",
        title="A级文章",
        score_grade="A",
        score_total=75.0,
        generated_video_path=_seed_video(tmp_path, "art_a"),
        video_draft_json=json.dumps({"main_line1": "标题"}, ensure_ascii=False),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc_dy", platform="douyin")
    db_session.commit()

    result = maybe_enqueue_auto_publish_jobs(
        db_session,
        article,
        config={"post_score_automation": {"auto_publish": {"enabled": True, "min_grade": "A"}}},
    )
    assert result["enqueued"] is True
    assert db_session.query(PublishJob).count() == 1


def test_enabled_publish_policy_returns_candidate_result_without_direct_jobs(
    db_session, tmp_path, monkeypatch
):
    article = IngestedArticle(
        id="art_policy",
        source_id="src1",
        canonical_url="https://example.com/policy",
        title="候选队列",
        score_grade="A",
        score_total=75.0,
        generated_video_path=_seed_video(tmp_path, "art_policy"),
    )
    db_session.add(article)
    db_session.commit()
    expected = {
        "candidate_evaluation": True,
        "candidates": [{"platform": "douyin", "status": "pending"}],
    }
    monkeypatch.setattr(
        "services.publishing.candidate_queue.evaluate_article_candidates",
        lambda session, candidate_article, config: expected,
    )

    result = maybe_enqueue_auto_publish_jobs(
        db_session,
        article,
        config={
            "publish_policy": {"enabled": True},
            "post_score_automation": {"auto_publish": {"enabled": True}},
        },
    )

    assert result == expected
    assert db_session.query(PublishJob).count() == 0


def test_killed_platform_falls_back_to_legacy_enqueue_while_keeping_candidates(
    db_session, tmp_path, monkeypatch
):
    article = IngestedArticle(
        id="art_killed",
        source_id="src1",
        canonical_url="https://example.com/killed",
        title="止损回退",
        score_grade="S",
        score_total=90.0,
        generated_video_path=_seed_video(tmp_path, "art_killed"),
        generated_cover_path=_seed_cover(tmp_path, "art_killed"),
        video_draft_json=json.dumps({"main_line1": "止损回退"}),
    )
    db_session.add(article)
    _add_account(db_session, account_id="acc-wc", platform="wechat_channels")
    db_session.commit()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.evaluate_article_candidates",
        lambda session, candidate_article, config: {
            "candidate_evaluation": True,
            "candidates": [{"platform": "wechat_channels", "status": "pending"}],
        },
    )

    result = maybe_enqueue_auto_publish_jobs(
        db_session,
        article,
        config={
            "publish_policy": {
                "enabled": True,
                "platforms": {
                    "wechat_channels": {
                        "enabled": False,
                        "kill_switch": {"active": True, "reason": "weak_d1"},
                    }
                },
            },
            "post_score_automation": {
                "auto_publish": {"enabled": True, "skip_if_exists": True, "min_grade": "S"},
                "story_gate": {"enabled": False},
            },
        },
    )

    assert result["candidate_evaluation"] is True
    assert result["legacy_fallback"]["enqueued"] is True
    assert db_session.query(PublishJob).count() == 1


def test_runtime_config_enables_candidate_queue_when_config_is_omitted(
    db_session, tmp_path, monkeypatch
):
    article = IngestedArticle(
        id="art_runtime_policy",
        source_id="src1",
        canonical_url="https://example.com/runtime-policy",
        title="运行时策略",
        score_grade="A",
        score_total=75.0,
        generated_video_path=_seed_video(tmp_path, "art_runtime_policy"),
    )
    db_session.add(article)
    db_session.commit()
    runtime = {"publish_policy": {"enabled": True}}
    expected = {"candidate_evaluation": True, "candidates": []}
    monkeypatch.setattr(
        "services.publishing.auto_publish.load_scoring_config",
        lambda: runtime,
    )
    monkeypatch.setattr(
        "services.publishing.candidate_queue.evaluate_article_candidates",
        lambda session, candidate_article, config: expected,
    )

    result = maybe_enqueue_auto_publish_jobs(db_session, article)

    assert result == expected

    result_from_empty_override = maybe_enqueue_auto_publish_jobs(
        db_session, article, config={}
    )
    assert result_from_empty_override == expected
