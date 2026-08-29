"""P2 tests: multi-platform first comment + deferred posting."""
from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from services.publishing.adapters.base import CommentResult, PublishResult
from services.publishing.adapters.creator_comment_helpers import pick_work
from services.publishing.first_comment_timing import get_comment_timing, is_first_comment_deferred


def test_can_post_first_comment_all_platforms():
    from services.publishing.platform_capabilities import can_post_first_comment

    assert can_post_first_comment("douyin") is True
    assert can_post_first_comment("kuaishou") is True
    assert can_post_first_comment("wechat_channels") is True
    assert can_post_first_comment("xiaohongshu") is True


def test_p2_platforms_use_deferred_first_comment():
    assert is_first_comment_deferred("kuaishou") is True
    assert is_first_comment_deferred("wechat_channels") is True
    assert is_first_comment_deferred("xiaohongshu") is True
    assert is_first_comment_deferred("douyin") is False


def test_get_comment_timing_uses_platform_limits():
    delay, wait_max, deferred = get_comment_timing("xiaohongshu")
    assert delay == 20
    assert wait_max == 90
    assert deferred is True


def test_pick_work_matches_post_id():
    rows = [
        {"photo_id": "abc", "title": "作品A"},
        {"photo_id": "def", "title": "作品B"},
    ]
    work = pick_work(rows, title="无关", post_id="def", id_keys=("photo_id",))
    assert work is not None
    assert work["photo_id"] == "def"


def test_orchestrator_deferred_comment_after_publish(tmp_path, monkeypatch):
    from src.db.engine import init_db, get_session_factory
    from src.db.models.publishing import PublishJob, PublisherAccount
    from services.publishing.orchestrator import PublishOrchestrator

    db_path = tmp_path / "p2_deferred.db"
    monkeypatch.setenv("INGESTION_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr("src.utils.config.Config.ROOT_DIR", tmp_path)
    (tmp_path / "data" / "videos").mkdir(parents=True)
    video = tmp_path / "data" / "videos" / "clip.mp4"
    video.write_bytes(b"x")
    init_db()

    with get_session_factory()() as session:
        session.add(
            PublisherAccount(
                id="acc1",
                platform="kuaishou",
                nickname="快手号",
                platform_uid="uid1",
                session_path="data/publish/sessions/acc1.enc",
                status="active",
            )
        )
        session.flush()
        session.add(
            PublishJob(
                id="job1",
                account_id="acc1",
                video_path="data/videos/clip.mp4",
                title="测试作品",
                status="pending",
                first_comment_text="你觉得这条资讯最关键的点是什么？",
                comment_status="none",
            )
        )
        session.commit()

    adapter = MagicMock()
    adapter.publish_video.return_value = PublishResult(
        success=True,
        platform_post_id="photo123",
        platform_post_url="https://www.kuaishou.com/short-video/photo123",
    )
    adapter.post_first_comment.return_value = CommentResult(success=True)

    with patch("services.publishing.orchestrator.get_adapter", return_value=adapter), patch(
        "services.publishing.orchestrator.get_first_comment_settings",
        return_value={
            "enabled": True,
            "comment_delay_sec": 15,
            "comment_wait_max_sec": 60,
            "retry_max": 3,
        },
    ), patch(
        "services.publishing.orchestrator.resolve_video_path",
        return_value=video,
    ), patch(
        "services.publishing.orchestrator.resolve_cover_path",
        return_value=None,
    ), patch(
        "services.publishing.orchestrator.publish_job_scope",
        lambda *args, **kwargs: nullcontext(),
    ), patch(
        "services.publishing.orchestrator.record_job_log",
        lambda *args, **kwargs: None,
    ):
        PublishOrchestrator(get_session_factory()).publish_job("job1")

    publish_payload = adapter.publish_video.call_args[0][1]
    assert publish_payload.first_comment is None
    adapter.post_first_comment.assert_called_once()

    with get_session_factory()() as session:
        job = session.get(PublishJob, "job1")
        assert job.status == "published"
        assert job.comment_status == "posted"
