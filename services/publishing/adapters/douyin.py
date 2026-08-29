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
    prepare_douyin_ai_cover,
    upload_douyin_video,
    wait_for_douyin_editor,
    wait_for_douyin_video_ready,
)
from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.adapters.base import PublishPayload, PublishResult, SessionStatus
from services.publishing.browser_nav import format_network_error_message, open_creator_pages
from services.publishing.browser_session import open_adapter_browser
from services.publishing.publish_warmup import warmup_creator_session
from services.publishing.human_pacing import pause_publish_step
from src.utils.config import Config


class DouyinAdapter(CreatorCenterAdapter):
    """Douyin — QR login + semi-automatic video publish."""

    def validate_session(self, session_path: Path) -> SessionStatus:
        try:
            from services.publishing.metrics.adapters.douyin import probe_douyin_creator_session

            active, status_code = probe_douyin_creator_session(session_path, headless=True)
            if active:
                return "active"
            if status_code == 8:
                return "expired"
            return "unknown"
        except Exception as exc:
            logger.warning("Douyin session validate failed: {}", exc)
            return "unknown"

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        screenshot_dir = Config.ROOT_DIR / "data" / "publish" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"douyin_fail_{int(time.time())}.png"
        page = None
        timeout_ms = self.upload_timeout_sec * 1000
        max_title = int(self.limits.get("max_title_length", 55))
        try:
            with open_adapter_browser(session_path, mode="publish") as sess:
                page = sess.page
                warmup_url = (
                    self.qr_profile.get("post_login_url")
                    or "https://creator.douyin.com/creator-micro/home"
                )
                open_creator_pages(
                    page,
                    warmup_url=warmup_url,
                    target_url=self.creator_url,
                    timeout_ms=60_000,
                )
                warmup_creator_session(page, platform_id="douyin")
                if not is_login_success_url(page.url, self._success_url_excludes()):
                    return PublishResult(success=False, error_message="会话已过期，请重新扫码登录")

                pause_publish_step(page, "开始上传")
                logger.info("抖音：开始上传视频")
                if not upload_douyin_video(page, str(payload.video_path.resolve()), timeout_ms=min(timeout_ms, 120_000)):
                    return PublishResult(success=False, error_message="未能定位抖音上传入口，请检查创作者中心页面")

                pause_publish_step(page, "等待视频处理")
                logger.info("抖音：等待视频处理完成")
                if not wait_for_douyin_video_ready(page, timeout_ms=timeout_ms):
                    logger.warning("抖音视频处理未在超时内完成，继续尝试填写文案")

                pause_publish_step(page, "填写标题")
                logger.info("抖音：等待标题编辑器")
                if not wait_for_douyin_editor(page, timeout_ms=timeout_ms):
                    logger.warning("抖音编辑器未在超时内出现，继续尝试填写文案")

                title_text = (payload.title or "").strip()
                if title_text:
                    logger.info("抖音：填写标题")
                    if not fill_douyin_title(
                        page,
                        title_text,
                        timeout_ms=min(timeout_ms, 30_000),
                        max_length=max_title,
                    ):
                        try:
                            page.screenshot(path=str(screenshot_path))
                        except Exception:
                            pass
                        return PublishResult(
                            success=False,
                            error_message="未能填写抖音标题（页面可能未滚动到标题输入框）",
                        )

                pause_publish_step(page, "选择 AI 封面")
                logger.info("抖音：等待并选择平台 AI 推荐封面")
                if not prepare_douyin_ai_cover(page, timeout_ms=90_000):
                    logger.warning("抖音 AI 推荐封面未就绪或未选中，将继续尝试发布")

                description = (payload.description or "").strip()
                tags_line = format_douyin_tags(payload.tags)
                if tags_line and description:
                    description = f"{description}\n{tags_line}"
                elif tags_line:
                    description = tags_line

                if description:
                    pause_publish_step(page, "填写简介")
                    logger.info("抖音：填写简介/话题")
                    filled = fill_douyin_description(page, description, timeout_ms=min(timeout_ms, 30_000))
                    if not filled and payload.tags:
                        fill_douyin_topics(page, payload.tags, timeout_ms=min(timeout_ms, 15_000))

                pause_publish_step(page, "点击发布")
                logger.info("抖音：点击发布")
                published = click_douyin_publish(page, timeout_ms=min(timeout_ms, 60_000))
                if not published:
                    try:
                        page.screenshot(path=str(screenshot_path))
                    except Exception:
                        pass
                    return PublishResult(
                        success=False,
                        error_message="未能自动点击发布或确认发布成功",
                    )

                logger.info("抖音已自动点击发布")
                from services.publishing.metrics.post_id import (
                    build_platform_post_url,
                    extract_platform_post_id,
                    is_synthetic_platform_post_id,
                )

                post_id = extract_platform_post_id("douyin", page.url)
                comment_result = None
                if payload.first_comment:
                    from services.publishing.adapters.douyin_comment import post_douyin_first_comment
                    from services.publishing.first_comment_settings import get_first_comment_settings

                    fc = get_first_comment_settings()
                    comment_result = post_douyin_first_comment(
                        page,
                        text=payload.first_comment,
                        title=title_text,
                        video_id=post_id if post_id and not is_synthetic_platform_post_id(post_id) else None,
                        delay_sec=int(fc.get("comment_delay_sec", 15)),
                        wait_max_sec=int(fc.get("comment_wait_max_sec", 60)),
                    )
                return PublishResult(
                    success=True,
                    platform_post_id=post_id or f"dy_{int(time.time())}",
                    platform_post_url=build_platform_post_url("douyin", post_id) if post_id else None,
                    manual_publish_pending=False,
                    comment_result=comment_result,
                )
        except PlaywrightTimeoutError as exc:
            if page is not None:
                try:
                    page.screenshot(path=str(screenshot_path))
                except Exception:
                    pass
            return PublishResult(success=False, error_message=str(exc))
        except Exception as exc:
            if page is not None:
                try:
                    page.screenshot(path=str(screenshot_path))
                except Exception:
                    pass
            return PublishResult(
                success=False,
                error_message=format_network_error_message(exc, platform="抖音"),
            )

    def post_first_comment(
        self,
        session_path: Path,
        *,
        post_id: str | None,
        post_url: str | None,
        title: str | None,
        text: str,
        delay_sec: int = 15,
        wait_max_sec: int = 60,
    ):
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        from services.publishing.adapters.base import CommentResult
        from services.publishing.adapters.douyin_comment import post_douyin_first_comment
        from services.publishing.browser_nav import format_network_error_message, open_creator_pages
        from services.publishing.browser_session import open_adapter_browser
        from services.publishing.metrics.post_id import is_synthetic_platform_post_id
        from services.publishing.publish_warmup import warmup_creator_session

        video_id = None if is_synthetic_platform_post_id(post_id) else post_id
        try:
            with open_adapter_browser(session_path, mode="publish") as sess:
                page = sess.page
                warmup_url = (
                    self.qr_profile.get("post_login_url")
                    or "https://creator.douyin.com/creator-micro/home"
                )
                open_creator_pages(
                    page,
                    warmup_url=warmup_url,
                    target_url=self.creator_url,
                    timeout_ms=60_000,
                )
                warmup_creator_session(page, platform_id="douyin")
                if not is_login_success_url(page.url, self._success_url_excludes()):
                    return CommentResult(success=False, error_message="会话已过期，请重新扫码登录")
                return post_douyin_first_comment(
                    page,
                    text=text,
                    title=(title or "").strip(),
                    video_id=video_id,
                    delay_sec=delay_sec,
                    wait_max_sec=wait_max_sec,
                )
        except PlaywrightTimeoutError as exc:
            return CommentResult(success=False, error_message=str(exc))
        except Exception as exc:
            return CommentResult(
                success=False,
                error_message=format_network_error_message(exc, platform="抖音"),
            )
