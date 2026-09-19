"""M0b: cloud industry pack manifest persisted under data dir and used for merge."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.industry.config_loader import build_effective_config, resolve_l2_pack_path
from services.industry.constants import DEFAULT_INDUSTRY_ID
from services.industry.pack_client import (
    apply_cloud_manifest_to_cache,
    fetch_pack_manifest,
    local_l2_pack_path,
    persist_pack_manifest,
)


CLOUD_L2_YAML = """
schema_version: 1
industry:
  path: tech/ai
  pack_version: "9.9.9"
scoring:
  overrides:
    keywords:
      tier_s: ["云端落盘关键词"]
content_methodology:
  target_audience_template: "云端测试受众"
"""


def test_persist_pack_manifest_writes_l2_yaml_under_data_dir(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    manifest = {
        "path": DEFAULT_INDUSTRY_ID,
        "pack_version": "9.9.9",
        "content_yaml": CLOUD_L2_YAML.strip() + "\n",
        "content_hash": "sha256:abc",
        "updated_at": "2026-09-19T00:00:00Z",
    }
    paths = persist_pack_manifest(manifest)
    l2_path = local_l2_pack_path(DEFAULT_INDUSTRY_ID)
    assert l2_path.is_file()
    assert paths["l2"] == l2_path
    assert "云端落盘关键词" in l2_path.read_text(encoding="utf-8")
    meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    assert meta["pack_version"] == "9.9.9"
    assert meta["content_hash"] == "sha256:abc"


def test_build_effective_config_prefers_persisted_pack_over_bundled(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    persist_pack_manifest(
        {
            "path": DEFAULT_INDUSTRY_ID,
            "pack_version": "9.9.9",
            "content_yaml": CLOUD_L2_YAML.strip() + "\n",
        }
    )
    assert resolve_l2_pack_path(DEFAULT_INDUSTRY_ID) == local_l2_pack_path(
        DEFAULT_INDUSTRY_ID
    )
    effective = build_effective_config(DEFAULT_INDUSTRY_ID)
    assert effective["pack_version"] == "9.9.9"
    assert "云端落盘关键词" in (
        effective.get("scoring") or {}
    ).get("ai_relevance_keywords", [])
    assert (
        (effective.get("content_methodology") or {}).get("target_audience_template")
        == "云端测试受众"
    )


def test_apply_cloud_manifest_to_cache_persists_then_refreshes_effective(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AINEWS_CLOUD_API_BASE", "https://cloud.example")
    monkeypatch.setenv("AINEWS_ACTIVE_INDUSTRY_ID", DEFAULT_INDUSTRY_ID)
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()

    payload = {
        "path": DEFAULT_INDUSTRY_ID,
        "pack_version": "9.9.9",
        "content_yaml": CLOUD_L2_YAML.strip() + "\n",
        "content_hash": "sha256:cloud",
    }

    class FakeResponse:
        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        manifest = fetch_pack_manifest(DEFAULT_INDUSTRY_ID)
        assert manifest["source"] == "cloud"
        effective = apply_cloud_manifest_to_cache(DEFAULT_INDUSTRY_ID)

    assert local_l2_pack_path(DEFAULT_INDUSTRY_ID).is_file()
    assert effective["pack_version"] == "9.9.9"
    from services.industry.config_loader import load_effective_cache

    cached = load_effective_cache(DEFAULT_INDUSTRY_ID)
    assert cached is not None
    assert cached["pack_version"] == "9.9.9"


def test_persist_pack_manifest_writes_l1_defaults_when_provided(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    from services.industry.config_loader import local_l1_defaults_path

    persist_pack_manifest(
        {
            "path": DEFAULT_INDUSTRY_ID,
            "content_yaml": CLOUD_L2_YAML.strip() + "\n",
            "l1_defaults_yaml": "schema_version: 1\nl1: tech\ndisplay_name: 科技云端\n",
        }
    )
    defaults = local_l1_defaults_path(DEFAULT_INDUSTRY_ID)
    assert defaults.is_file()
    assert "科技云端" in defaults.read_text(encoding="utf-8")
