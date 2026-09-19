#!/usr/bin/env python3
"""Seed industry_pack_releases from monorepo packs/."""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CLOUD_ROOT = Path(__file__).resolve().parents[1]
if str(CLOUD_ROOT) not in sys.path:
    sys.path.insert(0, str(CLOUD_ROOT))

from app.config import get_settings
from app.database import SessionLocal, get_engine, reset_engine_for_tests
from app.models import Base, IndustryPackRelease
from app.services.industry_catalog import load_taxonomy_yaml


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def seed() -> int:
    get_settings.cache_clear()
    reset_engine_for_tests()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    packs_root = get_settings().packs_root
    taxonomy = load_taxonomy_yaml()
    count = 0
    db = SessionLocal()
    try:
        for group in taxonomy.get("l1") or []:
            l1 = str(group.get("slug") or "").strip()
            for item in group.get("l2") or []:
                path = str(item.get("path") or "").strip()
                if "/" not in path:
                    continue
                l1_part, l2 = path.split("/", 1)
                pack_path = packs_root / l1_part / f"{l2}.yaml"
                if not pack_path.is_file():
                    print(f"skip missing pack: {pack_path}")
                    continue
                content = pack_path.read_text(encoding="utf-8")
                doc = yaml.safe_load(content) or {}
                industry = doc.get("industry") or {}
                defaults_path = packs_root / l1_part / "_defaults.yaml"
                defaults_yaml = (
                    defaults_path.read_text(encoding="utf-8")
                    if defaults_path.is_file()
                    else None
                )
                metadata = doc.get("metadata") or {}
                updated_raw = metadata.get("updated_at")
                updated_at = None
                if isinstance(updated_raw, str) and updated_raw.strip():
                    try:
                        updated_at = datetime.fromisoformat(
                            updated_raw.replace("Z", "+00:00")
                        )
                    except ValueError:
                        updated_at = datetime.now(timezone.utc)

                row = db.get(IndustryPackRelease, path)
                if row is None:
                    row = IndustryPackRelease(path=path)
                    db.add(row)
                row.pack_version = industry.get("pack_version")
                row.content_yaml = content
                row.content_hash = _sha256_file(pack_path)
                row.l1_defaults_yaml = defaults_yaml
                row.updated_at = updated_at or datetime.now(timezone.utc)
                count += 1
        db.commit()
    finally:
        db.close()
    print(f"Seeded {count} industry pack release(s) from {packs_root}")
    return count


if __name__ == "__main__":
    raise SystemExit(0 if seed() > 0 else 1)
