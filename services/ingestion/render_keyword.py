"""Pick a single on-card keyword for chronicle-frame templates."""
from __future__ import annotations

import re
from typing import Any, Iterable

MAX_KEYWORD_CHARS = 8
DEFAULT_FALLBACK = "快讯"

SKIP_KEYWORDS = frozenset(
    {
        "小牛说",
        "小牛说AI",
        "小牛聊AI",
        "人工智能",
        "AI资讯",
        "AI应用",
        "AI前沿",
        "科技前沿",
        "行业观察",
        "技术趋势",
        "AI",
    }
)


def _normalize_token(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.lstrip("#").strip()
    return text


def _iter_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        parts: list[str] = []
        for item in tags:
            parts.extend(_iter_tags(item))
        return parts
    text = str(tags).replace("，", " ").replace(",", " ")
    found = re.findall(r"#[^\s]+", text)
    tokens = found or re.split(r"\s+", text.strip())
    return [_normalize_token(tok) for tok in tokens if _normalize_token(tok)]


def _usable(token: str) -> bool:
    return bool(token) and token not in SKIP_KEYWORDS and token.upper() not in SKIP_KEYWORDS


def _clip(token: str) -> str:
    return token[:MAX_KEYWORD_CHARS]


def pick_card_keyword(
    *,
    tags: Any = None,
    keywords: Iterable[Any] | None = None,
    highlight_keywords: Iterable[Any] | None = None,
    theme: str | None = None,
    fallback: str = DEFAULT_FALLBACK,
) -> str:
    for token in _iter_tags(tags):
        if _usable(token):
            return _clip(token)
    for token in keywords or []:
        normalized = _normalize_token(token)
        if _usable(normalized):
            return _clip(normalized)
    for token in highlight_keywords or []:
        normalized = _normalize_token(token)
        if _usable(normalized):
            return _clip(normalized)
    theme_token = _normalize_token(theme)
    if _usable(theme_token):
        return _clip(theme_token)
    return _clip(_normalize_token(fallback) or DEFAULT_FALLBACK)
