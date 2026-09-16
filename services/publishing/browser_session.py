"""Unified browser session entry for publish automation."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

from loguru import logger

from services.publishing.browser_lock import browser_lock
from services.publishing.browser_profile import (
    account_id_from_session_path,
    backup_context_to_enc,
    ensure_account_profile,
    is_profile_initialized,
    launch_persistent_publish_context,
    load_browser_profile_config,
)
from services.publishing.job_recovery import load_publish_lock_timeout_sec, load_qr_lock_timeout_sec
from services.publishing.human_interaction import open_stealth_browser
from services.publishing.session_store import load_encrypted
from src.utils.config import Config

PublishSessionMode = Literal["login", "publish", "keepalive", "metrics"]


@dataclass
class PublishBrowserSession:
    playwright: object
    context: object
    page: object
    profile_dir: Path | None
    mode: PublishSessionMode
    profile_key: str
    session_enc_path: Path | None = None
    _browser: object | None = None

    def close(self) -> None:
        cfg = load_browser_profile_config()
        try:
            if cfg["backup_storage_state"] and self.session_enc_path is not None:
                backup_context_to_enc(self.context, self.session_enc_path)
        except Exception as exc:
            logger.warning("Failed to backup storage_state for {}: {}", self.profile_key, exc)
        try:
            self.context.close()
        except Exception:
            pass
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        try:
            self.playwright.stop()
        except Exception:
            pass


def _default_headless(mode: PublishSessionMode, override: bool | None) -> bool:
    if override is not None:
        return override
    cfg = load_browser_profile_config()
    if mode == "login":
        return False
    return bool(cfg.get("headless", False))


def _session_enc_path_for_key(profile_key: str) -> Path:
    return Config.DATA_DIR / "publish" / "sessions" / f"{profile_key}.enc"


def _bootstrap_publish_fingerprint(page, profile_key: str, *, mode: PublishSessionMode) -> None:
    if not profile_key or profile_key.startswith("_pending"):
        return
    try:
        page.goto("about:blank", wait_until="domcontentloaded", timeout=15_000)
    except Exception:
        pass
    from services.publishing.fingerprint_probe import (
        capture_persona_fingerprint_from_page,
        maybe_record_fingerprint_probe,
    )

    capture_persona_fingerprint_from_page(page, profile_key)
    maybe_record_fingerprint_probe(page, profile_key, mode=mode)



@contextmanager
def open_publish_session(
    profile_key: str,
    *,
    mode: PublishSessionMode,
    headless: bool | None = None,
    session_enc_path: Path | None = None,
) -> Iterator[PublishBrowserSession]:
    """Open a persistent Chrome profile session for login/publish/keepalive/metrics."""
    cfg = load_browser_profile_config()
    if not cfg["enabled"]:
        raise RuntimeError("browser_profile is disabled; use open_adapter_browser()")

    resolved_headless = _default_headless(mode, headless)
    if mode in ("login", "publish", "keepalive") and resolved_headless:
        logger.warning("Forcing headless=false for publish session mode={}", mode)
        resolved_headless = False

    enc_path = session_enc_path or _session_enc_path_for_key(profile_key)
    profile_dir = ensure_account_profile(
        profile_key,
        session_enc_path=enc_path if enc_path.is_file() else None,
    )

    from playwright.sync_api import sync_playwright

    lock_timeout = load_qr_lock_timeout_sec() if mode == "login" else load_publish_lock_timeout_sec()
    with browser_lock(timeout_sec=lock_timeout):
        playwright = sync_playwright().start()
        storage_for_launch = enc_path if enc_path.is_file() and not is_profile_initialized(profile_dir) else None
        context = launch_persistent_publish_context(
            playwright,
            profile_dir,
            headless=resolved_headless,
            storage_state_path=storage_for_launch,
            profile_key=profile_key,
        )
        page = context.pages[0] if context.pages else context.new_page()
        if mode != "login":
            _bootstrap_publish_fingerprint(page, profile_key, mode=mode)
        session = PublishBrowserSession(
            playwright=playwright,
            context=context,
            page=page,
            profile_dir=profile_dir,
            mode=mode,
            profile_key=profile_key,
            session_enc_path=enc_path if enc_path.is_file() else None,
        )
        try:
            yield session
        finally:
            session.close()


@contextmanager
def open_legacy_stealth_session(
    session_path: Path,
    *,
    headless: bool = False,
) -> Iterator[PublishBrowserSession]:
    """Legacy Playwright Chromium + encrypted storage_state snapshot."""
    from playwright.sync_api import sync_playwright

    temp_state = Config.DATA_DIR / "publish" / "_legacy_state.json"
    account_id = account_id_from_session_path(session_path) or "unknown"
    with browser_lock(timeout_sec=load_publish_lock_timeout_sec()):
        playwright = sync_playwright().start()
        temp_state.write_bytes(load_encrypted(session_path))
        browser, context = open_stealth_browser(
            playwright,
            headless=headless,
            storage_state=str(temp_state),
            account_id=account_id if account_id != "unknown" else None,
        )
        page = context.new_page()
        session = PublishBrowserSession(
            playwright=playwright,
            context=context,
            page=page,
            profile_dir=None,
            mode="publish",
            profile_key=account_id,
            session_enc_path=session_path,
            _browser=browser,
        )
        try:
            yield session
        finally:
            session.close()
            temp_state.unlink(missing_ok=True)


@contextmanager
def open_adapter_browser(
    session_path: Path,
    *,
    mode: PublishSessionMode = "publish",
    headless: bool | None = None,
    profile_key: str | None = None,
) -> Iterator[PublishBrowserSession]:
    """Profile-first session open with legacy storage_state fallback."""
    from services.publishing.persona import ensure_persona_for_account, set_publish_persona_account

    cfg = load_browser_profile_config()
    key = profile_key or account_id_from_session_path(session_path)
    if key:
        ensure_persona_for_account(key)
    set_publish_persona_account(key)
    try:
        if cfg["enabled"] and key:
            with open_publish_session(
                key,
                mode=mode,
                headless=headless,
                session_enc_path=session_path,
            ) as session:
                yield session
            return
        with open_legacy_stealth_session(
            session_path,
            headless=_default_headless(mode, headless),
        ) as session:
            yield session
    finally:
        set_publish_persona_account(None)
