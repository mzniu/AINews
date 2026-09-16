"""Persistent Chrome profile management for publish automation."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.publishing.fingerprint_shim import build_combined_stealth_init_script
from services.publishing.human_interaction import STEALTH_CHROMIUM_ARGS
from services.publishing.registry import load_publishing_yaml
from services.publishing.session_store import load_encrypted, save_encrypted
from src.utils.config import Config
from src.utils.paths import get_data_dir, resolve_data_path

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Playwright

BROWSER_PROFILE_VERSION = 1

PERSISTENT_CONTEXT_DEFAULTS: dict[str, Any] = {
    "locale": "zh-CN",
    "timezone_id": "Asia/Shanghai",
    "args": list(STEALTH_CHROMIUM_ARGS),
}


def load_browser_profile_config(yaml: dict[str, Any] | None = None) -> dict[str, Any]:
    data = yaml or load_publishing_yaml()
    defaults = data.get("defaults") or {}
    cfg = dict(defaults.get("browser_profile") or {})
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "channel": str(cfg.get("channel", "chrome") or "chrome"),
        "headless": bool(cfg.get("headless", False)),
        "profile_root": str(cfg.get("profile_root", "data/publish/profiles")),
        "backup_storage_state": bool(cfg.get("backup_storage_state", True)),
        "migrate_from_storage_state": bool(cfg.get("migrate_from_storage_state", True)),
        "probe_on_open": bool(cfg.get("probe_on_open", False)),
        "fingerprint_shim_enabled": bool((cfg.get("fingerprint_shim") or {}).get("enabled", True)),
    }


def resolve_profile_dir(profile_key: str, *, root: Path | None = None) -> Path:
    cfg = load_browser_profile_config()
    base = root or resolve_data_path(cfg["profile_root"])
    return base / profile_key


def pending_profile_key(qr_session_id: str) -> str:
    return f"_pending_{qr_session_id}"


def account_id_from_session_path(session_path: Path | str) -> str | None:
    path = Path(session_path)
    stem = path.stem.strip()
    if not stem or stem.startswith("_"):
        return None
    return stem


def is_profile_initialized(profile_dir: Path) -> bool:
    if not profile_dir.is_dir():
        return False
    try:
        return any(profile_dir.iterdir())
    except OSError:
        return False


def profile_path_for_account(account_id: str) -> str:
    rel = resolve_profile_dir(account_id).relative_to(get_data_dir())
    return f"data/{rel.as_posix()}"


def promote_pending_profile(pending_key: str, account_id: str) -> Path:
    """Move a pending QR login profile to the permanent account directory."""
    src = resolve_profile_dir(pending_key)
    dest = resolve_profile_dir(account_id)
    if not is_profile_initialized(src):
        dest.mkdir(parents=True, exist_ok=True)
        return dest
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    logger.info("Promoted browser profile {} -> {}", pending_key, account_id)
    return dest


def backup_context_to_enc(context: BrowserContext, enc_path: Path) -> None:
    storage = context.storage_state()
    payload = json.dumps(storage, ensure_ascii=False).encode("utf-8")
    save_encrypted(enc_path, payload)


def load_storage_state_dict(session_enc_path: Path) -> dict[str, Any]:
    return json.loads(load_encrypted(session_enc_path).decode("utf-8"))


def import_storage_state_into_context(context: BrowserContext, storage: dict[str, Any]) -> None:
    """Import Playwright storage_state JSON into a persistent browser context."""
    cookies = list(storage.get("cookies") or [])
    if cookies:
        context.add_cookies(cookies)

    origins = list(storage.get("origins") or [])
    if not origins:
        return

    page = context.pages[0] if context.pages else context.new_page()
    for origin_entry in origins:
        origin = str(origin_entry.get("origin") or "").strip()
        if not origin:
            continue
        local_storage = list(origin_entry.get("localStorage") or [])
        session_storage = list(origin_entry.get("sessionStorage") or [])
        if not local_storage and not session_storage:
            continue
        try:
            page.goto(origin, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            logger.warning("Skip origin storage import for {}: {}", origin, exc)
            continue
        if local_storage:
            page.evaluate(
                """(items) => {
                    for (const item of items) {
                        try { localStorage.setItem(item.name, item.value); } catch (e) {}
                    }
                }""",
                local_storage,
            )
        if session_storage:
            page.evaluate(
                """(items) => {
                    for (const item of items) {
                        try { sessionStorage.setItem(item.name, item.value); } catch (e) {}
                    }
                }""",
                session_storage,
            )


def _channel_candidates(channel: str) -> list[str | None]:
    normalized = (channel or "chrome").strip().lower()
    if normalized == "chromium":
        return [None]
    if normalized == "chrome":
        return ["chrome", "msedge", None]
    if normalized == "msedge":
        return ["msedge", "chrome", None]
    return [normalized, "chrome", "msedge", None]


def apply_publish_stealth_scripts(context: BrowserContext, profile_key: str | None = None) -> None:
    from services.publishing.persona import load_persona

    cfg = load_browser_profile_config()
    if not cfg.get("fingerprint_shim_enabled", True):
        from services.publishing.human_interaction import STEALTH_INIT_SCRIPT

        context.add_init_script(STEALTH_INIT_SCRIPT)
        return
    persona = load_persona(profile_key) if profile_key else {}
    context.add_init_script(build_combined_stealth_init_script(persona))


def launch_persistent_publish_context(
    playwright: Playwright,
    profile_dir: Path,
    *,
    headless: bool = False,
    storage_state_path: Path | None = None,
    profile_key: str | None = None,
) -> BrowserContext:
    """Launch a headed persistent Chrome context for the given profile directory."""
    cfg = load_browser_profile_config()
    profile_dir.mkdir(parents=True, exist_ok=True)
    launch_kwargs: dict[str, Any] = {
        **PERSISTENT_CONTEXT_DEFAULTS,
        "headless": headless,
    }

    last_error: Exception | None = None
    context: BrowserContext | None = None
    for channel in _channel_candidates(cfg["channel"]):
        try:
            kwargs = dict(launch_kwargs)
            if channel:
                kwargs["channel"] = channel
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                **kwargs,
            )
            apply_publish_stealth_scripts(context, profile_key or profile_dir.name)
            logger.debug(
                "Launched persistent profile {} (channel={}, headless={})",
                profile_dir.name,
                channel or "chromium",
                headless,
            )
            break
        except Exception as exc:
            last_error = exc
            logger.warning("Persistent context launch failed (channel={}): {}", channel, exc)
    if context is None:
        raise RuntimeError(f"无法启动 Chrome Profile：{last_error}")

    if storage_state_path is not None and storage_state_path.is_file():
        try:
            storage = load_storage_state_dict(storage_state_path)
            import_storage_state_into_context(context, storage)
            logger.info(
                "Imported storage_state into profile {} (cookies={}, origins={})",
                profile_dir.name,
                len(storage.get("cookies") or []),
                len(storage.get("origins") or []),
            )
        except Exception as exc:
            logger.warning("Failed to import storage_state for {}: {}", profile_dir.name, exc)

    return context


def migrate_account_session(
    account_id: str,
    session_enc_path: Path,
    *,
    post_login_url: str | None = None,
) -> Path:
    """Import encrypted storage_state into a new persistent profile directory."""
    from playwright.sync_api import sync_playwright

    profile_dir = resolve_profile_dir(account_id)
    if is_profile_initialized(profile_dir):
        return profile_dir

    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = launch_persistent_publish_context(
            playwright,
            profile_dir,
            headless=False,
            storage_state_path=session_enc_path,
        )
        page = context.pages[0] if context.pages else context.new_page()
        if post_login_url:
            try:
                page.goto(post_login_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(5000)
            except Exception as exc:
                logger.warning("Profile migration warmup failed for {}: {}", account_id, exc)
        if load_browser_profile_config()["backup_storage_state"]:
            backup_context_to_enc(context, session_enc_path)
        context.close()
    logger.info("Migrated storage_state to profile for account {}", account_id)
    return profile_dir


def ensure_account_profile(
    profile_key: str,
    *,
    session_enc_path: Path | None = None,
    post_login_url: str | None = None,
) -> Path:
    """Return an initialized profile dir, migrating from .enc when configured."""
    profile_dir = resolve_profile_dir(profile_key)
    if is_profile_initialized(profile_dir):
        return profile_dir
    cfg = load_browser_profile_config()
    if (
        cfg["migrate_from_storage_state"]
        and session_enc_path is not None
        and session_enc_path.is_file()
    ):
        migrate_account_session(profile_key, session_enc_path, post_login_url=post_login_url)
    else:
        profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir
