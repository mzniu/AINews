"""Browser fingerprint probing and persistence for publish automation."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger

from services.publishing.browser_profile import load_browser_profile_config
from services.publishing.persona import load_persona, save_persona

FINGERPRINT_PROBE_JS = """() => {
  let webglVendor = '';
  let webglRenderer = '';
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (gl) {
      const ext = gl.getExtension('WEBGL_debug_renderer_info');
      if (ext) {
        webglVendor = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) || '';
        webglRenderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) || '';
      }
    }
  } catch (e) {}
  return {
    webdriver: navigator.webdriver,
    userAgent: navigator.userAgent,
    languages: Array.from(navigator.languages || []),
    plugins: navigator.plugins ? navigator.plugins.length : 0,
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory,
    webglVendor,
    webglRenderer,
    chrome: typeof window.chrome,
    platform: navigator.platform,
    probed_at: new Date().toISOString(),
  };
}"""


def probe_browser_fingerprint(page) -> dict[str, Any]:
    """Collect fingerprint signals from the current page context."""
    try:
        result = page.evaluate(FINGERPRINT_PROBE_JS)
        if isinstance(result, dict):
            return result
    except Exception as exc:
        logger.warning("Fingerprint probe failed: {}", exc)
    return {"error": "probe_failed", "probed_at": datetime.utcnow().isoformat()}


def merge_probe_into_persona(persona: dict[str, Any], probe: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Fill missing persona fingerprint fields from a live probe."""
    updated = dict(persona)
    changed = False

    def _set_if_missing(key: str, value: Any) -> None:
        nonlocal changed
        if value in (None, "", []):
            return
        if updated.get(key) in (None, "", []):
            updated[key] = value
            changed = True

    _set_if_missing("user_agent", probe.get("userAgent"))
    _set_if_missing("languages", probe.get("languages"))
    _set_if_missing("hardware_concurrency", probe.get("hardwareConcurrency"))
    _set_if_missing("device_memory", probe.get("deviceMemory"))
    _set_if_missing("webgl_vendor", probe.get("webglVendor"))
    _set_if_missing("webgl_renderer", probe.get("webglRenderer"))
    if probe.get("probed_at"):
        updated["fingerprint_captured_at"] = probe["probed_at"]
        changed = True
    return updated, changed


def capture_persona_fingerprint_from_page(page, account_id: str) -> dict[str, Any]:
    """Probe the live browser once and persist missing fingerprint fields to persona."""
    if not account_id or account_id.startswith("_"):
        return load_persona(account_id) if account_id else {}
    probe = probe_browser_fingerprint(page)
    persona = load_persona(account_id)
    merged, changed = merge_probe_into_persona(persona, probe)
    if changed:
        save_persona(account_id, merged)
        logger.info("Captured fingerprint persona for account {}", account_id)
    return merged


def persist_fingerprint_probe(account_id: str, probe: dict[str, Any], *, mode: str = "") -> None:
    """Write probe JSON to publisher_accounts.last_fingerprint_probe."""
    if not account_id or account_id.startswith("_"):
        return
    payload = dict(probe)
    if mode:
        payload["session_mode"] = mode
    try:
        from src.db.engine import session_scope
        from src.db.models.publishing import PublisherAccount

        with session_scope() as session:
            account = session.get(PublisherAccount, account_id)
            if account is None:
                return
            account.last_fingerprint_probe = json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Failed to persist fingerprint probe for {}: {}", account_id, exc)


def maybe_record_fingerprint_probe(page, account_id: str, *, mode: str = "") -> dict[str, Any] | None:
    """Run probe when browser_profile.probe_on_open is enabled."""
    cfg = load_browser_profile_config()
    if not cfg.get("probe_on_open"):
        return None
    probe = probe_browser_fingerprint(page)
    persist_fingerprint_probe(account_id, probe, mode=mode)
    logger.info(
        "Fingerprint probe account={} webdriver={} plugins={} webglVendor={}",
        account_id,
        probe.get("webdriver"),
        probe.get("plugins"),
        probe.get("webglVendor"),
    )
    return probe


def resolve_user_agent_from_persona(account_id: str | None) -> str | None:
    if not account_id:
        return None
    ua = load_persona(account_id).get("user_agent")
    return str(ua).strip() if ua else None


def resolve_user_agent(page=None, account_id: str | None = None) -> str:
    """Prefer persona UA; fall back to live page probe; then default publish UA."""
    from services.publishing.human_interaction import DEFAULT_PUBLISH_USER_AGENT

    stored = resolve_user_agent_from_persona(account_id)
    if stored:
        return stored
    if page is not None:
        try:
            ua = page.evaluate("() => navigator.userAgent")
            if ua:
                if account_id and not account_id.startswith("_"):
                    persona = load_persona(account_id)
                    if not persona.get("user_agent"):
                        persona["user_agent"] = ua
                        save_persona(account_id, persona)
                return str(ua)
        except Exception:
            pass
    return DEFAULT_PUBLISH_USER_AGENT
