"""M0b cloud manifest client falls back to bundled pack when cloud unreachable."""
from __future__ import annotations

import pytest

from services.industry.constants import DEFAULT_INDUSTRY_ID
from services.industry.pack_client import fetch_pack_manifest


def test_fetch_pack_manifest_uses_bundled_when_cloud_unset(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    monkeypatch.delenv("AINEWS_CLOUD_API_BASE", raising=False)
    manifest = fetch_pack_manifest(DEFAULT_INDUSTRY_ID)
    assert manifest["path"] == DEFAULT_INDUSTRY_ID
    assert "content_yaml" in manifest
    assert manifest.get("pack_version") == "1.0.0"
