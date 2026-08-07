"""Tests for model configuration registry."""
from __future__ import annotations

import pytest

from services.model_config import registry as reg


@pytest.fixture
def isolated_models_config(tmp_path, monkeypatch):
    local_path = tmp_path / "models.local.yaml"
    monkeypatch.setattr(reg, "MODELS_LOCAL_PATH", local_path)
    return local_path


def test_mask_api_key():
    masked = reg.mask_api_key("sk-abcdefghijklmnop")
    assert masked.endswith("mnop")
    assert masked.startswith("*")
    assert reg.mask_api_key("") == ""


def test_save_and_load_roundtrip(isolated_models_config):
    cfg = {
        "version": 1,
        "language": {
            "active_id": "llm1",
            "profiles": [
                {
                    "id": "llm1",
                    "display_name": "Test LLM",
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com",
                    "model": "deepseek-chat",
                    "api_key": "sk-test-key",
                    "max_tokens": 4096,
                    "temperature": 0.5,
                    "enabled": True,
                }
            ],
        },
        "vision": {"active_id": None, "profiles": []},
    }
    reg.save_models_config(cfg)
    loaded = reg.load_models_config(migrate_env=False)
    assert loaded["language"]["profiles"][0]["api_key"] == "sk-test-key"
    assert loaded["language"]["active_id"] == "llm1"


def test_public_config_masks_keys(isolated_models_config):
    reg.save_models_config(
        {
            "version": 1,
            "language": {
                "active_id": "llm1",
                "profiles": [
                    {
                        "id": "llm1",
                        "display_name": "Test",
                        "provider": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "model": "deepseek-chat",
                        "api_key": "sk-secret1234",
                        "max_tokens": 8192,
                        "temperature": 0.7,
                        "enabled": True,
                    }
                ],
            },
            "vision": {"active_id": None, "profiles": []},
        }
    )
    public = reg.public_config(reg.load_models_config(migrate_env=False))
    prof = public["language"]["profiles"][0]
    assert "api_key" not in prof
    assert prof["api_key_masked"].endswith("1234")


def test_merge_keeps_existing_api_key_when_blank(isolated_models_config):
    reg.save_models_config(
        {
            "version": 1,
            "language": {
                "active_id": "llm1",
                "profiles": [
                    {
                        "id": "llm1",
                        "display_name": "Test",
                        "provider": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "model": "deepseek-chat",
                        "api_key": "sk-keep-me",
                        "max_tokens": 8192,
                        "temperature": 0.7,
                        "enabled": True,
                    }
                ],
            },
            "vision": {"active_id": None, "profiles": []},
        }
    )
    merged = reg.merge_incoming_config(
        {
            "version": 1,
            "language": {
                "active_id": "llm1",
                "profiles": [
                    {
                        "id": "llm1",
                        "display_name": "Renamed",
                        "provider": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "model": "deepseek-chat",
                        "api_key": "",
                        "max_tokens": 8192,
                        "temperature": 0.7,
                        "enabled": True,
                    }
                ],
            },
            "vision": {"active_id": None, "profiles": []},
        }
    )
    assert merged["language"]["profiles"][0]["api_key"] == "sk-keep-me"
    assert merged["language"]["profiles"][0]["display_name"] == "Renamed"


def test_migrate_from_env(isolated_models_config, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    cfg = reg.load_models_config(migrate_env=True)
    assert cfg["language"]["profiles"]
    assert cfg["language"]["profiles"][0]["api_key"] == "sk-from-env-key"
    assert isolated_models_config.exists()
