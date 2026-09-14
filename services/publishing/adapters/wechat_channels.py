"""WeChat Channels creator center adapter."""
from __future__ import annotations

import time
from pathlib import Path

from loguru import logger

from services.publishing.adapters.base import AccountInfo, PublishPayload, PublishResult
from services.publishing.adapters.creator_center import CreatorCenterAdapter
from services.publishing.adapters.wechat_channels_form import (
    click_wechat_publish,
    compose_post_desc_text,
    declare_wechat_original,
    ensure_wechat_description,
    fill_wechat_cover,
    fill_wechat_description,
    fill_wechat_title,
    upload_wechat_video,
    wait_for_wechat_video_ready,
    is_wechat_upload_blocked,
)
from services.publishing.metadata_bridge import normalize_wechat_title
from services.publishing.browser_session import open_adapter_browser
from services.publishing.human_interaction import human_idle_on_page
from services.publishing.publish_warmup import warmup_creator_session
from services.publishing.human_pacing import human_pause, pause_publish_step
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


class WechatChannelsAdapter(CreatorCenterAdapter):
    def _success_url_excludes(self) -> list[str]:
        return list(self.qr_profile.get("success_url_excludes") or ["login"])

    def _extract_account_from_page(self, page) -> AccountInfo:
        del page
        uid = f"wx_{int(time.time())}"
        return AccountInfo(nickname="视频号账号", platform_uid=uid, avatar_url=None)

    def validate_session(self, session_path: Path) -> str:
        try:
            from services.publishing.metrics.adapters.wechat_channels import probe_wechat_creator_session

            active, err_code = probe_wechat_creator_session(session_path, headless=True)
            if active:
                return self._check_or_refresh_session(session_path, headless=True, persist=False)
            if err_code not in (None, 0):
                return "expired"
        except Exception as exc:
            logger.warning("WeChat Channels API session probe failed: {}", exc)
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
        try:
            with open_adapter_browser(session_path, mode="keepalive", headless=headless) as sess:
                page = sess.page
                for url in (
                    "https://channels.weixin.qq.com/platform/post/create",
                    "https://channels.weixin.qq.com/platform",
                    self.creator_url,
                ):
                    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    human_pause(page, "page_load")
                    human_idle_on_page(page, moves=1)
                    if "login" not in page.url.lower():
                        return "active"
            return "expired"
        except Exception as exc:
            logger.warning(f"Session validate failed: {exc}")
            return "unknown"

    def publish_video(self, session_path: Path, payload: PublishPayload) -> PublishResult:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        screenshot_dir = Config.DATA_DIR / "publish" / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"fail_{int(time.time())}.png"
        page = None
        try:
            with open_adapter_browser(session_path, mode="publish") as sess:
                page = sess.page
                page.goto(self.creator_url, wait_until="domcontentloaded", timeout=60_000)
                warmup_creator_session(page, platform_id="wechat_channels")
                if "login" in page.url.lower():
                    return PublishResult(success=False, error_message="会话已过期，请重新扫码登录")

                timeout_ms = self.upload_timeout_sec * 1000
                pause_publish_step(page, "上传视频")
                logger.info("视频号：上传视频")
                if not upload_wechat_video(
                    page,
                    str(payload.video_path.resolve()),
                    timeout_ms=min(timeout_ms, 120_000),
                ):
                    try:
                        page.screenshot(path=str(screenshot_path))
                    except Exception:
                        pass
                    return PublishResult(success=False, error_message="未能定位视频号上传入口")

                pause_publish_step(page, "等待视频处理")
                logger.info("视频号：等待视频上传/处理完成")
                if not wait_for_wechat_video_ready(page, timeout_ms=timeout_ms):
                    return PublishResult(
                        success=False,
                        error_message="视频尚未上传完成，请稍后重试或检查网络",
                    )

                max_title = int(self.limits.get("max_title_length", 30))
                title_text = normalize_wechat_title(payload.title or "", max_title_length=max_title)
                pause_publish_step(page, "填写标题")
                logger.info("视频号：填写标题")
                fill_wechat_title(page, title_text, timeout_ms=min(timeout_ms, 60_000), max_length=max_title)
                desc_text = compose_post_desc_text(
                    main_line2=payload.main_line2 or "",
                    sub_title=payload.sub_title or "",
                    sub_title2=payload.sub_title2 or "",
                    summary=payload.summary or "",
                    tags=payload.tags,
                    description=payload.description,
                )
                if desc_text:
                    pause_publish_step(page, "填写描述")
                    logger.info("视频号：填写描述（键盘写入，%d 字）", len(desc_text))
                    filled = fill_wechat_description(
                        page,
                        desc_text,
                        timeout_ms=min(self.upload_timeout_sec * 1000, 60_000),
                    )
                    if not filled:
                        logger.warning(
                            "视频号描述未自动填入，请检查页面是否为 contenteditable/Shadow DOM 结构"
                        )
                if payload.cover_path:
                    pause_publish_step(page, "上传封面")
                    cover_filled = fill_wechat_cover(
                        page,
                        payload.cover_path,
                        timeout_ms=min(self.upload_timeout_sec * 1000, 60_000),
                    )
                    if not cover_filled:
                        logger.warning("视频号封面未自动上传，请在发布页手动设置封面")
                pause_publish_step(page, "声明原创")
                if not declare_wechat_original(
                    page,
                    timeout_ms=min(self.upload_timeout_sec * 1000, 60_000),
                ):
                    logger.warning("视频号声明原创未自动勾选，请在发布页手动声明")
                if desc_text:
                    pause_publish_step(page, "确认描述")
                    if not ensure_wechat_description(
                        page,
                        desc_text,
                        timeout_ms=min(self.upload_timeout_sec * 1000, 30_000),
                    ):
                        try:
                            page.screenshot(path=str(screenshot_path))
                        except Exception:
                            pass
                        return PublishResult(
                            success=False,
                            error_message="视频号描述未能写入编辑器（发表会丢失简介），已取消自动发表",
                        )

                pause_publish_step(page, "点击发表")
                published = click_wechat_publish(
                    page,
                    timeout_ms=min(timeout_ms, 90_000),
                )
                if not published:
                    upload_still_blocked = is_wechat_upload_blocked(page)
                    try:
                        page.screenshot(path=str(screenshot_path))
                    except Exception:
                        pass
                    error_message = "未能自动点击发表或确认发表成功，请检查封面/原创声明是否完成"
                    if upload_still_blocked:
                        error_message = "视频尚未上传完成（请上传视频），请稍后重试"
                    return PublishResult(
                        success=False,
                        error_message=error_message,
                    )

                logger.info("视频号已自动点击发表")
                from services.publishing.metrics.post_id import build_platform_post_url, extract_platform_post_id

                post_id = extract_platform_post_id("wechat_channels", page.url)
                comment_result = None
                if payload.first_comment:
                    from services.publishing.adapters.wechat_channels_comment import post_wechat_first_comment
                    from services.publishing.first_comment_settings import get_first_comment_settings
                    from services.publishing.first_comment_timing import is_first_comment_deferred
                    from services.publishing.metrics.post_id import is_synthetic_platform_post_id

                    if not is_first_comment_deferred("wechat_channels"):
                        fc = get_first_comment_settings()
                        comment_result = post_wechat_first_comment(
                            page,
                            text=payload.first_comment,
                            title=title_text,
                            export_id=post_id if post_id and not is_synthetic_platform_post_id(post_id) else None,
                            delay_sec=int(fc.get("comment_delay_sec", 15)),
                            wait_max_sec=int(fc.get("comment_wait_max_sec", 60)),
                        )
                return PublishResult(
                    success=True,
                    platform_post_id=post_id or f"wx_{int(time.time())}",
                    platform_post_url=build_platform_post_url("wechat_channels", post_id) if post_id else None,
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
        from services.publishing.adapters.wechat_channels_comment import post_wechat_first_comment
        from services.publishing.first_comment_timing import run_standalone_first_comment

        from services.publishing.adapters.wechat_channels_comment import COMMENT_HUB_URL

        return run_standalone_first_comment(
            session_path,
            platform_id="wechat_channels",
            platform_label="视频号",
            creator_url=COMMENT_HUB_URL,
            warmup_url="https://channels.weixin.qq.com/platform/post/list",
            success_url_excludes=self._success_url_excludes(),
            post_fn=post_wechat_first_comment,
            post_id=post_id,
            post_url=post_url,
            title=title,
            text=text,
            delay_sec=delay_sec,
            wait_max_sec=wait_max_sec,
            post_id_kw="export_id",
        )
