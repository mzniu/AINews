"""Parse per-article view / click counts from page text."""
from __future__ import annotations

import re

_CLICK_RE = re.compile(r"(\d[\d,]*)\s*点击")
_WAN_READ_RE = re.compile(r"([\d,.]+)\s*万\s*(?:阅读|浏览)")
_PLAIN_READ_RE = re.compile(r"(\d[\d,]*)\s*(?:阅读|浏览)")
_LABEL_READ_RE = re.compile(r"(?:阅读|浏览)[量数]?\s*[:：]?\s*([\d,.万]+)")


def _digits_to_int(raw: str) -> int:
    value = raw.strip().replace(",", "")
    if value.endswith("万"):
        return int(float(value[:-1]) * 10000)
    if "." in value:
        return int(float(value))
    return int(value)


def parse_view_count(text: str) -> int | None:
    """Return view/click count when present in HTML or plain text."""
    if not text:
        return None
    match = _CLICK_RE.search(text)
    if match:
        return _digits_to_int(match.group(1))
    match = _WAN_READ_RE.search(text)
    if match:
        return int(float(match.group(1).replace(",", "")) * 10000)
    match = _PLAIN_READ_RE.search(text)
    if match:
        return _digits_to_int(match.group(1))
    match = _LABEL_READ_RE.search(text)
    if match:
        return _digits_to_int(match.group(1))
    return None
