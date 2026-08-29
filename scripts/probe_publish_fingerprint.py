#!/usr/bin/env python3
"""Probe publish browser fingerprint for an account and compare with stored persona."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from services.publishing.browser_session import open_adapter_browser
from services.publishing.fingerprint_probe import (
    capture_persona_fingerprint_from_page,
    persist_fingerprint_probe,
    probe_browser_fingerprint,
)
from services.publishing.persona import load_persona
from services.publishing.registry import get_platform_config
from src.db.engine import init_db, session_scope
from src.db.models.publishing import PublisherAccount
from src.utils.config import Config


def _warmup_url(platform: str) -> str:
    try:
        cfg = get_platform_config(platform)
    except Exception:
        return "about:blank"
    qr_profile = cfg.get("qr_profile") or {}
    return str(qr_profile.get("post_login_url") or cfg.get("creator_url") or "about:blank")


def probe_account(account_id: str, *, save: bool = True) -> dict:
    init_db()
    with session_scope() as session:
        account = session.get(PublisherAccount, account_id)
        if account is None:
            raise SystemExit(f"Account not found: {account_id}")
        platform = account.platform
        session_path = account.session_path

    session_file = Config.ROOT_DIR / session_path
    if not session_file.is_file():
        raise SystemExit(f"Session file missing: {session_file}")

    with open_adapter_browser(session_file, mode="metrics", profile_key=account_id) as sess:
        page = sess.page
        url = _warmup_url(platform)
        if url != "about:blank":
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        probe = probe_browser_fingerprint(page)
        persona = capture_persona_fingerprint_from_page(page, account_id)
        if save:
            persist_fingerprint_probe(account_id, probe, mode="probe_script")

    return {
        "account_id": account_id,
        "platform": platform,
        "probe": probe,
        "persona": persona,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe publish browser fingerprint")
    parser.add_argument("--account-id", required=True, help="Publisher account id")
    parser.add_argument("--no-save", action="store_true", help="Do not write probe to database")
    parser.add_argument("--json", action="store_true", help="Print raw JSON only")
    args = parser.parse_args()

    result = probe_account(args.account_id, save=not args.no_save)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    probe = result["probe"]
    persona = result["persona"]
    logger.info("Account: {}", result["account_id"])
    logger.info("Platform: {}", result["platform"])
    logger.info("webdriver={} plugins={} chrome={}", probe.get("webdriver"), probe.get("plugins"), probe.get("chrome"))
    logger.info("userAgent={}", probe.get("userAgent"))
    logger.info("webglVendor={}", probe.get("webglVendor"))
    logger.info("webglRenderer={}", probe.get("webglRenderer"))
    logger.info("persona.user_agent={}", persona.get("user_agent"))
    logger.info("persona.webgl_vendor={}", persona.get("webgl_vendor"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
