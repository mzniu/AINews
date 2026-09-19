from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.industry import IndustryPackRelease

_INDUSTRY_ID_RE = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+$")


def is_valid_industry_id(value: str) -> bool:
    return bool(_INDUSTRY_ID_RE.match(value.strip()))


def load_taxonomy_yaml() -> dict[str, Any]:
    path = get_settings().packs_root / "taxonomy.yaml"
    if not path.is_file():
        return {"schema_version": 1, "l1": []}
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {"schema_version": 1, "l1": []}


def list_known_l2_paths() -> set[str]:
    paths: set[str] = set()
    data = load_taxonomy_yaml()
    for group in data.get("l1") or []:
        for item in group.get("l2") or []:
            path = str(item.get("path") or "").strip()
            if path:
                paths.add(path)
    return paths


def manifest_from_db(db: Session, industry_path: str) -> dict[str, Any] | None:
    row = db.get(IndustryPackRelease, industry_path)
    if row is None:
        return None
    l1, _ = industry_path.split("/", 1)
    return {
        "path": industry_path,
        "pack_version": row.pack_version,
        "content_yaml": row.content_yaml,
        "content_hash": row.content_hash,
        "l1_defaults_key": f"packs/{l1}/_defaults.yaml",
        "l1_defaults_yaml": row.l1_defaults_yaml,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def manifest_from_files(industry_path: str) -> dict[str, Any] | None:
    if not is_valid_industry_id(industry_path):
        return None
    root = get_settings().packs_root
    l1, l2 = industry_path.split("/", 1)
    pack_path = root / l1 / f"{l2}.yaml"
    if not pack_path.is_file():
        return None
    content = pack_path.read_text(encoding="utf-8")
    doc = yaml.safe_load(content) or {}
    industry = doc.get("industry") or {}
    defaults_path = root / l1 / "_defaults.yaml"
    l1_defaults_yaml = (
        defaults_path.read_text(encoding="utf-8") if defaults_path.is_file() else None
    )
    digest = hashlib.sha256(pack_path.read_bytes()).hexdigest()
    metadata = doc.get("metadata") or {}
    return {
        "path": industry_path,
        "pack_version": industry.get("pack_version"),
        "content_yaml": content,
        "content_hash": f"sha256:{digest}",
        "l1_defaults_key": f"packs/{l1}/_defaults.yaml",
        "l1_defaults_yaml": l1_defaults_yaml,
        "updated_at": metadata.get("updated_at"),
    }


def get_pack_manifest(db: Session, industry_path: str) -> dict[str, Any] | None:
    normalized = industry_path.strip().strip("/")
    if not is_valid_industry_id(normalized):
        return None
    return manifest_from_db(db, normalized) or manifest_from_files(normalized)
