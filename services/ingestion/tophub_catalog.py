"""TopHub node directory: fetch, cache, and stale fallback."""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.utils.paths import get_data_dir

_CACHE_FILENAME = "tophub_nodes.json"
_TTL_SECONDS = 24 * 60 * 60
_PAGE_SIZE = 20
_REQUEST_TIMEOUT_SEC = 30
_WALL_CLOCK_SEC = 75


class TophubAuthError(Exception):
    """Raised when the TopHub API key is missing."""


class TophubCatalogError(Exception):
    """Raised when the catalog cannot be fetched and no cache exists."""


@dataclass(frozen=True)
class TophubNodeCatalog:
    items: list[dict[str, Any]]
    stale: bool
    fetched_at: str


def _cache_path() -> Path:
    return get_data_dir() / "cache" / _CACHE_FILENAME


def _public_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "hashid": str(raw.get("hashid") or "").strip(),
        "name": str(raw.get("name") or "").strip(),
        "display": str(raw.get("display") or "").strip(),
        "domain": str(raw.get("domain") or "").strip(),
        "logo": str(raw.get("logo") or "").strip(),
    }


def _read_cache() -> dict[str, Any] | None:
    path = _cache_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return None
    return data


def _write_cache(items: list[dict[str, Any]], fetched_at: str) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": fetched_at, "items": items}
    fd, tmp_name = tempfile.mkstemp(prefix="tophub_nodes_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _catalog_from_cache(cache: dict[str, Any], *, stale: bool) -> TophubNodeCatalog:
    items = [_public_item(row) for row in cache.get("items") or [] if isinstance(row, dict)]
    items = [row for row in items if row["hashid"]]
    return TophubNodeCatalog(
        items=items,
        stale=stale,
        fetched_at=str(cache.get("fetched_at") or ""),
    )


def _fetch_all_pages(*, access_key: str, api_base_url: str) -> list[dict[str, Any]]:
    base = str(api_base_url or "").rstrip("/")
    headers = {"Authorization": access_key}
    items: list[dict[str, Any]] = []
    page = 1
    deadline = time.monotonic() + _WALL_CLOCK_SEC
    while True:
        if time.monotonic() > deadline:
            raise TophubCatalogError("TopHub 目录拉取超时")
        response = requests.get(
            f"{base}/nodes",
            params={"p": page},
            headers=headers,
            timeout=_REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        payload = response.json() or {}
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        for raw in rows:
            if isinstance(raw, dict):
                item = _public_item(raw)
                if item["hashid"]:
                    items.append(item)
        if len(rows) < _PAGE_SIZE:
            break
        page += 1
    return items


def list_tophub_nodes(
    *,
    refresh: bool = False,
    access_key: str,
    api_base_url: str,
) -> TophubNodeCatalog:
    key = str(access_key or "").strip()
    if not key:
        raise TophubAuthError("TopHub API Key 未配置，请在系统配置或环境变量 TOPHUB_ACCESS_KEY 中设置")

    cached = _read_cache()
    if cached and not refresh:
        fetched_at = str(cached.get("fetched_at") or "")
        try:
            stamp = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)
            if age.total_seconds() < _TTL_SECONDS:
                return _catalog_from_cache(cached, stale=False)
        except ValueError:
            pass

    try:
        items = _fetch_all_pages(access_key=key, api_base_url=api_base_url)
        fetched_at = datetime.now(timezone.utc).isoformat()
        _write_cache(items, fetched_at)
        return TophubNodeCatalog(items=items, stale=False, fetched_at=fetched_at)
    except TophubAuthError:
        raise
    except Exception as exc:
        if cached:
            return _catalog_from_cache(cached, stale=True)
        raise TophubCatalogError(str(exc) or "TopHub 目录拉取失败") from exc
