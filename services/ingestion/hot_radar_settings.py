"""Hot radar config: base YAML + local overrides (API key, board toggles)."""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml

from src.utils.config import Config

HOT_RADAR_BASE_PATH = Config.ROOT_DIR / "config" / "hot_radar.yaml"
HOT_RADAR_LOCAL_PATH = Config.CONFIG_DIR / "hot_radar.local.yaml"

DEFAULT_BOARDS = [
    {
        "id": "sina_ai",
        "hashid": "MZd77QpdrO",
        "name": "新浪热榜",
        "display": "AI榜",
        "enabled": True,
    },
    {
        "id": "ithome_ai",
        "hashid": "47o8762eMm",
        "name": "IT之家",
        "display": "AI",
        "enabled": True,
    },
    {
        "id": "readhub_ai",
        "hashid": "b0vmrPldB1",
        "name": "Readhub",
        "display": "AI",
        "enabled": True,
    },
    {
        "id": "kr36_ai",
        "hashid": "x9oz2O1oXb",
        "name": "36氪",
        "display": "AI频道",
        "enabled": True,
    },
    {
        "id": "qbitai_daily",
        "hashid": "MZd7azPorO",
        "name": "量子位",
        "display": "每日最新",
        "enabled": True,
    },
    {
        "id": "aibase_daily",
        "hashid": "ENeYylkeY4",
        "name": "AIbase",
        "display": "AI日报",
        "enabled": True,
    },
    {
        "id": "ifeng_ai",
        "hashid": "5PdMP7pvmg",
        "name": "凤凰科技",
        "display": "人工智能",
        "enabled": True,
    },
]


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


