"""Source adapter base types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ArticleRef:
    url: str
    title: str
    summary: str | None = None
    published_at: datetime | None = None
    theme: str | None = None
    keywords: list[str] = field(default_factory=list)
    cover_image_url: str | None = None
    view_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArticleDetail:
    url: str
    title: str
    content_text: str
    content_html: str | None = None
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    theme: str | None = None
    keywords: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    cover_image_url: str | None = None
    view_count: int | None = None
