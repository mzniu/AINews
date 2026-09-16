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
class _QrCaptureTarget:
    locator: object
    mode: Literal["img", "element"] = "img"


_WECHAT_LOGIN_MARKERS = ("channels.weixin.qq.com/login",)
_WECHAT_QR_IFRAME = "#wx-oauth-container iframe"
_WECHAT_QR_IMG_SELECTORS = (
    "img.js_qrcode_img.web_qrcode_img",
    "img.js_qrcode_img",
    "img.web_qrcode_img",
    'img[class*="qrcode"]',
    "img",
)
_WECHAT_QR_CONTAINER_SELECTORS = (
    _WECHAT_QR_IFRAME,
    ".qrcode-wrap",
    ".login-qrcode-wrap",
)
_WECHAT_MOBILE_LOGIN_PATH = "/mobile/mobile.html"
_WECHAT_OAUTH_LOAD_FAIL_MARKERS = ("加载失败", "点击重试")
_MOBILE_UA_PATTERN = ("mobile", "android", "iphone", "ipad", "phone")

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
    """Capture session cookies after login. Snapshot early — users often close the window right after scan."""
    current_url = page.url or ""
    try:
        if is_login_success_url(current_url, profile.success_url_excludes):
            early = context.storage_state()
            if not profile.required_session_cookies or storage_state_has_session_cookies(
                early, profile.required_session_cookies
            ):
                logger.info("Captured login storage immediately for {}", profile.platform_id)
                return early
    except Exception as exc:
        logger.debug("Early login storage snapshot skipped for {}: {}", profile.platform_id, exc)

    settle_url = (profile.post_login_url or "").strip()
    if settle_url and settle_url not in current_url:
        page.goto(settle_url, wait_until="domcontentloaded", timeout=60_000)
    _login_page_pause(page, profile, kind="page_load", after_login_success=True)

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


def _login_page_pause(
    page,
    profile: QrLoginProfile,
    *,
    kind: str = "page_load",
    after_login_success: bool = False,
) -> None:
    if profile.use_stealth_browser:
        from services.publishing.human_pacing import human_pause

        if after_login_success:
            human_pause(page, "after_click")
            return
        from services.publishing.human_interaction import human_idle_on_page

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


def _is_mobile_user_agent(user_agent: str | None) -> bool:
    lower = (user_agent or "").lower()
    return any(token in lower for token in _MOBILE_UA_PATTERN)


def _is_wechat_mobile_login_url(url: str | None) -> bool:
    return _WECHAT_MOBILE_LOGIN_PATH in (url or "")


def _desktop_publish_user_agent() -> str:
    from services.publishing.human_interaction import DEFAULT_PUBLISH_USER_AGENT

    return DEFAULT_PUBLISH_USER_AGENT


def _normalize_wechat_persona_user_agent(account_id: str | None) -> None:
    if not account_id:
        return
    from services.publishing.persona import load_persona, save_persona

    persona = load_persona(account_id)
    ua = str(persona.get("user_agent") or "")
    if not _is_mobile_user_agent(ua):
        return
    persona["user_agent"] = _desktop_publish_user_agent()
    save_persona(account_id, persona)
    logger.info("WeChat login: normalized mobile persona user_agent for {}", account_id)


def _ensure_wechat_desktop_login(page, context, *, account_id: str | None) -> None:
    """Force desktop UA/viewport so channels login.html does not redirect to mobile."""
    _normalize_wechat_persona_user_agent(account_id)
    desktop_ua = _desktop_publish_user_agent()
    try:
        current_ua = page.evaluate("() => navigator.userAgent")
    except Exception:
        current_ua = ""
    if _is_mobile_user_agent(current_ua):
        logger.warning("WeChat login: overriding mobile browser UA with desktop Chrome UA")

    try:
        cdp = context.new_cdp_session(page)
        cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": 1440,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        cdp.send("Network.setUserAgentOverride", {"userAgent": desktop_ua})
    except Exception as exc:
        logger.debug("WeChat login CDP desktop override skipped: {}", exc)

    try:
        context.add_init_script(
            f"""(() => {{
  const ua = {json.dumps(desktop_ua)};
  try {{
    Object.defineProperty(navigator, 'userAgent', {{ get: () => ua }});
  }} catch (e) {{}}
}})();"""
        )
    except Exception as exc:
        logger.debug("WeChat login init-script UA override skipped: {}", exc)