def _mask_secret(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def load_hot_radar_base() -> dict[str, Any]:
    data = _load_yaml(HOT_RADAR_BASE_PATH)
    if not data:
        return {
            "enabled": True,
            "provider": "tophub",
            "api_base_url": "https://api.tophubdata.com",
            "refresh_cron": "0 8 * * *",
            "max_age_minutes": 1440,
            "title_match_threshold": 0.72,
            "boards": copy.deepcopy(DEFAULT_BOARDS),
        }
    if not data.get("boards"):
        data["boards"] = copy.deepcopy(DEFAULT_BOARDS)
    return data


def load_hot_radar_local() -> dict[str, Any]:
    return _load_yaml(HOT_RADAR_LOCAL_PATH)


def merge_boards(base_boards: list[dict[str, Any]], local_boards: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not local_boards:
        return copy.deepcopy(base_boards)
    local_by_id = {str(b.get("id")): b for b in local_boards if b.get("id")}
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for board in base_boards:
        bid = str(board.get("id") or "")
        override = local_by_id.get(bid) or {}
        row = {**board, **{k: v for k, v in override.items() if v is not None}}
        merged.append(row)
        if bid:
            seen.add(bid)
    for board in local_boards:
        bid = str(board.get("id") or "")
        if bid and bid not in seen:
            merged.append(copy.deepcopy(board))
    return merged


def merge_hot_radar_config(base: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key in ("enabled", "provider", "api_base_url", "refresh_cron", "max_age_minutes", "title_match_threshold"):
        if key in local:
            merged[key] = local[key]
    if local.get("scoring"):
        merged["scoring"] = _deep_merge(merged.get("scoring") or {}, local["scoring"])
    if local.get("bonuses"):
        merged["bonuses"] = _deep_merge(merged.get("bonuses") or {}, local["bonuses"])
    if local.get("matching"):
        merged["matching"] = _deep_merge(merged.get("matching") or {}, local["matching"])
    if local.get("batch"):
        merged["batch"] = _deep_merge(merged.get("batch") or {}, local["batch"])
    if local.get("inheritance"):
        merged["inheritance"] = _deep_merge(merged.get("inheritance") or {}, local["inheritance"])
    if local.get("discovery"):
        merged["discovery"] = _deep_merge(merged.get("discovery") or {}, local["discovery"])
    merged["boards"] = merge_boards(merged.get("boards") or [], local.get("boards"))
    access_key = str(local.get("access_key") or os.getenv("TOPHUB_ACCESS_KEY") or "").strip()
    if access_key:
        merged["access_key"] = access_key
    return merged


def load_merged_hot_radar_config() -> dict[str, Any]:
    return merge_hot_radar_config(load_hot_radar_base(), load_hot_radar_local())


def load_hot_radar_config(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        return _load_yaml(path)
    return load_merged_hot_radar_config()


def resolve_tophub_access_key(config: dict[str, Any] | None = None) -> str:
    cfg = config or load_merged_hot_radar_config()
    return str(cfg.get("access_key") or os.getenv("TOPHUB_ACCESS_KEY") or "").strip()


def enabled_boards(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = config or load_merged_hot_radar_config()
    return [b for b in cfg.get("boards") or [] if b.get("enabled", True) and b.get("hashid")]


def public_hot_radar_settings() -> dict[str, Any]:
    base = load_hot_radar_base()
    local = load_hot_radar_local()
    merged = merge_hot_radar_config(base, local)
    access_key = resolve_tophub_access_key(merged)
    boards_public = []
    for board in merged.get("boards") or []:
        boards_public.append(
            {
                "id": board.get("id"),
                "hashid": board.get("hashid"),
                "name": board.get("name"),
                "display": board.get("display"),
                "enabled": bool(board.get("enabled", True)),
            }
        )
    return {
        "enabled": bool(merged.get("enabled", True)),
        "provider": str(merged.get("provider") or "tophub"),
        "api_base_url": str(merged.get("api_base_url") or "https://api.tophubdata.com"),
        "refresh_cron": str(merged.get("refresh_cron") or "0 8 * * *"),
        "max_age_minutes": int(merged.get("max_age_minutes", 1440)),
        "title_match_threshold": float(merged.get("title_match_threshold", 0.72)),
        "boards": boards_public,
        "discovery": {
            "enabled": bool((merged.get("discovery") or {}).get("enabled", True)),
            "max_rank": int((merged.get("discovery") or {}).get("max_rank", 20)),
            "max_urls_per_refresh": int((merged.get("discovery") or {}).get("max_urls_per_refresh", 35)),
            "per_board_max": int((merged.get("discovery") or {}).get("per_board_max", 5)),
        },
        "batch": {
            "rescore_on_refresh": bool((merged.get("batch") or {}).get("rescore_on_refresh", True)),
            "rescore_days": int((merged.get("batch") or {}).get("rescore_days", 7)),
        },
        "has_access_key": bool(access_key),
        "access_key_masked": _mask_secret(access_key),
        "base_config_path": str(HOT_RADAR_BASE_PATH),
        "local_config_path": str(HOT_RADAR_LOCAL_PATH),
        "has_local_file": HOT_RADAR_LOCAL_PATH.exists(),
    }


def _normalize_board_row(row: dict[str, Any]) -> dict[str, Any]:
    hashid = str(row.get("hashid") or "").strip()
    board_id = str(row.get("id") or hashid).strip()
    if not hashid:
        raise ValueError("每个热榜必须填写 hashid")
    if not re.fullmatch(r"[A-Za-z0-9]+", hashid):
        raise ValueError(f"无效 hashid: {hashid}")
    return {
        "id": board_id,
        "hashid": hashid,
        "name": str(row.get("name") or board_id).strip(),
        "display": str(row.get("display") or "").strip(),
        "enabled": bool(row.get("enabled", True)),
    }


def save_hot_radar_settings(payload: dict[str, Any]) -> dict[str, Any]:
    existing = load_hot_radar_local()
    local: dict[str, Any] = {"version": payload.get("version", 1)}

    if "enabled" in payload:
        local["enabled"] = bool(payload["enabled"])
    if "api_base_url" in payload:
        local["api_base_url"] = str(payload["api_base_url"]).strip()
    if "refresh_cron" in payload:
        local["refresh_cron"] = str(payload["refresh_cron"]).strip()
    if "max_age_minutes" in payload:
        local["max_age_minutes"] = int(payload["max_age_minutes"])
    if "title_match_threshold" in payload:
        local["title_match_threshold"] = float(payload["title_match_threshold"])

    access_key = str(payload.get("access_key") or "").strip()
    if access_key:
        local["access_key"] = access_key
    elif existing.get("access_key"):
        local["access_key"] = existing["access_key"]

    if "boards" in payload:
        local["boards"] = [_normalize_board_row(row) for row in payload.get("boards") or []]

    if "discovery" in payload and isinstance(payload["discovery"], dict):
        disc_payload = payload["discovery"]
        local["discovery"] = {
            "enabled": bool(disc_payload.get("enabled", True)),
            "max_rank": int(disc_payload.get("max_rank", 20)),
            "max_urls_per_refresh": int(disc_payload.get("max_urls_per_refresh", 35)),
            "per_board_max": int(disc_payload.get("per_board_max", 5)),
        }

    if "batch" in payload and isinstance(payload["batch"], dict):
        batch_payload = payload["batch"]
        local["batch"] = {}
        if "rescore_on_refresh" in batch_payload:
            local["batch"]["rescore_on_refresh"] = bool(batch_payload["rescore_on_refresh"])
        if "rescore_days" in batch_payload:
            local["batch"]["rescore_days"] = int(batch_payload["rescore_days"])

    HOT_RADAR_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HOT_RADAR_LOCAL_PATH, "w", encoding="utf-8") as handle:
        yaml.dump(local, handle, allow_unicode=True, sort_keys=False)
    return public_hot_radar_settings()
