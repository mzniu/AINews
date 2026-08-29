"""Probe creator first-comment flow for P2 platforms.

Usage:
  python scripts/probe_creator_first_comment.py --platform kuaishou
  python scripts/probe_creator_first_comment.py --platform wechat_channels --title "关键词"
  python scripts/probe_creator_first_comment.py --platform xiaohongshu --post --comment "你觉得这个数靠谱吗？"

PASS (dry-run): 作品列表可取 + 能定位评论输入框
PASS (--post):  上述 + 评论提交成功
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from services.publishing.human_interaction import open_stealth_browser
from services.publishing.human_pacing import human_pause
from services.publishing.session_store import load_encrypted
from src.db.engine import get_session_factory, init_db
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config

PLATFORM_HANDLERS = {
    "kuaishou": {
        "label": "快手",
        "module": "services.publishing.adapters.kuaishou_comment",
        "fn": "post_kuaishou_first_comment",
        "list_url": "https://cp.kuaishou.com/article/manage/video",
        "id_kw": "photo_id",
    },
    "wechat_channels": {
        "label": "视频号",
        "module": "services.publishing.adapters.wechat_channels_comment",
        "fn": "post_wechat_first_comment",
        "list_url": "https://channels.weixin.qq.com/platform/interaction/comment",
        "id_kw": "export_id",
    },
    "xiaohongshu": {
        "label": "小红书",
        "module": "services.publishing.adapters.xiaohongshu_comment",
        "fn": "post_xiaohongshu_first_comment",
        "list_url": "https://creator.xiaohongshu.com/new/note-manager",
        "id_kw": "note_id",
    },
}


def _pick_account(platform: str) -> PublisherAccount | None:
    init_db()
    with get_session_factory()() as session:
        return (
            session.query(PublisherAccount)
            .filter(PublisherAccount.platform == platform, PublisherAccount.status == "active")
            .order_by(PublisherAccount.last_publish_at.desc())
            .first()
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe creator first-comment selectors")
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORM_HANDLERS))
    parser.add_argument("--title", default="")
    parser.add_argument("--post-id", default="")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--comment", default="你觉得这条资讯最关键的点是什么？")
    parser.add_argument("--delay-sec", type=int, default=5)
    parser.add_argument("--wait-max-sec", type=int, default=60)
    args = parser.parse_args()

    handler = PLATFORM_HANDLERS[args.platform]
    account = _pick_account(args.platform)
    if account is None:
        print(f"未找到活跃 {handler['label']} 账号，请先在发布中心扫码绑定")
        return 2

    session_path = Config.ROOT_DIR / account.session_path
    if not session_path.exists():
        print(f"会话文件不存在: {session_path}")
        return 2

    import importlib

    module = importlib.import_module(handler["module"])
    post_fn = getattr(module, handler["fn"])

    report_dir = Config.ROOT_DIR / "data" / "publish"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"probe_{args.platform}_first_comment_report.json"

    temp_state = report_dir / f"_probe_{args.platform}_state.json"
    playwright = None
    browser = None
    result: dict = {
        "platform": args.platform,
        "started_at": datetime.utcnow().isoformat(),
        "dry_run": not args.post,
    }

    try:
        temp_state.write_bytes(load_encrypted(session_path))
        playwright = sync_playwright().start()
        browser, context = open_stealth_browser(
            playwright,
            headless=False,
            storage_state=str(temp_state),
        )
        page = context.new_page()
        page.goto(handler["list_url"], wait_until="domcontentloaded", timeout=60_000)
        human_pause(page, "page_load")

        kwargs = {
            "text": args.comment if args.post else "你觉得这条资讯最关键的点是什么？",
            "title": args.title,
            "delay_sec": args.delay_sec,
            "wait_max_sec": args.wait_max_sec,
            "dry_run": not args.post,
        }
        post_id = (args.post_id or "").strip() or None
        if post_id:
            kwargs[handler["id_kw"]] = post_id

        comment_result = post_fn(page, **kwargs)
        result["success"] = comment_result.success
        result["error"] = comment_result.error_message
        result["final_url"] = page.url
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        if comment_result.success:
            print(f"PASS_{'POST' if args.post else 'DRY_RUN'}: {handler['label']} 首评探测成功")
            print(f"report: {report_path}")
            return 0
        print(f"FAIL: {comment_result.error_message}")
        print(f"report: {report_path}")
        return 1
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        temp_state.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
