"""Stub publish implementations for platforms not yet supporting auto-publish."""
from __future__ import annotations

from pathlib import Path

from services.publishing.adapters.base import PublishPayload, PublishResult


def publish_not_implemented(session_path: Path, payload: PublishPayload) -> PublishResult:
    del session_path, payload
    return PublishResult(
        success=False,
        error_message="该平台自动发布尚未开放，请在创作者中心手动上传",
        manual_publish_pending=True,
    )
