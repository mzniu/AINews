"""TopHub node catalog: pagination, disk cache, auth errors."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from services.ingestion.tophub_catalog import (
    TophubAuthError,
    TophubCatalogError,
    list_tophub_nodes,
)


def _node(hashid: str, name: str, display: str = "热榜") -> dict:
    return {
        "hashid": hashid,
        "name": name,
        "display": display,
        "domain": f"{name.lower()}.example",
        "logo": "",
    }


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            err = requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err


@pytest.fixture()
def catalog_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    yield tmp_path
    get_data_dir.cache_clear()


def test_list_tophub_nodes_rejects_empty_access_key():
    with pytest.raises(TophubAuthError):
        list_tophub_nodes(access_key="", api_base_url="https://api.tophubdata.com")


def test_list_tophub_nodes_concatenates_pages(catalog_home, monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params or {})
        page = int((params or {}).get("p") or 1)
        if page == 1:
            return _FakeResponse({"data": [_node("hashAaa00001", "知乎") for _ in range(20)]})
        if page == 2:
            return _FakeResponse({"data": [_node("hashBbb00002", "微博")]})
        return _FakeResponse({"data": []})

    monkeypatch.setattr("services.ingestion.tophub_catalog.requests.get", fake_get)
    catalog = list_tophub_nodes(
        access_key="test-key",
        api_base_url="https://api.tophubdata.com",
    )
    assert [item["hashid"] for item in catalog.items] == ["hashAaa00001"] * 20 + ["hashBbb00002"]
    assert catalog.stale is False
    assert catalog.fetched_at
    assert len(calls) == 2


def test_list_tophub_nodes_uses_fresh_cache(catalog_home, monkeypatch: pytest.MonkeyPatch):
    cache_dir = catalog_home / "cache"
    cache_dir.mkdir(parents=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    (cache_dir / "tophub_nodes.json").write_text(
        json.dumps({"fetched_at": fetched_at, "items": [_node("cachedHash001", "缓存榜")]}),
        encoding="utf-8",
    )
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return _FakeResponse({"data": []})

    monkeypatch.setattr("services.ingestion.tophub_catalog.requests.get", fake_get)
    catalog = list_tophub_nodes(access_key="test-key", api_base_url="https://api.tophubdata.com")
    assert [item["hashid"] for item in catalog.items] == ["cachedHash001"]
    assert catalog.stale is False
    assert calls["n"] == 0


def test_list_tophub_nodes_refresh_bypasses_cache(catalog_home, monkeypatch: pytest.MonkeyPatch):
    cache_dir = catalog_home / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "tophub_nodes.json").write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "items": [_node("cachedHash001", "缓存榜")],
            }
        ),
        encoding="utf-8",
    )

    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse({"data": [_node("freshHash0001", "新榜")]})

    monkeypatch.setattr("services.ingestion.tophub_catalog.requests.get", fake_get)
    catalog = list_tophub_nodes(
        refresh=True,
        access_key="test-key",
        api_base_url="https://api.tophubdata.com",
    )
    assert [item["hashid"] for item in catalog.items] == ["freshHash0001"]
    assert catalog.stale is False


def test_list_tophub_nodes_refetches_corrupt_cache(catalog_home, monkeypatch: pytest.MonkeyPatch):
    cache_dir = catalog_home / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "tophub_nodes.json").write_text("{not-json", encoding="utf-8")

    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResponse({"data": [_node("repairedHash1", "修复榜")]})

    monkeypatch.setattr("services.ingestion.tophub_catalog.requests.get", fake_get)
    catalog = list_tophub_nodes(access_key="test-key", api_base_url="https://api.tophubdata.com")
    assert catalog.items[0]["hashid"] == "repairedHash1"


def test_list_tophub_nodes_raises_without_cache_on_fetch_error(catalog_home, monkeypatch: pytest.MonkeyPatch):
    def fake_get(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("services.ingestion.tophub_catalog.requests.get", fake_get)
    with pytest.raises(TophubCatalogError):
        list_tophub_nodes(access_key="test-key", api_base_url="https://api.tophubdata.com")


def test_list_tophub_nodes_returns_stale_cache_on_fetch_error(catalog_home, monkeypatch: pytest.MonkeyPatch):
    cache_dir = catalog_home / "cache"
    cache_dir.mkdir(parents=True)
    old_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    (cache_dir / "tophub_nodes.json").write_text(
        json.dumps({"fetched_at": old_at, "items": [_node("oldHash000001", "旧榜")]}),
        encoding="utf-8",
    )

    def fake_get(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("services.ingestion.tophub_catalog.requests.get", fake_get)
    catalog = list_tophub_nodes(access_key="test-key", api_base_url="https://api.tophubdata.com")
    assert catalog.stale is True
    assert catalog.items[0]["hashid"] == "oldHash000001"


def test_list_tophub_nodes_does_not_write_partial_cache(catalog_home, monkeypatch: pytest.MonkeyPatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        page = int((params or {}).get("p") or 1)
        if page == 1:
            return _FakeResponse({"data": [_node(f"page1Hash{i:04d}", "第一页") for i in range(20)]})
        raise RuntimeError("page 2 failed")

    monkeypatch.setattr("services.ingestion.tophub_catalog.requests.get", fake_get)
    with pytest.raises(TophubCatalogError):
        list_tophub_nodes(access_key="test-key", api_base_url="https://api.tophubdata.com")
    assert not (catalog_home / "cache" / "tophub_nodes.json").exists()