def _goto_wechat_login_page(page, context, login_url: str, *, account_id: str | None) -> None:
    _ensure_wechat_desktop_login(page, context, account_id=account_id)
    page.goto(login_url, wait_until="domcontentloaded")
    if _is_wechat_mobile_login_url(page.url):
        logger.warning("WeChat login redirected to mobile page; retrying with desktop UA")
        _ensure_wechat_desktop_login(page, context, account_id=account_id)
        page.goto(login_url, wait_until="domcontentloaded")


def _run_qr_login_loop(
    profile: QrLoginProfile,
    ctx: QrLoginContext,
    qr_path: Path,
    page,
    context,
) -> QrLoginResult:
    deadline = time.time() + ctx.qr_timeout_sec
    login_url = profile.login_url or ctx.login_url
    profile_key = ctx.account_id
    if not profile_key and profile.platform_id == "wechat_channels":
        from services.publishing.browser_profile import pending_profile_key

        profile_key = pending_profile_key(ctx.session_id)
    try:
        if profile.platform_id == "wechat_channels":
            _goto_wechat_login_page(page, context, login_url, account_id=profile_key)
        else:
            page.goto(login_url, wait_until="domcontentloaded")
        _login_page_pause(page, profile, kind="step")
        _prepare_login_page_for_qr(page, login_url)
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
            try:
                storage = _capture_login_storage_state(context, page, profile)
            except Exception as exc:
                if _is_target_closed_error(exc):
                    return QrLoginResult(
                        status="failed",
                        error_message=(
                            "扫码已成功，但浏览器窗口在保存会话前被关闭。"
                            "请重新扫码并在看到「登录成功」前保持浏览器窗口打开。"
                        ),
                        qr_image_path=str(qr_path),
                    )
                raise
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
            _capture_qr(page, qr_path, profile.qr_selector, prepare=False)
        except Exception:
            pass

    return QrLoginResult(
        status="expired",
        qr_image_path=str(qr_path),
        error_message=f"扫码超时（{ctx.qr_timeout_sec}s）",
    )


def _qr_selector_candidates(selector: str) -> list[str]:
    return [part.strip() for part in selector.split(",") if part.strip()]


def _is_wechat_login_url(url: str | None) -> bool:
    lower = (url or "").lower()
    return any(marker in lower for marker in _WECHAT_LOGIN_MARKERS)


def _wechat_qr_visible(page) -> bool:
    return _find_wechat_qr_target(page, prepare=False) is not None


def _wechat_oauth_load_failed(page) -> bool:
    if not _is_wechat_login_url(page.url) or _is_wechat_mobile_login_url(page.url):
        return False
    if _find_wechat_qr_img_target(page) is not None:
        return False
    try:
        body = page.locator("body").inner_text(timeout=2000)
    except Exception:
        return False
    return all(marker in body for marker in _WECHAT_OAUTH_LOAD_FAIL_MARKERS)


def _raise_qr_capture_error(page, selector: str | None) -> None:
    url = page.url or ""
    if "channels.weixin.qq.com" in url and _is_wechat_mobile_login_url(url):
        raise RuntimeError(
            "视频号登录被重定向到移动端页面（/mobile/mobile.html）。"
            "请重置浏览器指纹 User-Agent 为桌面 Chrome 后重试。"
        )
    if _is_wechat_login_url(url):
        if _wechat_oauth_load_failed(page):
            raise RuntimeError(
                "微信 OAuth 二维码加载失败（页面显示「加载失败，点击重试」）。"
                "请检查本机网络能否访问 open.weixin.qq.com，或在本地浏览器重试扫码登录。"
            )
    raise RuntimeError(f"QR element not found: {selector}")


def _prepare_login_page_for_qr(page, login_url: str | None) -> None:
    if not _is_wechat_login_url(login_url or getattr(page, "url", "")):
        return
    page.wait_for_timeout(2000)
    if _wechat_qr_visible(page):
        return
    for attempt in range(3):
        try:
            mask = page.locator(".qrcode-wrap .mask").first
            if not mask.is_visible(timeout=1200):
                if _wechat_qr_visible(page):
                    return
                page.wait_for_timeout(1500)
                continue
            page.locator(".refresh-wrap").first.click(timeout=3000)
            logger.info("WeChat login QR refresh click {}/3", attempt + 1)
        except Exception as exc:
            logger.debug("WeChat login QR refresh skipped: {}", exc)
        page.wait_for_timeout(2500)
        if _wechat_qr_visible(page):
            return


def _is_target_closed_error(exc: BaseException) -> bool:
    name = exc.__class__.__name__
    return name == "TargetClosedError" or "has been closed" in str(exc).lower()


