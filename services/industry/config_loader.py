"""Build and cache effective per-L2 config (repo catalog + industry packs + local)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

from services.industry.constants import DEFAULT_INDUSTRY_ID, is_valid_industry_id
from services.industry.profile import get_active_industry_id
from src.utils.config import Config
from src.utils.paths import get_data_dir

PACKS_ROOT = Config.ROOT_DIR / "packs"
_CACHE_DIRNAME = "effective"
_CONFIG_FILENAME = "config.json"


def effective_config_overlays_enabled() -> bool:
    """Allow unit tests to opt out of reading cache/effective overlays."""
    flag = os.getenv("AINEWS_DISABLE_EFFECTIVE_CONFIG", "").strip().lower()
    return flag not in {"1", "true", "yes"}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_pack_layers(*layers: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for layer in layers:
        if not layer:
            continue
        merged = _deep_merge(merged, layer)
    return merged


def merge_scoring_pack_overrides(
    base: dict[str, Any], pack_overrides: dict[str, Any]
) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in pack_overrides.items():
        if key == "keywords" and isinstance(value, dict):
            merged["keywords"] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _ref_id(entry: Any) -> str:
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        return str(entry.get("ref") or "").strip()
    return ""


def apply_catalog_ref_ops(
    catalog: list[dict[str, Any]],
    spec: dict[str, Any] | None,
    *,
    id_key: str = "id",
) -> list[dict[str, Any]]:
    if not spec:
        return copy.deepcopy(catalog)
    by_id = {str(row.get(id_key)): copy.deepcopy(row) for row in catalog if row.get(id_key)}
    adds = spec.get("add") or []
    if adds:
        for row in by_id.values():
            row["enabled"] = False
    for entry in spec.get("remove") or []:
        ref = _ref_id(entry)
        if ref:
            by_id.pop(ref, None)
    for entry in adds:
        ref = _ref_id(entry)
        if not ref or ref not in by_id:
            continue
        row = by_id[ref]
        if isinstance(entry, dict):
            for key, value in entry.items():
                if key == "ref":
                    continue
                row[key] = value
            if "enabled" not in entry:
                row["enabled"] = True
        else:
            row["enabled"] = True
    for entry in spec.get("patch") or []:
        ref = _ref_id(entry)
        if not ref or ref not in by_id or not isinstance(entry, dict):
            continue
        for key, value in entry.items():
            if key == "ref":
                continue
            by_id[ref][key] = value
    return list(by_id.values())


def local_packs_root() -> Path:
    return get_data_dir() / "cache" / "packs"


def local_l2_pack_path(industry_id: str) -> Path:
    l1, l2 = industry_id.split("/", 1)
    return local_packs_root() / l1 / f"{l2}.yaml"


def local_l1_defaults_path(industry_id: str) -> Path:
    l1, _ = industry_id.split("/", 1)
    return local_packs_root() / l1 / "_defaults.yaml"


def resolve_l2_pack_path(industry_id: str) -> Path:
    local = local_l2_pack_path(industry_id)
    if local.is_file():
        return local
    l1, l2 = industry_id.split("/", 1)
    return PACKS_ROOT / l1 / f"{l2}.yaml"


def resolve_l1_defaults_path(industry_id: str) -> Path:
    local = local_l1_defaults_path(industry_id)
    if local.is_file():
        return local
    l1, _ = industry_id.split("/", 1)
    return PACKS_ROOT / l1 / "_defaults.yaml"


def _pack_paths(industry_id: str) -> tuple[Path, Path]:
    return resolve_l1_defaults_path(industry_id), resolve_l2_pack_path(industry_id)


def _load_repo_scoring_base() -> dict[str, Any]:
    from services.ingestion.scoring_settings import SCORING_BASE_PATH, _load_local_yaml

    base = _load_yaml(SCORING_BASE_PATH)
    local = _load_local_yaml()
    if not local:
        return base
    return _deep_merge(base, local)


def _load_repo_ingestion_base() -> dict[str, Any]:
    from services.ingestion.settings import (
        load_ingestion_base,
        load_ingestion_local,
        merge_ingestion_config,
    )

    return merge_ingestion_config(load_ingestion_base(), load_ingestion_local())


def _load_repo_hot_radar_base() -> dict[str, Any]:
    from services.ingestion.hot_radar_settings import (
        load_hot_radar_base,
        load_hot_radar_local,
        merge_hot_radar_config,
    )

    return merge_hot_radar_config(load_hot_radar_base(), load_hot_radar_local())


def _apply_pack_to_scoring(
    repo_scoring: dict[str, Any], pack_doc: dict[str, Any]
) -> dict[str, Any]:
    scoring_block = pack_doc.get("scoring") or {}
    result = copy.deepcopy(repo_scoring)
    if scoring_block.get("profile"):
        result["profile"] = scoring_block["profile"]
    overrides = scoring_block.get("overrides") or {}
    if overrides:
        result = merge_scoring_pack_overrides(result, overrides)
        keywords = overrides.get("keywords")
        if isinstance(keywords, dict):
            flat: list[str] = []
            for tier in ("tier_s", "tier_a", "tier_b", "tier_c"):
                flat.extend(str(k) for k in (keywords.get(tier) or []))
            if flat:
                result["ai_relevance_keywords"] = flat
    return result


def build_effective_config(industry_id: str | None = None) -> dict[str, Any]:
    active = (industry_id or get_active_industry_id()).strip()
    if not is_valid_industry_id(active):
        raise ValueError(f"Invalid industry_id: {active}")
    l1_path, l2_path = _pack_paths(active)
    pack_doc = merge_pack_layers(_load_yaml(l1_path), _load_yaml(l2_path))

    ingestion_base = _load_repo_ingestion_base()
    ingestion_sources = apply_catalog_ref_ops(
        ingestion_base.get("sources") or [],
        (pack_doc.get("ingestion") or {}).get("sources"),
        id_key="id",
    )
    ingestion = {**ingestion_base, "sources": ingestion_sources}

    hot_radar_base = _load_repo_hot_radar_base()
    hot_radar_pack = pack_doc.get("hot_radar") or {}
    hot_radar_boards = apply_catalog_ref_ops(
        hot_radar_base.get("boards") or [],
        hot_radar_pack.get("boards"),
        id_key="id",
    )
    hot_radar = {**hot_radar_base, **{k: v for k, v in hot_radar_pack.items() if k != "boards"}}
    hot_radar["boards"] = hot_radar_boards

    scoring = _apply_pack_to_scoring(_load_repo_scoring_base(), pack_doc)

    return {
        "industry_id": active,
        "ingestion": ingestion,
        "hot_radar": hot_radar,
        "scoring": scoring,
        "content_methodology": pack_doc.get("content_methodology") or {},
        "pack_version": (pack_doc.get("industry") or {}).get("pack_version"),
    }


def effective_cache_path(industry_id: str) -> Path:
    safe = industry_id.replace("/", "_")
    return get_data_dir() / "cache" / _CACHE_DIRNAME / safe / _CONFIG_FILENAME


def write_effective_cache(
    industry_id: str, payload: dict[str, Any], *, manifest_hash: str
) -> Path:
    path = effective_cache_path(industry_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {**payload, "manifest_hash": manifest_hash}
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_effective_cache(industry_id: str | None = None) -> dict[str, Any] | None:
    active = (industry_id or get_active_industry_id()).strip()
    path = effective_cache_path(active)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def manifest_hash_for_pack(industry_id: str) -> str:
    l2_path = resolve_l2_pack_path(industry_id)
    if not l2_path.is_file():
        return ""
    digest = hashlib.sha256(l2_path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def refresh_effective_cache(industry_id: str | None = None) -> dict[str, Any]:
    active = (industry_id or get_active_industry_id()).strip()
    effective = build_effective_config(active)
    write_effective_cache(
        active, effective, manifest_hash=manifest_hash_for_pack(active)
    )
    return effective


def scoring_from_effective_cache() -> dict[str, Any] | None:
    if not effective_config_overlays_enabled():
        return None
    cached = load_effective_cache()
    if cached is None:
        return None
    scoring = cached.get("scoring")
    return scoring if isinstance(scoring, dict) else None


def hot_radar_from_effective_cache() -> dict[str, Any] | None:
    if not effective_config_overlays_enabled():
        return None
    cached = load_effective_cache()
    if cached is None:
        return None
    hot_radar = cached.get("hot_radar")
    return hot_radar if isinstance(hot_radar, dict) else None


def ingestion_from_effective_cache() -> dict[str, Any] | None:
    if not effective_config_overlays_enabled():
        return None
    cached = load_effective_cache()
    if cached is None:
        return None
    ingestion = cached.get("ingestion")
    return ingestion if isinstance(ingestion, dict) else None


def content_methodology_from_effective_cache() -> dict[str, Any] | None:
    cached = load_effective_cache()
    if cached is None:
        return None
    methodology = cached.get("content_methodology")
    return methodology if isinstance(methodology, dict) else None
