"""Platform adapter base types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SessionStatus = Literal["active", "expired", "unknown"]
QrStatus = Literal["pending", "waiting_scan", "scanned", "confirmed", "expired", "failed"]


@dataclass
class PublishPayload:
    video_path: Path
    title: str
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    cover_path: Path | None = None
    main_line2: str | None = None
    sub_title: str | None = None
    sub_title2: str | None = None
    summary: str | None = None


@dataclass
class PublishResult:
    success: bool
    platform_post_id: str | None = None
    error_message: str | None = None
    manual_publish_pending: bool = False


@dataclass
class AccountInfo:
    nickname: str
    platform_uid: str
    avatar_url: str | None = None


@dataclass
class QrLoginContext:
    session_id: str
    login_url: str
    qr_dir: Path
    qr_timeout_sec: int = 120


@dataclass
class QrLoginResult:
    status: QrStatus
    qr_image_path: str | None = None
    account_info: AccountInfo | None = None
    storage_state_json: bytes | None = None
    error_message: str | None = None


class PlatformAdapter(ABC):
    platform_id: str
    display_name: str

    @abstractmethod
    def run_qr_login_flow(self, ctx: QrLoginContext) -> QrLoginResult:
        """Run until confirmed, expired, or failed."""

    @abstractmethod
    def validate_session(self, session_path: Path) -> SessionStatus:
        """Check whether encrypted session is still valid."""

    @abstractmethod
    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        """Upload video and fill metadata."""

    def persist_storage_state(self, dest: Path, storage_state_json: bytes) -> None:
        from services.publishing.session_store import save_encrypted

        save_encrypted(dest, storage_state_json)

    def refresh_session(self, session_path: Path, *, headless: bool = True) -> SessionStatus:
        """Default: validate only. Platforms with short TTL should override."""
        return self.validate_session(session_path)
