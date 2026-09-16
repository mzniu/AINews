from __future__ import annotations

from pathlib import Path

import pytest

from services.publishing.browser_profile import (
    account_id_from_session_path,
    is_profile_initialized,
    load_browser_profile_config,
    pending_profile_key,
    profile_path_for_account,
    promote_pending_profile,
    resolve_profile_dir,
)
from src.utils.config import Config


def test_load_browser_profile_config_defaults():
    cfg = load_browser_profile_config(
        {
            "defaults": {
                "browser_profile": {
                    "enabled": True,
                    "channel": "chrome",
                    "headless": False,
                    "fingerprint_shim": {"enabled": True},
                }
            }
        }
    )
    assert cfg["enabled"] is True
    assert cfg["channel"] == "chrome"
    assert cfg["headless"] is False
    assert cfg["backup_storage_state"] is True
    assert cfg["fingerprint_shim_enabled"] is True


def test_account_id_from_session_path():
    assert account_id_from_session_path("data/publish/sessions/abc123.enc") == "abc123"
    assert account_id_from_session_path(Path("data/publish/sessions/abc123.enc")) == "abc123"
    assert account_id_from_session_path("_publish_state.json") is None


def test_resolve_profile_dir_and_pending_key(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data_dir))
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    profile_dir = resolve_profile_dir("acc1")
    assert profile_dir == tmp_path / "data" / "publish" / "profiles" / "acc1"
    assert pending_profile_key("qr1") == "_pending_qr1"
    assert profile_path_for_account("acc1") == "data/publish/profiles/acc1"


def test_promote_pending_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    pending = resolve_profile_dir("_pending_qr1")
    pending.mkdir(parents=True)
    (pending / "Default").mkdir()
    dest = promote_pending_profile("_pending_qr1", "acc1")
    assert dest == resolve_profile_dir("acc1")
    assert is_profile_initialized(dest)
    assert not pending.exists()


def test_import_storage_state_into_context_adds_cookies():
    from unittest.mock import MagicMock

    from services.publishing.browser_profile import import_storage_state_into_context

    context = MagicMock()
    context.pages = []
    storage = {
        "cookies": [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}],
        "origins": [],
    }
    import_storage_state_into_context(context, storage)
    context.add_cookies.assert_called_once_with(storage["cookies"])
    context.new_page.assert_not_called()


def test_load_storage_state_dict_roundtrip(tmp_path, monkeypatch):
    from services.publishing.browser_profile import load_storage_state_dict
    from services.publishing.session_store import save_encrypted

    monkeypatch.setattr(Config, "ROOT_DIR", tmp_path)
    enc = tmp_path / "data" / "publish" / "sessions" / "acc1.enc"
    enc.parent.mkdir(parents=True)
    payload = b'{"cookies":[{"name":"a","value":"1"}],"origins":[]}'
    save_encrypted(enc, payload)
    loaded = load_storage_state_dict(enc)
    assert loaded["cookies"][0]["name"] == "a"


def test_session_keepalive_default_headless_false():
    from services.publishing.session_keepalive import load_session_keepalive_config

    cfg = load_session_keepalive_config(
        {"defaults": {"session_keepalive": {"enabled": True, "headless": False}}}
    )
    assert cfg["headless"] is False
