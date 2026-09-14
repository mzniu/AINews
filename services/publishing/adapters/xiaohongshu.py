"""Xiaohongshu creator center adapter."""
from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from services.publishing.adapters.creator_center import CreatorCenterAdapter
from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.adapters.base import PublishPayload, PublishResult
from services.publishing.browser_nav import open_creator_pages
from services.publishing.browser_session import open_adapter_browser
from services.publishing.publish_warmup import warmup_creator_session
from services.publishing.adapters.xiaohongshu_form import (
    click_xiaohongshu_publish,
    compose_xiaohongshu_description,
    fill_xiaohongshu_description,
    fill_xiaohongshu_title,
    upload_xiaohongshu_video,
    wait_for_xiaohongshu_editor,
    wait_for_xiaohongshu_video_ready,
)
from services.publishing.metrics.post_id import (
    build_xiaohongshu_post_url,
    extract_xiaohongshu_note_id,
)
from services.publishing.human_pacing import pause_publish_step
from src.utils.config import Config


class XiaohongshuAdapter(CreatorCenterAdapter):
    """Xiaohongshu — QR login + automatic video publish."""

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        screenshot_dir = Config.DATA_DIR / "publish" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"xiaohongshu_fail_{int(time.time())}.png"
        page = None
        timeout_ms = self.upload_timeout_sec * 1000
        max_title = int(self.limits.get("max_title_length", 20))
        try:
            with open_adapter_browser(session_path, mode="publish") as sess:
                page = sess.page
                warmup_url = (
                    self.qr_profile.get("post_login_url")
                    or "https://creator.xiaohongshu.com/new/home"
                )
                open_creator_pages(
                    page,
                    warmup_url=warmup_url,
                    target_url=self.creator_url,
                    timeout_ms=60_000,
                )
                warmup_creator_session(page, platform_id="xiaohongshu")
                if not is_login_success_url(page.url, self._success_url_excludes()):
                    return PublishResult(success=False, error_message="会话已过期，请重新扫码登录")

                pause_publish_step(page, "上传视频")
                if not upload_xiaohongshu_video(page, str(payload.video_path.resolve()), timeout_ms=timeout_ms):
                    return PublishResult(success=False, error_message="未能定位小红书上传入口，请检查创作者中心页面")

                pause_publish_step(page, "等待视频处理")
                if not wait_for_xiaohongshu_video_ready(page, timeout_ms=timeout_ms):
                    logger.warning("小红书视频处理未在超时内完成，继续尝试填写文案")

                if not wait_for_xiaohongshu_editor(page, timeout_ms=min(timeout_ms, 60_000)):
                    logger.warning("小红书编辑器未在超时内出现，继续尝试填写文案")

                pause_publish_step(page, "填写标题")
                if not fill_xiaohongshu_title(
                    page,
                    payload.title or "",
                    timeout_ms=min(timeout_ms, 60_000),
                    max_length=max_title,
                ):
                    logger.warning("小红书标题填写失败，发布按钮可能不可用")

                description = compose_xiaohongshu_description(payload.description or "", payload.tags)
                if description:
                    pause_publish_step(page, "填写描述")
                    if not fill_xiaohongshu_description(page, description, timeout_ms=min(timeout_ms, 60_000)):
                        logger.warning("小红书描述/话题填写失败，发布按钮可能不可用")

                if payload.cover_path:
                    logger.warning("小红书自定义封面上传尚未实现，将使用平台默认封面")

                pause_publish_step(page, "点击发布")
                published = click_xiaohongshu_publish(page, timeout_ms=min(timeout_ms, 90_000))
                if not published:
                    try:
                        page.screenshot(path=str(screenshot_path))
                    except Exception:
                        pass
                    return PublishResult(
                        success=False,
                        error_message="未能自动发布或确认发布成功",
                    )

                logger.info("小红书已自动发布")
                note_id = extract_xiaohongshu_note_id(page.url)
                platform_post_url = build_xiaohongshu_post_url(note_id) if note_id else None
                comment_result = None
                if payload.first_comment:
                    from services.publishing.adapters.xiaohongshu_comment import post_xiaohongshu_first_comment
                    from services.publishing.first_comment_settings import get_first_comment_settings
                    from services.publishing.first_comment_timing import is_first_comment_deferred
                    from services.publishing.metrics.post_id import is_synthetic_platform_post_id

                    if not is_first_comment_deferred("xiaohongshu"):
                        fc = get_first_comment_settings()
                        comment_result = post_xiaohongshu_first_comment(
                            page,
                            text=payload.first_comment,
                            title=(payload.title or "").strip(),
                            note_id=note_id if note_id and not is_synthetic_platform_post_id(note_id) else None,
                            delay_sec=int(fc.get("comment_delay_sec", 15)),
                            wait_max_sec=int(fc.get("comment_wait_max_sec", 60)),
                        )
                return PublishResult(
                    success=True,
                    platform_post_id=note_id or f"xhs_{int(time.time())}",
                    platform_post_url=platform_post_url,
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
            return PublishResult(success=False, error_message=str(exc))

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
        from services.publishing.adapters.xiaohongshu_comment import post_xiaohongshu_first_comment
        from services.publishing.first_comment_timing import run_standalone_first_comment

        return run_standalone_first_comment(
            session_path,
            platform_id="xiaohongshu",
            platform_label="小红书",
            creator_url=self.creator_url,
            warmup_url=self.qr_profile.get("post_login_url") or "https://creator.xiaohongshu.com/new/home",
            success_url_excludes=self._success_url_excludes(),
            post_fn=post_xiaohongshu_first_comment,
            post_id=post_id,
            post_url=post_url,
            title=title,
            text=text,
            delay_sec=delay_sec,
            wait_max_sec=wait_max_sec,
            post_id_kw="note_id",
        )
