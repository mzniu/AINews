"""Ingestion crawl settings: base YAML + local overrides."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from src.utils.config import Config

INGESTION_BASE_PATH = Config.ROOT_DIR / "config" / "ingestion_sources.yaml"
INGESTION_LOCAL_PATH = Config.ROOT_DIR / "config" / "ingestion.local.yaml"

DEFAULT_WORKER = {
    "poll_interval_sec": 5,
}

DEFAULT_DEFAULTS = {
    "schedule_cron": "0 * * * *",
    "timezone": "Asia/Shanghai",
    "max_list_pages": 2,
    "max_new_articles_per_run": 30,
    "request_delay_sec": 2,
    "use_playwright": False,
    "download_images": True,
    "max_images_per_article": 20,
    "max_image_bytes": 10485760,
    "stop_after_existing": 5,
    "story_cluster": {
        "enabled": True,
        "title_threshold": 0.72,
        "hours_window": 72,
    },
}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_ingestion_local() -> dict[str, Any]:
    return _load_yaml(INGESTION_LOCAL_PATH)


def load_ingestion_base() -> dict[str, Any]:
    data = _load_yaml(INGESTION_BASE_PATH)
    if not data:
        return {"version": 1, "defaults": dict(DEFAULT_DEFAULTS), "sources": []}
    defaults = {**DEFAULT_DEFAULTS, **(data.get("defaults") or {})}
    data["defaults"] = defaults
    return data


def merge_ingestion_config(base: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    if local.get("defaults"):
        merged["defaults"] = _deep_merge(merged.get("defaults") or {}, local["defaults"])
    if local.get("worker"):
        merged["worker"] = _deep_merge(merged.get("worker") or dict(DEFAULT_WORKER), local["worker"])

    local_sources = local.get("sources") or {}
    if local_sources:
        sources_out = []
        for src in merged.get("sources") or []:
            sid = src.get("id")
            if sid and sid in local_sources:
                sources_out.append(_deep_merge(src, local_sources[sid]))
            else:
                sources_out.append(copy.deepcopy(src))
        merged["sources"] = sources_out
    merged["worker"] = {**DEFAULT_WORKER, **(merged.get("worker") or {})}
    return merged


def load_merged_ingestion_config() -> dict[str, Any]:
    base = load_ingestion_base()
    local = load_ingestion_local()
    return merge_ingestion_config(base, local)


def save_ingestion_local(payload: dict[str, Any]) -> dict[str, Any]:
    local = {
        "version": payload.get("version", 1),
        "worker": payload.get("worker") or dict(DEFAULT_WORKER),
        "defaults": payload.get("defaults") or {},
        "sources": payload.get("sources") or {},
    }
    INGESTION_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INGESTION_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return local


def public_ingestion_settings() -> dict[str, Any]:
    base = load_ingestion_base()
    local = load_ingestion_local()
    merged = merge_ingestion_config(base, local)
    source_overrides = local.get("sources") or {}
    sources_public = []
    for src in merged.get("sources") or []:
        sid = src.get("id")
        sources_public.append(
            {
                "id": sid,
                "display_name": src.get("display_name", sid),
                "enabled": bool(src.get("enabled", True)),
                "schedule_cron": src.get("schedule_cron"),
                "adapter": src.get("adapter"),
                "base_url": src.get("base_url"),
                "list_url": src.get("list_url"),
                "max_list_pages": src.get("max_list_pages"),
                "max_new_articles_per_run": src.get("max_new_articles_per_run"),
                "request_delay_sec": src.get("request_delay_sec"),
                "download_images": src.get("download_images"),
                "max_images_per_article": src.get("max_images_per_article"),
                "stop_after_existing": src.get("stop_after_existing"),
                "has_local_override": sid in source_overrides,
            }
        )
    return {
        "version": merged.get("version", 1),
        "worker": merged.get("worker") or dict(DEFAULT_WORKER),
        "defaults": merged.get("defaults") or dict(DEFAULT_DEFAULTS),
        "sources": sources_public,
        "base_config_path": str(INGESTION_BASE_PATH),
        "local_config_path": str(INGESTION_LOCAL_PATH),
        "has_local_file": INGESTION_LOCAL_PATH.exists(),
    }


def build_local_from_public(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract only overridable fields for local yaml."""
    source_overrides: dict[str, Any] = {}
    for src in payload.get("sources") or []:
        sid = src.get("id")
        if not sid:
            continue
        source_overrides[sid] = {
            "enabled": bool(src.get("enabled", True)),
            "schedule_cron": src.get("schedule_cron"),
            "max_list_pages": src.get("max_list_pages"),
            "max_new_articles_per_run": src.get("max_new_articles_per_run"),
            "request_delay_sec": src.get("request_delay_sec"),
            "download_images": src.get("download_images"),
            "max_images_per_article": src.get("max_images_per_article"),
            "stop_after_existing": src.get("stop_after_existing"),
        }
    return {
        "version": payload.get("version", 1),
        "worker": payload.get("worker") or dict(DEFAULT_WORKER),
        "defaults": payload.get("defaults") or {},
        "sources": source_overrides,
    }
