"""Kuaishou creator center adapter."""
from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from services.publishing.adapters.creator_center import CreatorCenterAdapter
from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.adapters.base import PublishPayload, PublishResult
from services.publishing.adapters.kuaishou_form import (
    advance_past_kuaishou_upload_window,
    click_kuaishou_publish,
    compose_kuaishou_description,
    dismiss_kuaishou_guide_tooltips,
    fill_kuaishou_description,
    fill_kuaishou_title,
    upload_kuaishou_video,
    wait_for_kuaishou_editor,
    wait_for_kuaishou_video_ready,
)
from services.publishing.session_store import load_encrypted
from src.utils.config import Config


class KuaishouAdapter(CreatorCenterAdapter):
    """Kuaishou — QR login + semi-automatic video publish."""

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        temp_state = Config.ROOT_DIR / "data" / "publish" / "_publish_state.json"
        screenshot_dir = Config.ROOT_DIR / "data" / "publish" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"kuaishou_fail_{int(time.time())}.png"
        page = None
        browser = None
        playwright = None
        timeout_ms = self.upload_timeout_sec * 1000
        max_title = int(self.limits.get("max_title_length", 50))
        max_tags = int(self.limits.get("max_tags", 4))
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

            if not upload_kuaishou_video(page, str(payload.video_path.resolve()), timeout_ms=timeout_ms):
                return PublishResult(success=False, error_message="未能定位快手上传入口，请检查创作者中心页面")

            if not wait_for_kuaishou_video_ready(page, timeout_ms=timeout_ms):
                logger.warning("快手视频处理未在超时内完成，继续尝试填写文案")

            if not advance_past_kuaishou_upload_window(page, timeout_ms=min(timeout_ms, 60_000)):
                logger.warning("快手仍停留在上传窗口，继续尝试填写文案")

            if not wait_for_kuaishou_editor(page, timeout_ms=min(timeout_ms, 60_000)):
                logger.warning("快手编辑器未在超时内出现，继续尝试填写文案")

            dismiss_kuaishou_guide_tooltips(page)

            fill_kuaishou_title(
                page,
                payload.title or "",
                timeout_ms=min(timeout_ms, 60_000),
                max_length=max_title,
            )

            description = compose_kuaishou_description(
                payload.description or "",
                payload.tags,
                max_tags=max_tags,
            )
            if description:
                filled = fill_kuaishou_description(page, description, timeout_ms=min(timeout_ms, 60_000))
                if not filled:
                    logger.warning("快手作品描述填写失败，请在发布页手动补充")

            if payload.cover_path:
                logger.warning("快手自定义封面上传尚未实现，将使用平台默认封面")

            published = click_kuaishou_publish(page, timeout_ms=min(timeout_ms, 90_000))
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

            logger.info("快手已自动点击发布")
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            return PublishResult(
                success=True,
                platform_post_id=f"ks_{int(time.time())}",
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
