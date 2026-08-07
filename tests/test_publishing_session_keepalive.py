from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.publishing.session_keepalive import (
    load_session_keepalive_config,
    refresh_platform_session,
)


def test_load_session_keepalive_config_defaults():
    cfg = load_session_keepalive_config(
        {
            "defaults": {
                "session_keepalive": {
                    "enabled": True,
                    "interval_hours": 3,
                }
            }
        }
    )
    assert cfg["enabled"] is True
    assert cfg["interval_hours"] == 3
    assert "wechat_channels" in cfg["platforms"]


@patch("services.publishing.session_keepalive.get_adapter")
def test_refresh_platform_session_uses_adapter_hook(mock_get_adapter, tmp_path):
    adapter = MagicMock()
    adapter.refresh_session.return_value = "active"
    mock_get_adapter.return_value = adapter
    session_path = tmp_path / "acc.enc"
    session_path.write_bytes(b"x")

    status = refresh_platform_session("wechat_channels", session_path)

    assert status == "active"
    adapter.refresh_session.assert_called_once()


def test_orchestrator_marks_account_expired_on_session_error():
    from datetime import datetime

    from services.publishing.orchestrator import PublishOrchestrator
    from src.db.models.publishing import PublishJob, PublisherAccount

    job = PublishJob(
        id="job1",
        account_id="acc1",
        video_path="data/videos/a.mp4",
        title="标题",
        status="uploading",
    )
    account = PublisherAccount(
        id="acc1",
        platform="wechat_channels",
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
    adapter.publish_video.return_value = MagicMock(
        success=False,
        error_message="会话已过期，请重新扫码登录",
        manual_publish_pending=False,
        platform_post_id=None,
    )

    with patch("services.publishing.orchestrator.resolve_video_path", return_value=MagicMock()):
        with patch("services.publishing.orchestrator.resolve_cover_path", return_value=None):
            with patch("services.publishing.orchestrator.get_adapter", return_value=adapter):
                with patch("services.publishing.orchestrator.publish_job_scope"):
                    with patch("services.publishing.orchestrator.record_job_log"):
                        PublishOrchestrator(session_factory).publish_job("job1")

    assert job.status == "failed"
    assert account.status == "expired"
    assert "重新登录" in (job.error_message or "")
