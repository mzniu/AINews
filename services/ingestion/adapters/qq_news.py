"""腾讯新闻频道 adapter（API 列表 + rain 详情页 window.DATA）。"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any, List
from urllib.parse import parse_qsl, urlparse

from services.ingestion.http_client import get_text, post_json

from bs4 import BeautifulSoup

from services.ingestion.adapters.base import ArticleDetail, ArticleRef
from services.ingestion.url_utils import canonicalize_url
from src.utils.config import Config

_LIST_API = "https://i.news.qq.com/web_feed/getPCList"
_DATA_MARKER = "window.DATA"
_VIDEO_ID_RE = re.compile(r"^\d{8}V", re.I)
_IMG_ATTR_KEY_RE = re.compile(r"^IMG_\d+$")
_NOISE_IMAGE_MARKERS = (
    "_200200/0",
    "_181x181s",
    "newsapp_ls/0/",
    "newsapp_bt/",
)
_MIN_DETAIL_CHARS = 80


def extract_window_data(html: str) -> dict[str, Any] | None:
    """Parse `window.DATA = {...}` with brace matching so nested `};` in strings survive."""
    marker_at = html.find(_DATA_MARKER)
    if marker_at < 0:
        return None
    eq_at = html.find("=", marker_at + len(_DATA_MARKER))
    if eq_at < 0:
        return None
    start = html.find("{", eq_at)
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    quote = ""
    for index, char in enumerate(html[start:], start):
        if in_str:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                in_str = False
            continue
        if char in ('"', "'"):
            in_str = True
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : index + 1])
                except json.JSONDecodeError:
                    return None
    return None


class QqNewsAdapter:
    adapter_id = "qq_news"

    def __init__(
        self,
        source_id: str,
        base_url: str,
        channel_id: str | None = None,
        list_referer: str | None = None,
        **_: object,
    ) -> None:
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")
        self.channel_id = channel_id or "news_news_fx"
        self.list_referer = list_referer or f"{self.base_url}/ch/fx"

    def _headers(self, *, referer: str | None = None) -> dict[str, str]:
        origin = "https://news.qq.com"
        parsed = urlparse(self.base_url)
        if parsed.scheme and parsed.netloc:
            origin = f"{parsed.scheme}://{parsed.netloc}"
        return {
            "User-Agent": Config.USER_AGENT,
            "Referer": referer or self.list_referer,
            "Origin": origin,
            "Accept": "application/json, text/plain, */*",
        }

    def fetch_html(self, url: str) -> str:
        return get_text(url, headers=self._headers(referer=self.list_referer))

    def discover_list(self, list_url: str) -> List[ArticleRef]:
        page = self._page_from_list_url(list_url)
        payload = self.fetch_list_payload(page)
        return self.parse_list_payload(payload)

    def fetch_list_payload(self, page: int = 0) -> dict[str, Any]:
        forward = "2" if page <= 0 else "1"
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = post_json(
                    _LIST_API,
                    json={
                        "base_req": {"from": "pc"},
                        "forward": forward,
                        "channel_id": self.channel_id,
                        "page": max(0, page),
                    },
                    headers={**self._headers(), "Content-Type": "application/json"},
                )
                payload = response.json()
            except Exception as exc:
                last_error = exc
            else:
                if payload.get("code") == 0 and isinstance(payload.get("data"), list):
                    return payload
                message = payload.get("message") or "unknown error"
                last_error = RuntimeError(f"腾讯新闻列表 API 失败: {message}")
            if attempt < 2:
                time.sleep(0.8 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def parse_list_payload(self, payload: dict[str, Any]) -> List[ArticleRef]:
        items: List[ArticleRef] = []
        seen: set[str] = set()

        for block in payload.get("data") or []:
            candidates = block.get("sub_item") or [block]
            for raw in candidates:
                article_id = str(raw.get("id") or "").strip()
                title = str(raw.get("title") or "").strip()
                if not article_id or not title:
                    continue
                if self._is_video_item(raw, article_id):
                    continue
                url = canonicalize_url(self._article_url(article_id))
                if url in seen:
                    continue
                seen.add(url)

                link_info = raw.get("link_info") or {}
                if link_info.get("url"):
                    url = canonicalize_url(str(link_info["url"]))

                summary = str(raw.get("intro") or raw.get("desc") or "").strip() or None
                cover = self._pick_cover(raw.get("pic_info") or {})
                media = raw.get("media_info") or {}
                author = str(media.get("chl_name") or "").strip() or None
                published_at = self._parse_publish_time(raw.get("publish_time"))

                items.append(
                    ArticleRef(
                        url=url,
                        title=title,
                        summary=summary,
                        published_at=published_at,
                        theme="财经",
                        keywords=["财经", "腾讯新闻"],
                        cover_image_url=cover,
                        extra={
                            "article_id": article_id,
                            "author": author,
                            "articletype": raw.get("articletype"),
                        },
                    )
                )
        return items

    def fetch_detail(self, ref: ArticleRef) -> ArticleDetail:
        detail_url = ref.url
        article_id = (ref.extra or {}).get("article_id")
        rain_url = self._article_url(str(article_id)) if article_id else None
        if rain_url:
            detail_url = rain_url
        html = self.fetch_html(detail_url)
        detail = self.parse_detail_html(html, url=detail_url)
        if self._detail_too_thin(detail) and ref.url and canonicalize_url(ref.url) != canonicalize_url(detail_url):
            html = self.fetch_html(ref.url)
            fallback = self.parse_detail_html(html, url=ref.url)
            if not self._detail_too_thin(fallback):
                detail = fallback
        if not detail.summary and ref.summary:
            detail.summary = ref.summary
        if not detail.theme and ref.theme:
            detail.theme = ref.theme
        if not detail.keywords and ref.keywords:
            detail.keywords = list(ref.keywords)
        if not detail.cover_image_url and ref.cover_image_url:
            detail.cover_image_url = ref.cover_image_url
        if not detail.published_at and ref.published_at:
            detail.published_at = ref.published_at
        if not detail.author and (ref.extra or {}).get("author"):
            detail.author = str(ref.extra["author"])
        return detail

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        data = self._extract_window_data(html)
        if data:
            return self._detail_from_window_data(data, url=url, html=html)

        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1") or soup.select_one("title")
        title = title_el.get_text(strip=True) if title_el else ""
        content_el = soup.select_one("#article-content, .content-article, .LEFT")
        content_html = str(content_el) if content_el else ""
        content_text = content_el.get_text("\n", strip=True) if content_el else ""
        images = self._images_from_dom(soup)
        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=content_text,
            content_html=content_html,
            summary=None,
            author=None,
            published_at=None,
            theme="财经",
            keywords=["财经", "腾讯新闻"],
            images=images,
            cover_image_url=images[0] if images else None,
        )

    def _detail_from_window_data(
        self, data: dict[str, Any], *, url: str, html: str
    ) -> ArticleDetail:
        title = str(data.get("title") or "").strip()
        summary = (
            str(data.get("abstract") or data.get("desc") or data.get("introduction") or "")
            .strip()
            or None
        )
        author = str(data.get("media") or "").strip() or None
        published_at = self._parse_publish_time(data.get("pubtime"))

        origin = data.get("originContent") or {}
        content_html = str(origin.get("text") or "").strip()
        soup = BeautifulSoup(content_html, "lxml") if content_html else None
        content_text = soup.get_text("\n", strip=True) if soup else ""

        image_candidates: list[str] = []
        if soup:
            image_candidates.extend(self._images_from_soup(soup))
        image_candidates.extend(self._images_from_origin_attribute(data))
        image_candidates.extend(self._images_from_dom(BeautifulSoup(html, "lxml")))
        images = self._dedupe_images(image_candidates)

        cover = images[0] if images else self._pick_cover(data.get("pic_info") or {})

        if not content_text:
            soup_page = BeautifulSoup(html, "lxml")
            content_el = soup_page.select_one("#article-content, .content-article")
            if content_el:
                content_html = str(content_el)
                content_text = content_el.get_text("\n", strip=True)

        keywords = ["财经", "腾讯新闻"]
        for tag in (data.get("tags") or [])[:8]:
            text = str(tag).strip()
            if text and text not in keywords:
                keywords.append(text)

        return ArticleDetail(
            url=canonicalize_url(str(data.get("url") or url)),
            title=title,
            content_text=content_text,
            content_html=content_html or None,
            summary=summary,
            author=author,
            published_at=published_at,
            theme="财经",
            keywords=keywords,
            images=images,
            cover_image_url=cover,
        )

    def _images_from_origin_attribute(self, data: dict[str, Any]) -> list[str]:
        attr = data.get("originAttribute") or {}
        if not isinstance(attr, dict):
            return []
        keys = [key for key in attr if _IMG_ATTR_KEY_RE.match(str(key))]
        keys.sort(key=lambda key: int(str(key).split("_")[1]))
        images: list[str] = []
        for key in keys:
            item = attr.get(key)
            if not isinstance(item, dict):
                continue
            url = (
                item.get("bigOrigUrl")
                or item.get("origUrl")
                or item.get("imgurl1000")
                or item.get("imgurl0")
                or item.get("url")
            )
            if url:
                images.append(self._abs_url(str(url)))
        return images

    def _images_from_soup(self, soup: BeautifulSoup) -> list[str]:
        images: list[str] = []
        for img in soup.select("img[src], img[data-original], img[data-src], img[data-lazy-src]"):
            src = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
                or img.get("src")
                or ""
            ).strip()
            if src and not src.startswith("data:"):
                images.append(self._abs_url(src))
        return images

    def _images_from_dom(self, soup: BeautifulSoup) -> list[str]:
        content_el = soup.select_one("#article-content, .content-article")
        if not content_el:
            return []
        for noisy in content_el.select("#article-author, .article-author, .author-avatar"):
            noisy.decompose()
        return self._images_from_soup(content_el)

    def _dedupe_images(self, urls: list[str]) -> list[str]:
        seen: set[str] = set()
        images: list[str] = []
        for raw in urls:
            url = self._abs_url(raw)
            if not url or self._is_noise_image(url):
                continue
            key = self._image_dedupe_key(url)
            if key in seen:
                continue
            seen.add(key)
            images.append(url)
        return images

    def _image_dedupe_key(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path
        if "/om_bt/" in path or "/news_ls/" in path or "/om_ls/" in path:
            return f"{parsed.netloc}{path.rsplit('/', 1)[0]}"
        return f"{parsed.netloc}{path}"

    def _is_noise_image(self, url: str) -> bool:
        lower = url.lower()
        return any(marker in lower for marker in _NOISE_IMAGE_MARKERS)

    def _extract_window_data(self, html: str) -> dict[str, Any] | None:
        return extract_window_data(html)

    def _detail_too_thin(self, detail: ArticleDetail) -> bool:
        return len((detail.content_text or "").strip()) < _MIN_DETAIL_CHARS

    def _page_from_list_url(self, list_url: str) -> int:
        parsed = urlparse(list_url)
        pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        raw = pairs.get("page", "0")
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0

    def _article_url(self, article_id: str) -> str:
        return f"{self.base_url}/rain/a/{article_id}"

    def _abs_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("http"):
            return href
        return f"{self.base_url}/{href.lstrip('/')}"

    def _is_video_item(self, raw: dict[str, Any], article_id: str) -> bool:
        article_type = str(raw.get("articletype") or raw.get("article_type") or "")
        if article_type in {"56", "102", "103"}:
            return True
        return bool(_VIDEO_ID_RE.match(article_id))

    def _pick_cover(self, pic_info: dict[str, Any]) -> str | None:
        for key in ("big_img", "small_img", "share_img", "three_img"):
            values = pic_info.get(key)
            if isinstance(values, list) and values:
                return self._abs_url(str(values[0]))
            if isinstance(values, str) and values:
                return self._abs_url(values)
        ext = pic_info.get("ext") or {}
        for value in ext.values():
            if value:
                return self._abs_url(str(value))
        return None

    def _parse_publish_time(self, raw: Any) -> datetime | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
