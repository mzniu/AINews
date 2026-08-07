"""Shared QR login helpers for platform adapters."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Sequence

from loguru import logger

from services.publishing.adapters.base import AccountInfo, QrLoginContext, QrLoginResult


@dataclass
class QrLoginProfile:
    platform_id: str
    login_url: str
    success_url_excludes: list[str] = field(default_factory=lambda: ["login", "passport"])
    qr_selector: str | None = None
    qr_switch_selector: str | None = None
    headless: bool = False
    uid_extractor: Literal["dom", "generated"] = "generated"
    nickname_selector: str | None = None
    extract_account_info: Callable | None = None
    post_login_url: str | None = None
    post_login_wait_ms: int = 3000
    required_session_cookies: tuple[str, ...] = ()


def is_login_success_url(url: str, success_url_excludes: list[str]) -> bool:
    lower = (url or "").lower()
    return not any(token in lower for token in success_url_excludes)


def storage_state_has_session_cookies(storage: dict, cookie_names: Sequence[str]) -> bool:
    if not cookie_names:
        return True
    names = {str(item.get("name", "")).lower() for item in storage.get("cookies", [])}
    return any(name.lower() in names for name in cookie_names)


def _capture_login_storage_state(context, page, profile: QrLoginProfile) -> dict:
    settle_url = profile.post_login_url
    if settle_url:
        page.goto(settle_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(max(profile.post_login_wait_ms, 0))

    if not profile.required_session_cookies:
        return context.storage_state()

    for attempt in range(6):
        storage = context.storage_state()
        if storage_state_has_session_cookies(storage, profile.required_session_cookies):
            return storage
        logger.warning(
            "Login settle attempt %s/%s: missing session cookies %s for %s",
            attempt + 1,
            6,
            profile.required_session_cookies,
            profile.platform_id,
        )
        page.wait_for_timeout(1000)

    return context.storage_state()


def run_generic_qr_login(profile: QrLoginProfile, ctx: QrLoginContext) -> QrLoginResult:
    from playwright.sync_api import sync_playwright

    ctx.qr_dir.mkdir(parents=True, exist_ok=True)
    qr_path = ctx.qr_dir / f"{ctx.session_id}.png"
    deadline = time.time() + ctx.qr_timeout_sec

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=profile.headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(profile.login_url or ctx.login_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            if profile.qr_switch_selector:
                try:
                    page.locator(profile.qr_switch_selector).first.click(timeout=5000)
                    page.wait_for_timeout(1000)
                except Exception as exc:
                    logger.warning("QR switch click failed for %s: %s", profile.platform_id, exc)
            _capture_qr(page, qr_path, profile.qr_selector)
        except Exception as exc:
            browser.close()
            return QrLoginResult(status="failed", error_message=str(exc))

        while time.time() < deadline:
            if is_login_success_url(page.url, profile.success_url_excludes):
                storage = _capture_login_storage_state(context, page, profile)
                if profile.required_session_cookies and not storage_state_has_session_cookies(
                    storage, profile.required_session_cookies
                ):
                    browser.close()
                    return QrLoginResult(
                        status="failed",
                        error_message=(
                            "登录成功但未捕获到完整会话 Cookie（"
                            f"缺少 {', '.join(profile.required_session_cookies)}），请重试扫码"
                        ),
                        qr_image_path=str(qr_path),
                    )
                info = _resolve_account_info(page, profile)
                browser.close()
                return QrLoginResult(
                    status="confirmed",
                    qr_image_path=str(qr_path),
                    account_info=info,
                    storage_state_json=json.dumps(storage).encode("utf-8"),
                )
            page.wait_for_timeout(2000)
            try:
                _capture_qr(page, qr_path, profile.qr_selector)
            except Exception:
                pass

        browser.close()
        return QrLoginResult(
            status="expired",
            qr_image_path=str(qr_path),
            error_message=f"扫码超时（{ctx.qr_timeout_sec}s）",
        )


def _capture_qr(page, qr_path: Path, selector: str | None) -> None:
    if selector:
        page.locator(selector).first.screenshot(path=str(qr_path))
    else:
        page.screenshot(path=str(qr_path), full_page=True)


def _resolve_account_info(page, profile: QrLoginProfile) -> AccountInfo:
    if profile.extract_account_info:
        return profile.extract_account_info(page)
    nickname = "未命名账号"
    if profile.nickname_selector:
        try:
            nickname = page.locator(profile.nickname_selector).first.inner_text(timeout=3000).strip()
        except Exception:
            pass
    uid = f"{profile.platform_id}_{int(time.time())}"
    return AccountInfo(nickname=nickname or "未命名账号", platform_uid=uid)
