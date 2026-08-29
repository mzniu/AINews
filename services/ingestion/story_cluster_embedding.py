"""Lightweight text embeddings for story clustering (hashing or API)."""
from __future__ import annotations

import math
import re
from typing import Any

from src.db.models.ingestion import IngestedArticle

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")
_CACHE: dict[str, list[float]] = {}


def build_article_cluster_text(article: IngestedArticle, *, max_chars: int = 800) -> str:
    parts = [
        article.title or "",
        article.summary or "",
        (article.content_text or "")[:max_chars],
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    tokens = _TOKEN_RE.findall(text)
    bigrams: list[str] = []
    chars = re.sub(r"\s+", "", text)
    for index in range(max(0, len(chars) - 1)):
        bigrams.append(chars[index : index + 2])
    return tokens + bigrams


def hashing_embedding(text: str, *, dimensions: int = 256) -> list[float]:
    cached = _CACHE.get(text)
    if cached is not None:
        return cached
    vec = [0.0] * dimensions
    for token in _tokenize(text):
        bucket = hash(token) % dimensions
        vec[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    result = [value / norm for value in vec]
    _CACHE[text] = result
    return result


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def api_embedding_similarity(left_text: str, right_text: str, *, model: str) -> float | None:
    from services.ingestion.story_cluster_llm import build_language_client, resolve_language_model

    client = build_language_client()
    if client is None:
        return None
    try:
        response = client.embeddings.create(
            model=model,
            input=[left_text, right_text],
        )
        vectors = [row.embedding for row in response.data]
        if len(vectors) != 2:
            return None
        return cosine_similarity(vectors[0], vectors[1])
    except Exception:
        return None


def embedding_similarity(
    left: IngestedArticle,
    right: IngestedArticle,
    *,
    config: dict[str, Any] | None = None,
) -> float:
    from services.ingestion.story_cluster_config import load_story_cluster_config

    cfg = (config or load_story_cluster_config()).get("embedding") or {}
    if not cfg.get("enabled", True):
        return 0.0

    left_text = build_article_cluster_text(left)
    right_text = build_article_cluster_text(right)
    if not left_text or not right_text:
        return 0.0

    method = str(cfg.get("method", "hashing")).lower()
    if method == "api":
        api_score = api_embedding_similarity(
            left_text,
            right_text,
            model=str(cfg.get("embedding_model", "text-embedding-3-small")),
        )
        if api_score is not None:
            return max(0.0, min(1.0, api_score))

    dimensions = int(cfg.get("dimensions", 256))
    left_vec = hashing_embedding(left_text, dimensions=dimensions)
    right_vec = hashing_embedding(right_text, dimensions=dimensions)
    return max(0.0, min(1.0, cosine_similarity(left_vec, right_vec)))
