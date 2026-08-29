"""Enhanced URL/title matching for hot radar ↔ ingested articles."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from services.ingestion.story_cluster import normalize_title, title_similarity
from services.ingestion.url_utils import canonicalize_url

_ITHOME_HTML = re.compile(r"/html/(\d+)\.htm", re.I)
_ITHOME_SLASH = re.compile(r"/0/(\d+)/(\d+)\.htm", re.I)
_KR36_ID = re.compile(r"/p/(\d+)", re.I)
_QBITAI_ID = re.compile(r"/archives/(\d+)", re.I)
_LEIPHONE_ID = re.compile(r"/(?:archives|article)/(\d+)", re.I)


def normalize_netloc(netloc: str) -> str:
    host = (netloc or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    return host


def extract_url_keys(url: str) -> set[str]:
    if not url:
        return set()
    parsed = urlparse(canonicalize_url(url))
    host = normalize_netloc(parsed.netloc)
    path = parsed.path or ""
    keys: set[str] = set()
    keys.add(f"host:{host}|path:{path.rstrip('/')}")

    for pattern, prefix in (
        (_KR36_ID, "36kr"),
        (_QBITAI_ID, "qbitai"),
        (_LEIPHONE_ID, "leiphone"),
    ):
        match = pattern.search(path)
        if match:
            keys.add(f"{prefix}:{match.group(1)}")

    html_match = _ITHOME_HTML.search(path)
    if html_match:
        keys.add(f"ithome:{html_match.group(1)}")
    slash_match = _ITHOME_SLASH.search(path)
    if slash_match:
        keys.add(f"ithome:{slash_match.group(1)}{slash_match.group(2)}")

    tail = path.rsplit("/", 1)[-1]
    if tail:
        keys.add(f"tail:{tail}")
    return keys


def match_urls(article_url: str, hot_url: str) -> tuple[bool, str, float]:
    if not article_url or not hot_url:
        return False, "", 0.0

    left = canonicalize_url(article_url)
    right = canonicalize_url(hot_url)
    if left == right:
        return True, "url_exact", 1.0

    left_path = left.split("?", 1)[0]
    right_path = right.split("?", 1)[0]
    if left_path == right_path:
        return True, "url_path", 0.98

    left_keys = extract_url_keys(article_url)
    right_keys = extract_url_keys(hot_url)
    shared = left_keys & right_keys
    site_keys = {key for key in shared if not key.startswith("tail:") and not key.startswith("host:")}
    if site_keys:
        return True, "url_id", 0.96

    left_tail = left_path.rsplit("/", 1)[-1]
    right_tail = right_path.rsplit("/", 1)[-1]
    if left_tail and left_tail == right_tail:
        return True, "url_tail", 0.75

    left_host = normalize_netloc(urlparse(left).netloc)
    right_host = normalize_netloc(urlparse(right).netloc)
    if left_host == right_host and left_tail and right_tail and left_tail == right_tail:
        return True, "url_tail", 0.75

    return False, "", 0.0


def _entity_overlap_count(text_a: str, text_b: str, entity_names: list[str]) -> int:
    if not entity_names:
        return 0
    left = (text_a or "").lower()
    right = (text_b or "").lower()
    count = 0
    for name in entity_names:
        if not name:
            continue
        needle = name.lower()
        if needle in left and needle in right:
            count += 1
    return count


def score_title_pair(
    article_title: str,
    hot_title: str,
    *,
    entity_names: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[float, str]:
    cfg = config or {}
    entities = entity_names or []
    left = normalize_title(article_title)
    right = normalize_title(hot_title)
    if not left or not right:
        return 0.0, ""

    if left == right:
        return float(cfg.get("title_exact", 1.0)), "title_exact"

    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if shorter and shorter in longer and len(shorter) >= 8:
        return float(cfg.get("title_contains", 0.88)), "title_contains"

    similarity = title_similarity(article_title, hot_title)
    threshold = float(cfg.get("title_similarity_threshold", 0.72))
    overlap_min = int(cfg.get("entity_overlap_min", 2))
    overlap_boost = float(cfg.get("entity_overlap_boost", 0.12))
    overlap_floor = float(cfg.get("entity_overlap_floor", 0.65))
    overlap = _entity_overlap_count(article_title, hot_title, entities)
    min_overlap_similarity = float(cfg.get("entity_overlap_min_similarity", 0.35))
    if overlap >= overlap_min and similarity >= min_overlap_similarity:
        boosted = min(1.0, max(similarity, overlap_floor) + overlap_boost)
        if boosted >= threshold:
            return boosted, "entity_overlap"

    if similarity >= threshold:
        return similarity, "title_similarity"

    return similarity, ""


def text_embedding_similarity(left_text: str, right_text: str, *, config: dict[str, Any] | None = None) -> float:
    from services.ingestion.story_cluster_embedding import cosine_similarity, hashing_embedding

    cfg = (config or {}).get("embedding") or {}
    dimensions = int(cfg.get("dimensions", 256))
    if not left_text.strip() or not right_text.strip():
        return 0.0
    left_vec = hashing_embedding(left_text, dimensions=dimensions)
    right_vec = hashing_embedding(right_text, dimensions=dimensions)
    return max(0.0, min(1.0, cosine_similarity(left_vec, right_vec)))


def score_title_pair_with_embedding(
    article_title: str,
    hot_title: str,
    *,
    entity_names: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[float, str]:
    cfg = config or {}
    confidence, method = score_title_pair(article_title, hot_title, entity_names=entity_names, config=cfg)
    if method:
        return confidence, method

    gray_low = float(cfg.get("gray_zone_low", 0.55))
    gray_high = float(cfg.get("gray_zone_high", 0.72))
    similarity = title_similarity(article_title, hot_title)
    if not cfg.get("use_embedding_in_gray", True):
        return confidence, method
    if similarity < gray_low or similarity >= gray_high:
        return confidence, method

    embed_score = text_embedding_similarity(article_title, hot_title, config=cfg)
    embed_threshold = float(cfg.get("embedding_threshold", 0.78))
    if embed_score >= embed_threshold:
        return embed_score, "title_embedding"
    return confidence, method


def compute_time_factor(
    *,
    article_published_at,
    snapshot_fetched_at,
    config: dict[str, Any] | None = None,
) -> float:
    if article_published_at is None or snapshot_fetched_at is None:
        return 1.0
    cfg = config or {}
    hours = abs((snapshot_fetched_at - article_published_at).total_seconds()) / 3600.0
    window = float(cfg.get("time_window_hours", 48))
    if hours <= window:
        return 1.0
    decay = float(cfg.get("time_decay_per_day", 0.15))
    extra_days = (hours - window) / 24.0
    return max(float(cfg.get("time_factor_floor", 0.6)), 1.0 - decay * extra_days)


def compute_final_confidence(
    base_confidence: float,
    *,
    board_weight: float = 1.0,
    time_factor: float = 1.0,
) -> float:
    return max(0.0, min(1.0, base_confidence * board_weight * time_factor))


def compute_effective_rank(rank: int, confidence: float, *, config: dict[str, Any] | None = None) -> int:
    cfg = config or {}
    min_conf = float(cfg.get("min_confidence", 0.6))
    if confidence < min_conf:
        return rank + int(cfg.get("low_confidence_rank_penalty", 20))
    if confidence < float(cfg.get("medium_confidence", 0.8)):
        return rank + int(cfg.get("medium_confidence_rank_penalty", 5))
    return rank
