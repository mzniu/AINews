"""TDD tests for post-publish first comment (P0 Douyin)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.publishing.adapters.base import CommentResult, PublishPayload, PublishResult
from services.publishing.auto_publish import maybe_enqueue_auto_publish_jobs
from services.publishing.first_comment import (
    apply_comment_outcome,
    should_post_first_comment,
    validate_first_comment,
)
from services.publishing.metadata_bridge import draft_from_video_draft
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
    db_path = tmp_path / "first_comment.db"
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


def test_validate_first_comment_accepts_question_in_range():
    ok, err = validate_first_comment("你觉得这条资讯最关键的点是什么？")
    assert ok is True
    assert err is None


def test_validate_first_comment_rejects_too_short():
    ok, err = validate_first_comment("太短了")
    assert ok is False
    assert err


def test_validate_first_comment_rejects_too_long():
    ok, err = validate_first_comment("甲" * 51)
    assert ok is False
    assert err


def test_can_post_first_comment_platforms():
    from services.publishing.platform_capabilities import can_post_first_comment

    assert can_post_first_comment("douyin") is True
    assert can_post_first_comment("kuaishou") is True
    assert can_post_first_comment("wechat_channels") is True
    assert can_post_first_comment("xiaohongshu") is True
    assert can_post_first_comment("unknown_platform") is False


def test_should_post_first_comment_when_ready():
    assert should_post_first_comment(
        first_comment_text="你觉得这条资讯最关键的点是什么？",
        comment_status="none",
        platform_id="douyin",
        enabled=True,
    )


def test_should_post_first_comment_skips_when_posted():
    assert not should_post_first_comment(
        first_comment_text="你觉得这条资讯最关键的点是什么？",
        comment_status="posted",
        platform_id="douyin",
        enabled=True,
    )


def test_should_post_first_comment_skips_without_text():
    assert not should_post_first_comment(
        first_comment_text="",
        comment_status="none",
        platform_id="douyin",
        enabled=True,
    )


def test_should_post_first_comment_skips_when_disabled():
    assert not should_post_first_comment(
        first_comment_text="你觉得这条资讯最关键的点是什么？",
        comment_status="none",
        platform_id="douyin",
        enabled=False,
    )


def test_should_post_first_comment_skips_unsupported_platform():
    assert not should_post_first_comment(
        first_comment_text="你觉得这条资讯最关键的点是什么？",
        comment_status="none",
        platform_id="unknown_platform",
        enabled=True,
    )


def test_apply_comment_outcome_posted():
    job = PublishJob(
        id="j1",
        account_id="a1",
        video_path="data/videos/a.mp4",
        title="标题",
        first_comment_text="你觉得这条资讯最关键的点是什么？",
    )
    result = PublishResult(
        success=True,
        comment_result=CommentResult(success=True),
    )
    apply_comment_outcome(job, result, platform_id="douyin", enabled=True)
    assert job.comment_status == "posted"
    assert job.comment_posted_at is not None
    assert job.comment_error_message is None


def test_apply_comment_outcome_failed_keeps_publish_success():
    job = PublishJob(
        id="j1",
        account_id="a1",
        video_path="data/videos/a.mp4",
        title="标题",
        first_comment_text="你觉得这条资讯最关键的点是什么？",
    )
    result = PublishResult(
        success=True,
        comment_result=CommentResult(success=False, error_message="comment_input_not_found"),
    )
    apply_comment_outcome(job, result, platform_id="douyin", enabled=True)
    assert job.comment_status == "failed"
    assert "comment_input" in (job.comment_error_message or "")


def test_apply_comment_outcome_skipped_when_disabled():
    job = PublishJob(
        id="j1",
        account_id="a1",
        video_path="data/videos/a.mp4",
        title="标题",
        first_comment_text="你觉得这条资讯最关键的点是什么？",
    )
    result = PublishResult(success=True, comment_result=None)
    apply_comment_outcome(job, result, platform_id="douyin", enabled=False)
    assert job.comment_status == "skipped"


def test_apply_comment_outcome_none_without_text():
    job = PublishJob(
        id="j1",
        account_id="a1",
        video_path="data/videos/a.mp4",
        title="标题",
        first_comment_text=None,
    )
    result = PublishResult(success=True, comment_result=None)
    apply_comment_outcome(job, result, platform_id="douyin", enabled=True)
    assert job.comment_status == "none"


def test_draft_from_video_draft_includes_first_comment():
    draft = draft_from_video_draft(
        {
            "main_line1": "突发！",
            "first_comment": "你觉得这条资讯最关键的点是什么？",
        }
    )
    assert draft.first_comment == "你觉得这条资讯最关键的点是什么？"


def test_auto_publish_snapshots_first_comment_text(db_session, tmp_path):
    article = IngestedArticle(
        id="art_fc",
        source_id="src1",
        canonical_url="https://example.com/a",
        title="DeepSeek 发布",
        score_grade="S",
        score_total=90.0,
        generated_video_path=_seed_video(tmp_path, "art_fc"),
        video_draft_json=json.dumps(
            {
                "main_line1": "DeepSeek 发布新模型",
                "short_title": "DeepSeek发布",
                "first_comment": "你觉得这条资讯最关键的点是什么？",
            },
            ensure_ascii=False,
        ),
    )
    db_session.add(article)
    db_session.add(
        PublisherAccount(
            id="acc_dy",
            platform="douyin",
            nickname="dy",
            session_path="data/publish/sessions/acc_dy.enc",
            status="active",
        )
    )
    db_session.commit()

    result = maybe_enqueue_auto_publish_jobs(db_session, article, config=_AUTO_PUBLISH_CFG)
    db_session.commit()

    assert result["enqueued"] is True
    job = db_session.query(PublishJob).filter_by(source_id="art_fc").one()
    assert job.first_comment_text == "你觉得这条资讯最关键的点是什么？"
    assert job.comment_status == "none"


def test_orchestrator_passes_first_comment_in_payload(tmp_path, monkeypatch):
    from services.publishing.orchestrator import PublishOrchestrator
    from src.db.models.publishing import PublishJob, PublisherAccount

    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    (tmp_path / "data" / "videos").mkdir(parents=True, exist_ok=True)
    video = tmp_path / "data" / "videos" / "a.mp4"
    video.write_bytes(b"x")

    job = PublishJob(
        id="job1",
        account_id="acc1",
        video_path="data/videos/a.mp4",
        title="突发？Meta核心研究员离职",
        status="uploading",
        first_comment_text="你觉得这条资讯最关键的点是什么？",
        comment_status="none",
    )
    account = PublisherAccount(
        id="acc1",
        platform="douyin",
        session_path="data/publish/sessions/acc1.enc",
        status="active",
    )

    session = MagicMock()
    session.get.side_effect = lambda model, pk: {
        ("PublishJob", "job1"): job,
        ("PublisherAccount", "acc1"): account,
    }.get((getattr(model, "__name__", str(model)), pk))

    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = session

    captured: dict = {}

    def _publish(_session_path, payload: PublishPayload):
        captured["payload"] = payload
        return PublishResult(
            success=True,
            platform_post_id="7673873560674290944",
            comment_result=CommentResult(success=True),
        )

    adapter = MagicMock()
    adapter.publish_video.side_effect = _publish

    with patch("services.publishing.orchestrator.resolve_video_path", return_value=video):
        with patch("services.publishing.orchestrator.resolve_cover_path", return_value=None):
            with patch("services.publishing.orchestrator.get_adapter", return_value=adapter):
                with patch("services.publishing.orchestrator.publish_job_scope"):
                    with patch("services.publishing.orchestrator.record_job_log"):
                        with patch(
                            "services.publishing.orchestrator.get_first_comment_settings",
                            return_value={"enabled": True},
                        ):
                            PublishOrchestrator(session_factory).publish_job("job1")

    assert captured["payload"].first_comment == "你觉得这条资讯最关键的点是什么？"
    assert job.comment_status == "posted"


def test_get_first_comment_settings_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        "services.publishing.first_comment_settings.PUBLISHING_LOCAL_PATH",
        tmp_path / "config" / "publishing_platforms.local.yaml",
    )
    monkeypatch.setattr(
        "services.publishing.first_comment_settings.load_publishing_yaml",
        lambda: {"defaults": {"first_comment": {"enabled": False, "comment_delay_sec": 15, "comment_wait_max_sec": 60, "retry_max": 3}}},
    )
    from services.publishing.first_comment_settings import get_first_comment_settings

    settings = get_first_comment_settings()
    assert settings["enabled"] is False
    assert settings["comment_delay_sec"] == 15
    assert settings["comment_wait_max_sec"] == 60
    assert settings["retry_max"] == 3


def test_save_first_comment_settings(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    from services.publishing.first_comment_settings import (
        get_first_comment_settings,
        save_first_comment_settings,
    )

    save_first_comment_settings(enabled=True)
    assert get_first_comment_settings()["enabled"] is True


@patch("services.content_generation_service.invoke_json_llm_with_compliance")
@patch("services.content_generation_service._build_openai_client")
def test_generate_video_content_includes_first_comment(mock_client, mock_invoke):
    from services.content_generation_service import generate_video_content

    mock_client.return_value = (MagicMock(), "deepseek-chat", "https://api.deepseek.com", {"id": "p1"})
    compliance = MagicMock()
    compliance.tokens_used = 50
    compliance.to_dict.return_value = {"passed": True}
    mock_invoke.return_value = (
        {
            "main_line1": "Meta核心研究员离职",
            "short_title": "Meta研究员离职",
            "main_line2": "",
            "sub_title": "轻观点",
            "sub_title2": "",
            "summary": "小牛说：Meta 研究员离职。",
            "voiceover_script": "口播稿内容足够长以满足最低字数要求限制。",
            "tags": "#AI",
            "first_comment": "你觉得这条资讯最关键的点是什么？",
        },
        compliance,
    )

    result = generate_video_content(title="原标题", content="正文")

    assert result["first_comment"] == "你觉得这条资讯最关键的点是什么？"


def _published_job(**kwargs):
    defaults = dict(
        id="j1",
        account_id="a1",
        video_path="data/videos/a.mp4",
        title="标题",
        status="published",
        first_comment_text="你觉得这条资讯最关键的点是什么？",
        comment_status="failed",
        comment_retry_count=0,
    )
    defaults.update(kwargs)
    return PublishJob(**defaults)


def test_can_retry_comment_when_failed():
    from services.publishing.first_comment import can_retry_comment

    ok, err = can_retry_comment(_published_job(), platform_id="douyin", retry_max=3)
    assert ok is True
    assert err is None


def test_can_retry_comment_rejects_posted():
    from services.publishing.first_comment import can_retry_comment

    ok, err = can_retry_comment(
        _published_job(comment_status="posted"),
        platform_id="douyin",
        retry_max=3,
    )
    assert ok is False
    assert err == "already_posted"


def test_can_retry_comment_respects_retry_max():
    from services.publishing.first_comment import can_retry_comment

    ok, err = can_retry_comment(
        _published_job(comment_retry_count=3),
        platform_id="douyin",
        retry_max=3,
    )
    assert ok is False
    assert err == "retry_limit_reached"


def test_can_retry_comment_force_bypasses_retry_max():
    from services.publishing.first_comment import can_retry_comment

    ok, err = can_retry_comment(
        _published_job(comment_retry_count=5),
        platform_id="douyin",
        retry_max=3,
        force=True,
    )
    assert ok is True


def test_apply_comment_retry_outcome_increments_count():
    from services.publishing.first_comment import apply_comment_retry_outcome

    job = _published_job()
    apply_comment_retry_outcome(job, CommentResult(success=True))
    assert job.comment_retry_count == 1
    assert job.comment_status == "posted"


def test_retry_comment_job_calls_adapter(tmp_path, monkeypatch):
    from services.publishing.orchestrator import PublishOrchestrator

    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    job = _published_job(id="job1", account_id="acc1")
    account = PublisherAccount(
        id="acc1",
        platform="douyin",
        session_path="data/publish/sessions/acc1.enc",
        status="active",
    )

    session = MagicMock()
    session.get.side_effect = lambda model, pk: {
        ("PublishJob", "job1"): job,
        ("PublisherAccount", "acc1"): account,
    }.get((getattr(model, "__name__", str(model)), pk))

    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = session

    adapter = MagicMock()
    adapter.post_first_comment.return_value = CommentResult(success=True)

    with patch("services.publishing.orchestrator.get_adapter", return_value=adapter):
        with patch("services.publishing.orchestrator.publish_job_scope"):
            with patch("services.publishing.orchestrator.record_job_log"):
                with patch(
                    "services.publishing.orchestrator.get_first_comment_settings",
                    return_value={"comment_delay_sec": 0, "comment_wait_max_sec": 15, "retry_max": 3},
                ):
                    result = PublishOrchestrator(session_factory).retry_comment_job("job1")

    assert result["success"] is True
    adapter.post_first_comment.assert_called_once()
    assert job.comment_status == "posted"
    assert job.comment_retry_count == 1
