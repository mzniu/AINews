"""Download article images to data/ingested/."""
from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from src.utils.config import Config
from utils.image_format import resolve_image_ext

INGESTED_ROOT = Path("data/ingested")

WECHAT_MP_REFERER = "https://mp.weixin.qq.com/"
WECHAT_CDN_HOSTS = ("mmbiz.qpic.cn", "mmecoa.qpic.cn", "wx.qlogo.cn")


def is_wechat_cdn_url(image_url: str) -> bool:
    host = (urlparse(image_url).netloc or "").lower()
    return any(token in host for token in WECHAT_CDN_HOSTS) or "mmbiz" in image_url.lower()


def is_wechat_hotlink_placeholder(content: bytes) -> bool:
    """Detect WeChat anti-hotlink placeholder ('此图片来自微信公众平台')."""
    if not content:
        return True
    if b"\xe6\xad\xa4\xe5\x9b\xbe" in content or b"\xe6\x9c\xaa\xe7\xbb\x8f\xe8\xae\xb8\xe5\x8f\xaf" in content:
        return True
    if len(content) < 2048:
        return True
    if len(content) > 80_000:
        return False
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(content))
        width, height = img.size
        if width <= 900 and height <= 280 and len(content) < 35_000:
            return True
    except Exception:
        pass
    return False


def _wechat_image_url_variants(image_url: str) -> list[str]:
    if not is_wechat_cdn_url(image_url):
        return [image_url]
    base = image_url.split("?", 1)[0]
    variants = [
        image_url,
        f"{base}?wx_fmt=jpeg&from=appmsg",
        f"{base}?wx_fmt=png&from=appmsg",
        f"{base}?wx_fmt=webp&from=appmsg",
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for item in variants:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _referer_candidates(image_url: str, referer: str | None) -> list[str | None]:
    candidates: list[str | None] = []
    if is_wechat_cdn_url(image_url):
        if referer and "mp.weixin.qq.com" in referer:
            candidates.append(referer)
        candidates.extend([WECHAT_MP_REFERER, "https://mp.weixin.qq.com", "http://mp.weixin.qq.com/"])
    if referer:
        candidates.append(referer)
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            candidates.append(f"{parsed.scheme}://{parsed.netloc}/")
    candidates.append(None)
    seen: set[str | None] = set()
    ordered: list[str | None] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _build_image_headers(referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": Config.USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
    return headers


def _fetch_image_bytes(
    http: requests.Session,
    image_url: str,
    *,
    headers: dict[str, str],
    max_bytes: int,
) -> tuple[bytes | None, str | None, str]:
    response = http.get(
        image_url,
        timeout=Config.CRAWLER_TIMEOUT,
        headers=headers,
        stream=True,
    )
    response.raise_for_status()
    content = b""
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        content += chunk
        if len(content) > max_bytes:
            return None, None, "image_too_large"
    if not content:
        return None, None, "empty_response"
    content_type = response.headers.get("content-type")
    return content, content_type, ""


def download_image(
    image_url: str,
    dest_dir: Path,
    *,
    index: int,
    max_bytes: int = 10 * 1024 * 1024,
    session: Optional[requests.Session] = None,
    referer: str | None = None,
    max_retries: int = 3,
    retry_delay_sec: float = 2.0,
) -> dict:
    dest_dir.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()
    last_error = "unknown"
    url_variants = _wechat_image_url_variants(image_url)
    referer_variants = _referer_candidates(image_url, referer)

    for url in url_variants:
        for ref in referer_variants:
            headers = _build_image_headers(ref)
            for attempt in range(max_retries):
                try:
                    content, content_type, err = _fetch_image_bytes(
                        http,
                        url,
                        headers=headers,
                        max_bytes=max_bytes,
                    )
                    if err:
                        last_error = err
                        if err == "image_too_large":
                            return {"success": False, "error": err, "original_url": image_url}
                        continue
                    assert content is not None
                    if is_wechat_cdn_url(url) and is_wechat_hotlink_placeholder(content):
                        last_error = "wechat_hotlink_placeholder"
                        break
                    ext = resolve_image_ext(
                        content,
                        content_type=content_type,
                        url=url,
                    )
                    filename = f"img_{index:03d}{ext}"
                    path = dest_dir / filename
                    path.write_bytes(content)
                    sha = hashlib.sha256(content).hexdigest()
                    return {
                        "success": True,
                        "local_path": path.as_posix(),
                        "original_url": image_url,
                        "sha256": sha,
                        "download_url": url,
                        "referer_used": ref,
                    }
                except Exception as exc:
                    last_error = str(exc)
                    retryable = any(
                        token in last_error.lower()
                        for token in (
                            "timeout",
                            "connection",
                            "reset",
                            "broken",
                            "temporarily",
                            "403",
                            "429",
                        )
                    )
                    if retryable and attempt < max_retries - 1:
                        time.sleep(retry_delay_sec)
                        continue
                    break

    return {"success": False, "error": last_error, "original_url": image_url}
