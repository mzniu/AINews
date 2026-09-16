"""Deduplicate scored images by URL, path, and vision content description."""
from __future__ import annotations

import re
from typing import Any

from services.ingestion.image_scorer import load_image_scoring_config


def normalize_image_url(url: str | None) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    return raw.split("?", 1)[0].rstrip("/").lower()


def normalize_image_local_path(path: str | None) -> str:
    raw = str(path or "").strip().replace("\\", "/")
    if raw.startswith("/"):
        raw = raw[1:]
    return raw.lower()


def normalize_content_description(text: str | None) -> str:
    raw = str(text or "").strip().lower()
    if not raw:
        return ""
    raw = re.sub(r"[\s\u3000]+", "", raw)
    raw = re.sub(r"[^\w\u4e00-\u9fff]+", "", raw)
    return raw


def resolve_content_description(item: dict[str, Any]) -> str:
    for key in ("content_description", "caption"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    evaluation = item.get("evaluation")
    if isinstance(evaluation, dict):
        for key in ("content_description", "caption"):
            value = str(evaluation.get(key) or "").strip()
            if value:
                return value
    return ""


def descriptions_similar(
    left: str,
    right: str,
    *,
    threshold: float = 0.82,
) -> bool:
    normalized_left = normalize_content_description(left)
    normalized_right = normalize_content_description(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    shorter, longer = sorted((normalized_left, normalized_right), key=len)
    if len(shorter) >= 8 and shorter in longer:
        return True

    def _bigrams(value: str) -> set[str]:
        if len(value) < 2:
            return {value} if value else set()
        return {value[index : index + 2] for index in range(len(value) - 1)}

    left_bigrams = _bigrams(normalized_left)
    right_bigrams = _bigrams(normalized_right)
    if not left_bigrams or not right_bigrams:
        return False
    overlap = len(left_bigrams & right_bigrams)
    union = len(left_bigrams | right_bigrams)
    return (overlap / union) >= threshold


def image_dedupe_keys(item: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    url = normalize_image_url(item.get("url"))
    if url:
        keys.append(f"url:{url}")
    local_path = normalize_image_local_path(item.get("local_path"))
    if local_path:
        keys.append(f"path:{local_path}")
    content = normalize_content_description(resolve_content_description(item))
    if len(content) >= 8:
        keys.append(f"desc:{content}")
    return keys


def image_entry_rank_key(item: dict[str, Any]) -> tuple:
    rank = item.get("relevance_rank")
    score = item.get("relevance_score")
    return (
        0 if rank is not None else 1,
        rank if rank is not None else 9999,
        -(score if score is not None else -1),
    )


def dedupe_image_entries(
    images: list[dict[str, Any]],
    *,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Drop duplicate images, keeping the best relevance-ranked entry."""
    cfg = config or load_image_scoring_config()
    dedupe_cfg = cfg.get("dedupe") or {}
    by_content = bool(dedupe_cfg.get("by_content_description", True))
    threshold = float(dedupe_cfg.get("similarity_threshold", 0.82))

    kept: list[dict[str, Any]] = []
    key_sets: list[set[str]] = []

    for item in images:
        keys = set(image_dedupe_keys(item))
        description = resolve_content_description(item)
        match_idx = None
        for idx, existing_keys in enumerate(key_sets):
            if keys and (keys & existing_keys):
                match_idx = idx
                break
            if by_content and description:
                existing_desc = resolve_content_description(kept[idx])
                if existing_desc and descriptions_similar(
                    description,
                    existing_desc,
                    threshold=threshold,
                ):
                    match_idx = idx
                    break
        if match_idx is None:
            kept.append(item)
            key_sets.append(set(keys))
            continue
        key_sets[match_idx].update(keys)
        if image_entry_rank_key(item) < image_entry_rank_key(kept[match_idx]):
            kept[match_idx] = item
    return kept
