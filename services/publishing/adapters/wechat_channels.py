"""WeChat Channels creator center adapter."""
from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from services.publishing.adapters.base import (
    AccountInfo,
    PlatformAdapter,
    PublishPayload,
    PublishResult,
    QrLoginContext,
    QrLoginResult,
)
from services.publishing.adapters.qr_helpers import QrLoginProfile, run_generic_qr_login
from services.publishing.adapters.wechat_channels_form import (
    click_wechat_publish,
    declare_wechat_original,
    fill_wechat_cover,
    fill_wechat_post_description,
    fill_wechat_title,
    upload_wechat_video,
    wait_for_wechat_video_ready,
    is_wechat_upload_blocked,
)
from services.publishing.metadata_bridge import normalize_wechat_title
from services.publishing.session_store import load_encrypted
from src.utils.config import Config

SELECTORS = {
    "file_input": 'input[type="file"]',
    "title_input": 'textarea[placeholder*="标题"], input[placeholder*="标题"]',
    "description_input": (
        '[contenteditable="true"], textarea[placeholder*="描述"], '
        'textarea[placeholder*="简介"], textarea[placeholder*="说点什么"]'
    ),
    "publish_button": 'button:has-text("发表"), button:has-text("发布")',
    "logged_in_marker": ".finder-account, .account-info, [class*='account']",
}


class WechatChannelsAdapter(PlatformAdapter):
    def __init__(
        self,
        *,
        platform_id: str = "wechat_channels",
        display_name: str = "微信视频号",
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

    def run_qr_login_flow(self, ctx: QrLoginContext) -> QrLoginResult:
        profile = QrLoginProfile(
            platform_id=self.platform_id,
            login_url=self.login_url,
            success_url_excludes=["login"],
            qr_selector=None,
            extract_account_info=self._extract_account_from_page,
        )
        return run_generic_qr_login(profile, ctx)

    def _extract_account_from_page(self, page) -> AccountInfo:
        del page
        uid = f"wx_{int(time.time())}"
        return AccountInfo(nickname="视频号账号", platform_uid=uid, avatar_url=None)

    def validate_session(self, session_path: Path) -> str:
        return self._check_or_refresh_session(session_path, headless=True, persist=False)

    def refresh_session(self, session_path: Path, *, headless: bool = True) -> str:
        return self._check_or_refresh_session(session_path, headless=headless, persist=True)

    def _check_or_refresh_session(
        self,
        session_path: Path,
        *,
        headless: bool,
        persist: bool,
    ) -> str:
        import json

        from playwright.sync_api import sync_playwright

        temp_state = Config.ROOT_DIR / "data" / "publish" / "_validate_state.json"
        playwright = None
        browser = None
        try:
            temp_state.write_bytes(load_encrypted(session_path))
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(temp_state))
            page = context.new_page()
            for url in (
                "https://channels.weixin.qq.com/platform/post/create",
                "https://channels.weixin.qq.com/platform",
                self.creator_url,
            ):
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(2500)
                if "login" not in page.url.lower():
                    if persist:
                        storage = context.storage_state()
                        self.persist_storage_state(
                            session_path,
                            json.dumps(storage, ensure_ascii=False).encode("utf-8"),
                        )
                    return "active"
            return "expired"
        except Exception as exc:
            logger.warning(f"Session validate failed: {exc}")
            return "unknown"
        finally:
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            temp_state.unlink(missing_ok=True)

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        temp_state = Config.ROOT_DIR / "data" / "publish" / "_publish_state.json"
        screenshot_dir = Config.ROOT_DIR / "data" / "publish" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"fail_{int(time.time())}.png"
        page = None
        browser = None
        playwright = None
        try:
            temp_state.write_bytes(load_encrypted(session_path))
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(storage_state=str(temp_state))
            page = context.new_page()
            page.goto(self.creator_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3000)
            if "login" in page.url.lower():
                browser.close()
                playwright.stop()
                return PublishResult(success=False, error_message="会话已过期，请重新扫码登录")

            timeout_ms = self.upload_timeout_sec * 1000
            logger.info("视频号：上传视频")
            if not upload_wechat_video(
                page,
                str(payload.video_path.resolve()),
                timeout_ms=min(timeout_ms, 120_000),
            ):
                if page is not None:
                    try:
                        page.screenshot(path=str(screenshot_path))
                    except Exception:
                        pass
                return PublishResult(success=False, error_message="未能定位视频号上传入口")

            logger.info("视频号：等待视频上传/处理完成")
            if not wait_for_wechat_video_ready(page, timeout_ms=timeout_ms):
                return PublishResult(
                    success=False,
                    error_message="视频尚未上传完成，请稍后重试或检查网络",
                )

            max_title = int(self.limits.get("max_title_length", 30))
            title_text = normalize_wechat_title(payload.title or "", max_title_length=max_title)
            logger.info("视频号：填写标题")
            fill_wechat_title(page, title_text, timeout_ms=min(timeout_ms, 60_000), max_length=max_title)
            if payload.description or payload.tags or payload.main_line2 or payload.sub_title or payload.summary:
                filled = fill_wechat_post_description(
                    page,
                    main_line2=payload.main_line2 or "",
                    sub_title=payload.sub_title or "",
                    sub_title2=payload.sub_title2 or "",
                    summary=payload.summary or "",
                    tags=payload.tags,
                    description=payload.description,
                    timeout_ms=min(self.upload_timeout_sec * 1000, 60_000),
                )
                if not filled:
                    logger.warning(
                        "视频号描述未自动填入，请检查页面是否为 contenteditable/Shadow DOM 结构"
                    )
            if payload.cover_path:
                cover_filled = fill_wechat_cover(
                    page,
                    payload.cover_path,
                    timeout_ms=min(self.upload_timeout_sec * 1000, 60_000),
                )
                if not cover_filled:
                    logger.warning("视频号封面未自动上传，请在发布页手动设置封面")
            if not declare_wechat_original(
                page,
                timeout_ms=min(self.upload_timeout_sec * 1000, 60_000),
            ):
                logger.warning("视频号声明原创未自动勾选，请在发布页手动声明")

            published = click_wechat_publish(
                page,
                timeout_ms=min(timeout_ms, 90_000),
            )
            if not published:
                upload_still_blocked = is_wechat_upload_blocked(page) if page is not None else False
                if page is not None:
                    try:
                        page.screenshot(path=str(screenshot_path))
                    except Exception:
                        pass
                if browser is not None:
                    browser.close()
                if playwright is not None:
                    playwright.stop()
                error_message = "未能自动点击发表或确认发表成功，请检查封面/原创声明是否完成"
                if upload_still_blocked:
                    error_message = "视频尚未上传完成（请上传视频），请稍后重试"
                return PublishResult(
                    success=False,
                    error_message=error_message,
                )

            logger.info("视频号已自动点击发表")
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            return PublishResult(
                success=True,
                platform_post_id=f"wx_{int(time.time())}",
                manual_publish_pending=False,
            )
        except PlaywrightTimeoutError as exc:
            if page is not None:
                try:
                    page.screenshot(path=str(screenshot_path))
                except Exception:
                    pass
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            return PublishResult(success=False, error_message=str(exc))
        except Exception as exc:
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            return PublishResult(success=False, error_message=str(exc))
        finally:
            temp_state.unlink(missing_ok=True)