def _parse_qr_selector(selector: str) -> tuple[str | None, str]:
    text = selector.strip()
    if text.lower().startswith("iframe:"):
        body = text[len("iframe:") :]
        if "|" not in body:
            return body.strip(), "img"
        iframe_sel, inner_sel = body.split("|", 1)
        return iframe_sel.strip(), inner_sel.strip()
    return None, text


def _first_visible_locator(locator, *, timeout_ms: int = 4000):
    deadline = time.time() + max(timeout_ms, 0) / 1000
    while time.time() < deadline:
        try:
            count = locator.count()
        except Exception:
            return None
        for index in range(count):
            try:
                item = locator.nth(index)
                if item.is_visible(timeout=200):
                    return item
            except Exception:
                continue
        time.sleep(0.25)
    return None


def _find_wechat_qr_img_target(page) -> _QrCaptureTarget | None:
    try:
        iframe_visible = page.locator(_WECHAT_QR_IFRAME).first.is_visible(timeout=1500)
    except Exception:
        iframe_visible = False
    if not iframe_visible:
        return None
    for img_sel in _WECHAT_QR_IMG_SELECTORS:
        try:
            loc = _first_visible_locator(
                page.frame_locator(_WECHAT_QR_IFRAME).locator(img_sel),
                timeout_ms=4000,
            )
            if loc is not None:
                return _QrCaptureTarget(locator=loc, mode="img")
        except Exception:
            continue
    return None


def _iter_qr_search_specs(selectors: Sequence[str]) -> list[tuple[str | None, str]]:
    specs: list[tuple[str | None, str]] = []
    seen: set[tuple[str | None, str]] = set()
    for raw in selectors:
        iframe_sel, inner_sel = _parse_qr_selector(raw)
        key = (iframe_sel, inner_sel)
        if key not in seen:
            specs.append(key)
            seen.add(key)
    return specs


def _find_wechat_qr_target(page, *, prepare: bool = False) -> _QrCaptureTarget | None:
    if prepare:
        _prepare_login_page_for_qr(page, page.url)
    img_target = _find_wechat_qr_img_target(page)
    if img_target is not None:
        return img_target
    for container_sel in _WECHAT_QR_CONTAINER_SELECTORS:
        try:
            loc = page.locator(container_sel).first
            loc.wait_for(state="visible", timeout=2000)
            return _QrCaptureTarget(locator=loc, mode="element")
        except Exception:
            continue
    return None


def _find_visible_qr_locator(page, selectors: Sequence[str]) -> _QrCaptureTarget | None:
    specs = _iter_qr_search_specs(selectors)
    if _is_wechat_login_url(page.url):
        specs.extend((iframe_sel, inner) for iframe_sel, inner in (
            (_WECHAT_QR_IFRAME, img_sel) for img_sel in _WECHAT_QR_IMG_SELECTORS
        ))

    for iframe_sel, inner_sel in specs:
        if iframe_sel:
            try:
                loc = _first_visible_locator(
                    page.frame_locator(iframe_sel).locator(inner_sel),
                    timeout_ms=4000,
                )
                if loc is not None:
                    return _QrCaptureTarget(locator=loc, mode="img")
            except Exception:
                continue
            continue

        for frame in page.frames:
            try:
                loc = _first_visible_locator(frame.locator(inner_sel), timeout_ms=2500)
                if loc is not None:
                    return _QrCaptureTarget(locator=loc, mode="img")
            except Exception:
                continue

    if _is_wechat_login_url(page.url):
        return _find_wechat_qr_target(page, prepare=False)
    return None


def _download_qr_from_img(loc, page, qr_path: Path) -> bool:
    try:
        src = loc.evaluate(
            """(el) => {
                if (!el || el.tagName !== 'IMG') return '';
                try { return new URL(el.currentSrc || el.src, document.baseURI).href; }
                catch { return el.src || ''; }
            }"""
        )
    except Exception:
        return False
    if not src or src.startswith("data:"):
        return False
    response = page.context.request.get(src)
    if not response.ok:
        return False
    qr_path.write_bytes(response.body())
    return True


def _capture_qr(page, qr_path: Path, selector: str | None, *, prepare: bool = True) -> None:
    if not selector:
        page.screenshot(path=str(qr_path), full_page=True)
        return

    if prepare:
        _prepare_login_page_for_qr(page, page.url)
    selectors = _qr_selector_candidates(selector)
    target = _find_visible_qr_locator(page, selectors)
    if target is None:
        _raise_qr_capture_error(page, selector)

    loc = target.locator
    if target.mode == "img" and _download_qr_from_img(loc, page, qr_path):
        return
    loc.screenshot(path=str(qr_path))


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
