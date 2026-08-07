"""Douyin creator center adapter."""
from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from services.publishing.adapters.creator_center import CreatorCenterAdapter
from services.publishing.adapters.douyin_form import (
    click_douyin_publish,
    fill_douyin_description,
    fill_douyin_title,
    fill_douyin_topics,
    format_douyin_tags,
    select_douyin_publish_cover,
    upload_douyin_video,
    wait_for_douyin_editor,
    wait_for_douyin_video_ready,
)
from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.adapters.base import PublishPayload, PublishResult
from services.publishing.session_store import load_encrypted
from src.utils.config import Config


class DouyinAdapter(CreatorCenterAdapter):
    """Douyin — QR login + semi-automatic video publish."""

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright

        temp_state = Config.ROOT_DIR / "data" / "publish" / "_publish_state.json"
        screenshot_dir = Config.ROOT_DIR / "data" / "publish" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"douyin_fail_{int(time.time())}.png"
        page = None
        browser = None
        playwright = None
        timeout_ms = self.upload_timeout_sec * 1000
        max_title = int(self.limits.get("max_title_length", 55))
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

            logger.info("抖音：开始上传视频")
            if not upload_douyin_video(page, str(payload.video_path.resolve()), timeout_ms=min(timeout_ms, 120_000)):
                return PublishResult(success=False, error_message="未能定位抖音上传入口，请检查创作者中心页面")

            logger.info("抖音：等待视频处理完成")
            if not wait_for_douyin_video_ready(page, timeout_ms=timeout_ms):
                logger.warning("抖音视频处理未在超时内完成，继续尝试填写文案")

            logger.info("抖音：等待标题编辑器")
            if not wait_for_douyin_editor(page, timeout_ms=timeout_ms):
                logger.warning("抖音编辑器未在超时内出现，继续尝试填写文案")

            logger.info("抖音：填写标题")
            fill_douyin_title(page, payload.title or "", timeout_ms=min(timeout_ms, 30_000), max_length=max_title)

            description = (payload.description or "").strip()
            tags_line = format_douyin_tags(payload.tags)
            if tags_line and description:
                description = f"{description}\n{tags_line}"
            elif tags_line:
                description = tags_line

            if description:
                logger.info("抖音：填写简介/话题")
                filled = fill_douyin_description(page, description, timeout_ms=min(timeout_ms, 30_000))
                if not filled and payload.tags:
                    fill_douyin_topics(page, payload.tags, timeout_ms=min(timeout_ms, 15_000))

            logger.info("抖音：尝试选择推荐封面（可选，失败不阻塞）")
            if not select_douyin_publish_cover(page, timeout_ms=6_000):
                logger.warning("抖音封面未自动选中，将继续尝试直接发布")

            logger.info("抖音：点击发布")
            published = click_douyin_publish(page, timeout_ms=min(timeout_ms, 60_000))
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

            logger.info("抖音已自动点击发布")
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
            return PublishResult(
                success=True,
                platform_post_id=f"dy_{int(time.time())}",
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
