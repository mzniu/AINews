"""Helpers for platform post IDs."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_SYNTHETIC_RE = re.compile(r"^(xhs|wx|dy|ks)(_manual)?_\d+$", re.I)


def is_synthetic_platform_post_id(post_id: str | None) -> bool:
    if not post_id:
        return True
    return bool(_SYNTHETIC_RE.match(post_id.strip()))


def extract_xiaohongshu_note_id(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("noteId", "note_id", "id"):
        values = query.get(key)
        if values and values[0]:
            return values[0].strip()
    parts = [part for part in parsed.path.split("/") if part]
    if "explore" in parts:
        idx = parts.index("explore")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def build_xiaohongshu_post_url(note_id: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def extract_douyin_aweme_id(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("aweme_id", "item_id", "video_id", "modal_id"):
        values = query.get(key)
        if values and values[0]:
            return values[0].strip()
    match = re.search(r"/video/(\d+)", parsed.path)
    if match:
        return match.group(1)
    return None


def build_douyin_post_url(aweme_id: str) -> str:
    return f"https://www.douyin.com/video/{aweme_id}"


def extract_kuaishou_photo_id(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("photoId", "photo_id", "workId", "work_id"):
        values = query.get(key)
        if values and values[0]:
            return values[0].strip()
    match = re.search(r"/short-video/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    match = re.search(r"/photo/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    return None


def build_kuaishou_post_url(photo_id: str) -> str:
    return f"https://www.kuaishou.com/short-video/{photo_id}"


def extract_wechat_export_id(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("export_id", "exportId", "objectId", "object_id", "id"):
        values = query.get(key)
        if values and values[0]:
            return values[0].strip()
    return None


def build_wechat_post_url(export_id: str) -> str | None:
    del export_id
    return None


def build_platform_post_url(platform: str, post_id: str) -> str | None:
    builders = {
        "xiaohongshu": build_xiaohongshu_post_url,
        "douyin": build_douyin_post_url,
        "kuaishou": build_kuaishou_post_url,
        "wechat_channels": build_wechat_post_url,
    }
    builder = builders.get(platform)
    if builder is None:
        return None
    return builder(post_id)


def extract_platform_post_id(platform: str, url: str) -> str | None:
    extractors = {
        "xiaohongshu": extract_xiaohongshu_note_id,
        "douyin": extract_douyin_aweme_id,
        "kuaishou": extract_kuaishou_photo_id,
        "wechat_channels": extract_wechat_export_id,
    }
    extractor = extractors.get(platform)
    if extractor is None:
        return None
    return extractor(url)
