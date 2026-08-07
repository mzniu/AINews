"""Shared creator-center adapter for login-only platforms (Phase 2A)."""
from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from services.publishing.adapters.base import (
    PlatformAdapter,
    PublishPayload,
    PublishResult,
    QrLoginContext,
    QrLoginResult,
    SessionStatus,
)
from services.publishing.adapters.publish_stubs import publish_not_implemented
from services.publishing.adapters.qr_helpers import QrLoginProfile, is_login_success_url, run_generic_qr_login
from services.publishing.session_store import load_encrypted
from src.utils.config import Config


class CreatorCenterAdapter(PlatformAdapter):
    """QR login + session validation; video publish deferred to Phase 2B."""

    def __init__(
        self,
        *,
        platform_id: str,
        display_name: str,
        login_url: str,
        creator_url: str,
        upload_timeout_sec: int = 600,
        qr_profile: dict | None = None,
        limits: dict | None = None,
    ) -> None:
        self.platform_id = platform_id
        self.display_name = display_name
        self.login_url = login_url
        self.creator_url = creator_url
        self.upload_timeout_sec = upload_timeout_sec
        self.qr_profile = qr_profile or {}
        self.limits = limits or {}

    def _success_url_excludes(self) -> list[str]:
        return list(self.qr_profile.get("success_url_excludes") or ["login", "passport"])

    def run_qr_login_flow(self, ctx: QrLoginContext) -> QrLoginResult:
        required = self.qr_profile.get("required_session_cookies") or []
        profile = QrLoginProfile(
            platform_id=self.platform_id,
            login_url=self.login_url,
            success_url_excludes=self._success_url_excludes(),
            qr_selector=self.qr_profile.get("qr_selector"),
            qr_switch_selector=self.qr_profile.get("qr_switch_selector"),
            headless=bool(self.qr_profile.get("headless", False)),
            nickname_selector=self.qr_profile.get("nickname_selector"),
            post_login_url=self.qr_profile.get("post_login_url") or self.creator_url,
            post_login_wait_ms=int(self.qr_profile.get("post_login_wait_ms", 3000)),
            required_session_cookies=tuple(required),
        )
        return run_generic_qr_login(profile, ctx)

    def validate_session(self, session_path: Path) -> SessionStatus:
        from playwright.sync_api import sync_playwright

        temp_state = Config.ROOT_DIR / "data" / "publish" / "_validate_state.json"
        try:
            temp_state.write_bytes(load_encrypted(session_path))
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(storage_state=str(temp_state))
                page = context.new_page()
                page.goto(self.creator_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2000)
                expired = not is_login_success_url(page.url, self._success_url_excludes())
                browser.close()
            return "expired" if expired else "active"
        except Exception as exc:
            logger.warning(f"Session validate failed ({self.platform_id}): {exc}")
            return "unknown"
        finally:
            temp_state.unlink(missing_ok=True)

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        return publish_not_implemented(session_path, payload)
