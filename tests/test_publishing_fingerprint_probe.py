from __future__ import annotations

from services.publishing.fingerprint_probe import merge_probe_into_persona, probe_browser_fingerprint
from services.publishing.fingerprint_shim import (
    build_combined_stealth_init_script,
    build_fingerprint_init_script,
    fingerprint_values_from_persona,
)
from services.publishing.persona import DEFAULT_PERSONA, save_persona, load_persona
from src.utils.config import Config


def test_fingerprint_values_from_persona_merges_defaults():
    values = fingerprint_values_from_persona({"webgl_vendor": "Custom Vendor"})
    assert values["webgl_vendor"] == "Custom Vendor"
    assert values["languages"] == ["zh-CN", "zh", "en"]


def test_build_fingerprint_init_script_masks_signals():
    script = build_fingerprint_init_script({"hardware_concurrency": 12})
    assert "webdriver" in script
    assert "hardwareConcurrency" in script
    assert "plugins" in script
    assert "WEBGL_debug_renderer_info" in script
    assert "chrome.csi" in script


def test_build_combined_stealth_includes_base_script():
    script = build_combined_stealth_init_script()
    assert "webdriver" in script
    assert "hardwareConcurrency" in script


def test_merge_probe_into_persona_fills_missing_fields():
    persona = {
        "typing_delay_scale": 1.0,
        "pause_multiplier": 1.0,
        "warmup_moves": 3,
    }
    probe = {
        "userAgent": "Mozilla/5.0 Chrome/138",
        "webglVendor": "Google Inc. (Intel)",
        "webglRenderer": "ANGLE Intel",
        "hardwareConcurrency": 16,
        "deviceMemory": 16,
        "languages": ["zh-CN", "en"],
        "probed_at": "2026-08-11T00:00:00.000Z",
    }
    merged, changed = merge_probe_into_persona(persona, probe)
    assert changed is True
    assert merged["user_agent"] == probe["userAgent"]
    assert merged["webgl_vendor"] == probe["webglVendor"]
    assert merged["hardware_concurrency"] == 16


def test_probe_browser_fingerprint_uses_page_evaluate():
    page = type("Page", (), {})()
    page.evaluate = lambda _js: {
        "webdriver": None,
        "userAgent": "ua",
        "languages": ["zh-CN"],
        "plugins": 3,
        "webglVendor": "Intel",
        "webglRenderer": "UHD",
        "chrome": "object",
    }
    result = probe_browser_fingerprint(page)
    assert result["webdriver"] is None
    assert result["plugins"] == 3


def test_save_persona_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    save_persona("acc1", {"user_agent": "Mozilla/test", "pause_multiplier": 1.1})
    loaded = load_persona("acc1")
    assert loaded["user_agent"] == "Mozilla/test"
    assert loaded["pause_multiplier"] == 1.1
