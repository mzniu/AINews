"""Xiaohongshu creator center adapter."""
from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from services.publishing.adapters.creator_center import CreatorCenterAdapter
from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.adapters.base import PublishPayload, PublishResult
from services.publishing.adapters.xiaohongshu_form import (
    click_xiaohongshu_publish,
    compose_xiaohongshu_description,
    fill_xiaohongshu_description,
    fill_xiaohongshu_title,
    upload_xiaohongshu_video,
    wait_for_xiaohongshu_editor,
    wait_for_xiaohongshu_video_ready,
)
from services.publishing.session_store import load_encrypted
from src.utils.config import Config


class XiaohongshuAdapter(CreatorCenterAdapter):
    """Xiaohongshu — QR login + semi-automatic video publish."""

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        temp_state = Config.ROOT_DIR / "data" / "publish" / "_publish_state.json"
        screenshot_dir = Config.ROOT_DIR / "data" / "publish" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"xiaohongshu_fail_{int(time.time())}.png"
        page = None
        browser = None
        playwright = None
        timeout_ms = self.upload_timeout_sec * 1000
        max_title = int(self.limits.get("max_title_length", 20))
        try:
            temp_state.write_bytes(load_encrypted(session_path))
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(storage_state=str(temp_state))
            page = context.new_page()
            page.goto(self.creator_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2000)
            if not is_login_success_url(page.url, self._success_url_excludes()):
                browser.close()
                playwright.stop()
                return PublishResult(success=False, error_message="会话已过期，请重新扫码登录")

            if not upload_xiaohongshu_video(page, str(payload.video_path.resolve()), timeout_ms=timeout_ms):
                return PublishResult(success=False, error_message="未能定位小红书上传入口，请检查创作者中心页面")

            if not wait_for_xiaohongshu_video_ready(page, timeout_ms=timeout_ms):
                logger.warning("小红书视频处理未在超时内完成，继续尝试填写文案")

            if not wait_for_xiaohongshu_editor(page, timeout_ms=min(timeout_ms, 60_000)):
                logger.warning("小红书编辑器未在超时内出现，继续尝试填写文案")

            fill_xiaohongshu_title(
                page,
                payload.title or "",
                timeout_ms=min(timeout_ms, 60_000),
                max_length=max_title,
            )

            description = compose_xiaohongshu_description(payload.description or "", payload.tags)
            if description:
                fill_xiaohongshu_description(page, description, timeout_ms=min(timeout_ms, 60_000))

            if payload.cover_path:
                logger.warning("小红书自定义封面上传尚未实现，将使用平台默认封面")

            published = click_xiaohongshu_publish(page, timeout_ms=min(timeout_ms, 90_000))
            if not published:
                if page is not None:
                    try:
                        page.screenshot(path=str(screenshot_path))
                    except Exception:
                        pass
                if browser is not None:
                    browser.close()
                if playwright is not None:
                    playwright.stop()
                return PublishResult(
                    success=False,
                    error_message="未能自动点击发布或确认发布成功",
                )

            logger.info("小红书已自动点击发布")
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            return PublishResult(
                success=True,
                platform_post_id=f"xhs_{int(time.time())}",
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
        finally:
            temp_state.unlink(missing_ok=True)
