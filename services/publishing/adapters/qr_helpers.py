"""Shared QR login helpers for platform adapters."""
from __future__ import annotations

import json
import random
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
    cookie_settle_attempts: int = 15
    cookie_settle_interval_ms: int = 2000
    use_stealth_browser: bool = True
    required_session_cookies: tuple[str, ...] = ()


def build_qr_login_profile(
    *,
    platform_id: str,
    login_url: str,
    creator_url: str,
    qr_profile: dict | None = None,
    extract_account_info: Callable | None = None,
    default_success_excludes: list[str] | None = None,
) -> QrLoginProfile:
    """Build a QR login profile from platform config and optional account extractor."""
    cfg = qr_profile or {}
    required = cfg.get("required_session_cookies") or []
    excludes = list(cfg.get("success_url_excludes") or default_success_excludes or ["login", "passport"])
    return QrLoginProfile(
        platform_id=platform_id,
        login_url=login_url,
        success_url_excludes=excludes,
        qr_selector=cfg.get("qr_selector"),
        qr_switch_selector=cfg.get("qr_switch_selector"),
        headless=bool(cfg.get("headless", False)),
        nickname_selector=cfg.get("nickname_selector"),
        post_login_url=cfg.get("post_login_url") or creator_url,
        post_login_wait_ms=int(cfg.get("post_login_wait_ms", 3000)),
        cookie_settle_attempts=int(cfg.get("cookie_settle_attempts", 15)),
        cookie_settle_interval_ms=int(cfg.get("cookie_settle_interval_ms", 2000)),
        use_stealth_browser=bool(cfg.get("use_stealth_browser", True)),
        required_session_cookies=tuple(required),
        extract_account_info=extract_account_info,
    )


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
        _login_page_pause(page, profile, kind="page_load")

    if not profile.required_session_cookies:
        return context.storage_state()

    attempts = max(profile.cookie_settle_attempts, 1)
    for attempt in range(attempts):
        storage = context.storage_state()
        if storage_state_has_session_cookies(storage, profile.required_session_cookies):
            return storage
        logger.warning(
            "Login settle attempt %s/%s: missing session cookies %s for %s",
            attempt + 1,
            attempts,
            profile.required_session_cookies,
            profile.platform_id,
        )
        _login_settle_pause(page, profile)

    return context.storage_state()


def _login_settle_pause(page, profile: QrLoginProfile) -> None:
    interval_ms = max(profile.cookie_settle_interval_ms, 500)
    if profile.use_stealth_browser:
        from services.publishing.human_pacing import human_pause

        human_pause(page, "polling")
        return
    page.wait_for_timeout(interval_ms)


def _login_page_pause(page, profile: QrLoginProfile, *, kind: str = "page_load") -> None:
    if profile.use_stealth_browser:
        from services.publishing.human_interaction import human_idle_on_page
        from services.publishing.human_pacing import human_pause

        human_pause(page, kind)  # type: ignore[arg-type]
        if kind == "page_load":
            human_idle_on_page(page, moves=random.randint(2, 4))
        return
    fixed_ms = {"page_load": max(profile.post_login_wait_ms, 0), "step": 1500, "polling": 2000}.get(kind, 2000)
    page.wait_for_timeout(fixed_ms)


def _create_login_browser(playwright, profile: QrLoginProfile):
    if not profile.use_stealth_browser:
        browser = playwright.chromium.launch(headless=profile.headless)
        return browser, browser.new_context()
    from services.publishing.human_interaction import open_stealth_browser

    return open_stealth_browser(playwright, headless=profile.headless)


def run_generic_qr_login(profile: QrLoginProfile, ctx: QrLoginContext) -> QrLoginResult:
    from services.publishing.browser_profile import load_browser_profile_config, pending_profile_key

    ctx.qr_dir.mkdir(parents=True, exist_ok=True)
    qr_path = ctx.qr_dir / f"{ctx.session_id}.png"
    cfg = load_browser_profile_config()
    use_profile = bool(cfg.get("enabled", True)) and profile.use_stealth_browser
    if use_profile:
        profile_key = ctx.account_id or pending_profile_key(ctx.session_id)
        from services.publishing.browser_session import open_publish_session

        with open_publish_session(profile_key, mode="login") as sess:
            return _run_qr_login_loop(profile, ctx, qr_path, sess.page, sess.context)
    return _run_qr_login_legacy(profile, ctx, qr_path)


def _run_qr_login_legacy(profile: QrLoginProfile, ctx: QrLoginContext, qr_path: Path) -> QrLoginResult:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser, context = _create_login_browser(playwright, profile)
        page = context.new_page()
        try:
            return _run_qr_login_loop(profile, ctx, qr_path, page, context)
        finally:
            browser.close()


def _run_qr_login_loop(
    profile: QrLoginProfile,
    ctx: QrLoginContext,
    qr_path: Path,
    page,
    context,
) -> QrLoginResult:
    deadline = time.time() + ctx.qr_timeout_sec
    try:
        page.goto(profile.login_url or ctx.login_url, wait_until="domcontentloaded")
        _login_page_pause(page, profile, kind="step")
        if profile.qr_switch_selector:
            try:
                if profile.use_stealth_browser:
                    from services.publishing.human_interaction import human_click

                    human_click(page, page.locator(profile.qr_switch_selector).first, timeout_ms=5000)
                else:
                    page.locator(profile.qr_switch_selector).first.click(timeout=5000)
                _login_page_pause(page, profile, kind="step")
            except Exception as exc:
                logger.warning("QR switch click failed for %s: %s", profile.platform_id, exc)
        _capture_qr(page, qr_path, profile.qr_selector)
    except Exception as exc:
        return QrLoginResult(status="failed", error_message=str(exc))

    while time.time() < deadline:
        if is_login_success_url(page.url, profile.success_url_excludes):
            storage = _capture_login_storage_state(context, page, profile)
            if profile.required_session_cookies and not storage_state_has_session_cookies(
                storage, profile.required_session_cookies
            ):
                remaining = deadline - time.time()
                if remaining > 8:
                    logger.info(
                        "Login URL ok but session cookies not ready for %s, "
                        "will retry (%.0fs remaining)",
                        profile.platform_id,
                        remaining,
                    )
                    _login_page_pause(page, profile, kind="polling")
                    continue
                return QrLoginResult(
                    status="failed",
                    error_message=(
                        "登录成功但未捕获到完整会话 Cookie（"
                        f"缺少 {', '.join(profile.required_session_cookies)}），请重试扫码"
                    ),
                    qr_image_path=str(qr_path),
                )
            info = _resolve_account_info(page, profile)
            return QrLoginResult(
                status="confirmed",
                qr_image_path=str(qr_path),
                account_info=info,
                storage_state_json=json.dumps(storage).encode("utf-8"),
            )
        _login_page_pause(page, profile, kind="polling")
        try:
            _capture_qr(page, qr_path, profile.qr_selector)
        except Exception:
            pass

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
