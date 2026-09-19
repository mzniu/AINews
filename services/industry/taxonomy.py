"""Bundled industry taxonomy helpers (M0 L2 registry)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from services.industry.config_loader import PACKS_ROOT, _load_yaml


def _taxonomy_path():
    return PACKS_ROOT / "taxonomy.yaml"


@lru_cache(maxsize=1)
def load_taxonomy() -> dict[str, Any]:
    return _load_yaml(_taxonomy_path())


def iter_l2_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for l1 in load_taxonomy().get("l1") or []:
        l1_slug = str(l1.get("slug") or "")
        l1_name = str(l1.get("display_name") or l1_slug)
        for l2 in l1.get("l2") or []:
            path = str(l2.get("path") or "")
            if not path:
                continue
            entries.append(
                {
                    "path": path,
                    "display_name": str(l2.get("display_name") or path),
                    "pack_version": l2.get("pack_version"),
                    "status": str(l2.get("status") or "active"),
                    "l1_slug": l1_slug,
                    "l1_display_name": l1_name,
                }
            )
    return entries


def find_l2(path: str) -> dict[str, Any] | None:
    normalized = path.strip()
    for entry in iter_l2_entries():
        if entry["path"] == normalized:
            return dict(entry)
    return None


def is_registered_l2(path: str) -> bool:
    return find_l2(path) is not None
