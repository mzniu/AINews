"""URL helpers for ingestion."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

STRIP_QUERY_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "from"}


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "http").lower()
    netloc = parsed.netloc.lower()
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in STRIP_QUERY_KEYS
    ]
    query = urlencode(query_pairs)
    return urlunparse((scheme, netloc, parsed.path, "", query, ""))


def build_list_page_url(source_config: dict, page: int) -> str:
    pagination = source_config.get("list_pagination") or {}
    if pagination.get("type") == "query_index":
        param = pagination.get("param", "index")
        start = int(pagination.get("start", 1))
        list_url = source_config["list_url"]
        parsed = urlparse(list_url)
        pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        pairs[param] = str(start + page - 1)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(pairs), "")
        )
    if pagination.get("type") == "query_paged":
        param = pagination.get("param", "paged")
        start = int(pagination.get("start", 1))
        list_url = source_config["list_url"]
        parsed = urlparse(list_url)
        pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        pairs[param] = str(start + page - 1)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path or "/", "", urlencode(pairs), "")
        )
    return source_config["list_url"]
