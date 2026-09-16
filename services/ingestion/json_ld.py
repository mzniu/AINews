"""Extract structured data from HTML pages."""
from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup


def _iter_json_ld_nodes(data: Any):
    if isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                yield from _iter_json_ld_nodes(node)
        yield data
    elif isinstance(data, list):
        for item in data:
            yield from _iter_json_ld_nodes(item)


def extract_news_article_ld(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
        if not cleaned.strip():
            continue
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            continue
        for node in _iter_json_ld_nodes(data):
            node_type = node.get("@type")
            if node_type == "NewsArticle" or (
                isinstance(node_type, list) and "NewsArticle" in node_type
            ):
                return node
    return None
