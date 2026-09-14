"""Kuaishou creator center adapter."""
from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from services.publishing.adapters.creator_center import CreatorCenterAdapter
from services.publishing.adapters.qr_helpers import is_login_success_url
from services.publishing.adapters.base import PublishPayload, PublishResult
from services.publishing.browser_nav import format_network_error_message, open_creator_pages
from services.publishing.browser_session import open_adapter_browser
from services.publishing.publish_warmup import warmup_creator_session
from services.publishing.human_pacing import pause_publish_step
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
from src.utils.config import Config


class KuaishouAdapter(CreatorCenterAdapter):
    """Kuaishou — QR login + semi-automatic video publish."""

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        screenshot_dir = Config.DATA_DIR / "publish" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"kuaishou_fail_{int(time.time())}.png"
        page = None
        timeout_ms = self.upload_timeout_sec * 1000
        max_title = int(self.limits.get("max_title_length", 50))
        max_tags = int(self.limits.get("max_tags", 4))
        try:
            with open_adapter_browser(session_path, mode="publish") as sess:
                page = sess.page
                warmup_url = self.qr_profile.get("post_login_url") or self.login_url
                open_creator_pages(
                    page,
                    warmup_url=warmup_url,
                    target_url=self.creator_url,
                    timeout_ms=60_000,
                )
                warmup_creator_session(page, platform_id="kuaishou")
                if not is_login_success_url(page.url, self._success_url_excludes()):
                    return PublishResult(success=False, error_message="会话已过期，请重新扫码登录")

                pause_publish_step(page, "上传视频")
                if not upload_kuaishou_video(page, str(payload.video_path.resolve()), timeout_ms=timeout_ms):
                    return PublishResult(success=False, error_message="未能定位快手上传入口，请检查创作者中心页面")

                pause_publish_step(page, "等待视频处理")
                if not wait_for_kuaishou_video_ready(page, timeout_ms=timeout_ms):
                    logger.warning("快手视频处理未在超时内完成，继续尝试填写文案")

                pause_publish_step(page, "进入编辑页")
                if not advance_past_kuaishou_upload_window(page, timeout_ms=min(timeout_ms, 60_000)):
                    logger.warning("快手仍停留在上传窗口，继续尝试填写文案")

                if not wait_for_kuaishou_editor(page, timeout_ms=min(timeout_ms, 60_000)):
                    logger.warning("快手编辑器未在超时内出现，继续尝试填写文案")

                dismiss_kuaishou_guide_tooltips(page)

                pause_publish_step(page, "填写标题")
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
                    pause_publish_step(page, "填写描述")
                    filled = fill_kuaishou_description(page, description, timeout_ms=min(timeout_ms, 60_000))
                    if not filled:
                        logger.warning("快手作品描述填写失败，请在发布页手动补充")

                if payload.cover_path:
                    logger.warning("快手自定义封面上传尚未实现，将使用平台默认封面")

                pause_publish_step(page, "点击发布")
                published = click_kuaishou_publish(page, timeout_ms=min(timeout_ms, 90_000))
                if not published:
                    try:
                        page.screenshot(path=str(screenshot_path))
                    except Exception:
                        pass
                    return PublishResult(
                        success=False,
                        error_message="未能自动点击发布或确认发布成功",
                    )

                logger.info("快手已自动点击发布")
                from services.publishing.metrics.post_id import build_platform_post_url, extract_platform_post_id

                post_id = extract_platform_post_id("kuaishou", page.url)
                comment_result = None
                if payload.first_comment:
                    from services.publishing.adapters.kuaishou_comment import post_kuaishou_first_comment
                    from services.publishing.first_comment_settings import get_first_comment_settings
                    from services.publishing.first_comment_timing import is_first_comment_deferred

                    if not is_first_comment_deferred("kuaishou"):
                        fc = get_first_comment_settings()
                        from services.publishing.metrics.post_id import is_synthetic_platform_post_id

                        comment_result = post_kuaishou_first_comment(
                            page,
                            text=payload.first_comment,
                            title=(payload.title or "").strip(),
                            photo_id=post_id if post_id and not is_synthetic_platform_post_id(post_id) else None,
                            delay_sec=int(fc.get("comment_delay_sec", 15)),
                            wait_max_sec=int(fc.get("comment_wait_max_sec", 60)),
                        )
                return PublishResult(
                    success=True,
                    platform_post_id=post_id or f"ks_{int(time.time())}",
                    platform_post_url=build_platform_post_url("kuaishou", post_id) if post_id else None,
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
                error_message=format_network_error_message(exc, platform="快手"),
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
        from services.publishing.adapters.kuaishou_comment import COMMENT_HUB_URL, post_kuaishou_first_comment
        from services.publishing.first_comment_timing import run_standalone_first_comment

        return run_standalone_first_comment(
            session_path,
            platform_id="kuaishou",
            platform_label="快手",
            creator_url=COMMENT_HUB_URL,
            warmup_url=self.qr_profile.get("post_login_url") or self.login_url,
            success_url_excludes=self._success_url_excludes(),
            post_fn=post_kuaishou_first_comment,
            post_id=post_id,
            post_url=post_url,
            title=title,
            text=text,
            delay_sec=delay_sec,
            wait_max_sec=wait_max_sec,
            post_id_kw="photo_id",
        )
