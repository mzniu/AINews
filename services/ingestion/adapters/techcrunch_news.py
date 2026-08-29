"""TechCrunch AI channel adapter (WordPress REST list + HTML fallback)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List
from urllib.parse import parse_qsl, urljoin, urlparse

from bs4 import BeautifulSoup

from services.ingestion.adapters.base import ArticleDetail, ArticleRef
from services.ingestion.http_client import get_text
from services.ingestion.url_utils import canonicalize_url
from src.utils.beijing_time import BEIJING_TZ
from src.utils.config import Config

AI_CATEGORY_ID = 577047203
_POST_FIELDS = (
    "id,date,date_gmt,link,slug,title,excerpt,content,"
    "jetpack_featured_media_url,yoast_head_json,categories"
)
_SKIP_IMAGE = (
    "data:",
    "gravatar",
    "1x1",
    "pixel",
    "emoji",
    "jwplayer",
    "scorecardresearch",
    ".svg",
)


class TechcrunchNewsAdapter:
    adapter_id = "techcrunch_news"

    def __init__(
        self,
        source_id: str,
        base_url: str,
        category_id: int | str | None = None,
        list_referer: str | None = None,
        **_: object,
    ) -> None:
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")
        try:
            self.category_id = int(category_id) if category_id else AI_CATEGORY_ID
        except (TypeError, ValueError):
            self.category_id = AI_CATEGORY_ID
        self.list_referer = list_referer or f"{self.base_url}/category/artificial-intelligence/"

    def _headers(self, *, accept: str = "text/html") -> dict[str, str]:
        return {
            "User-Agent": Config.USER_AGENT,
            "Referer": self.list_referer,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        }

    def fetch_html(self, url: str) -> str:
        return get_text(url, headers=self._headers())

    def discover_list(self, list_url: str) -> List[ArticleRef]:
        page = self._page_from_list_url(list_url)
        payload = self.fetch_list_payload(page)
        return self.parse_list_payload(payload)

    def fetch_list_payload(self, page: int = 1) -> list[dict[str, Any]]:
        url = (
            f"{self.base_url}/wp-json/wp/v2/posts"
            f"?categories={self.category_id}&per_page=20"
            f"&page={max(1, page)}&_fields={_POST_FIELDS}"
        )
        raw = get_text(url, headers=self._headers(accept="application/json"))
        payload = json.loads(raw)
        if isinstance(payload, dict):
            raise RuntimeError(payload.get("message") or "TechCrunch 列表 API 失败")
        if not isinstance(payload, list):
            raise RuntimeError("TechCrunch 列表 API 返回异常")
        return payload

    def parse_list_payload(self, payload: list[dict[str, Any]] | dict[str, Any]) -> List[ArticleRef]:
        rows = payload if isinstance(payload, list) else payload.get("posts") or payload.get("data") or []
        items: List[ArticleRef] = []
        seen: set[str] = set()
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            url = canonicalize_url(str(raw.get("link") or "").strip())
            title = _wp_text((raw.get("title") or {}).get("rendered") if isinstance(raw.get("title"), dict) else raw.get("title"))
            if not url.startswith("http") or len(title) < 8:
                continue
            if url in seen:
                continue
            seen.add(url)
            content_html = ""
            content = raw.get("content")
            if isinstance(content, dict):
                content_html = str(content.get("rendered") or "")
            excerpt = raw.get("excerpt")
            summary = _wp_text(excerpt.get("rendered") if isinstance(excerpt, dict) else excerpt)
            cover = str(raw.get("jetpack_featured_media_url") or "").strip() or None
            author = _author_from_post(raw)
            post_id = raw.get("id")
            items.append(
                ArticleRef(
                    url=url,
                    title=title,
                    summary=summary or None,
                    published_at=_parse_gmt(raw.get("date_gmt") or raw.get("date")),
                    theme="AI",
                    keywords=["AI", "TechCrunch"],
                    cover_image_url=cover,
                    extra={
                        "post_id": post_id,
                        "slug": raw.get("slug"),
                        "author": author,
                        "content_html": content_html,
                    },
                )
            )
        return items

    def fetch_detail(self, ref: ArticleRef) -> ArticleDetail:
        extra = ref.extra or {}
        content_html = str(extra.get("content_html") or "")
        if content_html.strip():
            detail = self._detail_from_fields(
                url=ref.url,
                title=ref.title,
                content_html=content_html,
                summary=ref.summary,
                author=str(extra.get("author") or "") or None,
                published_at=ref.published_at,
                cover=ref.cover_image_url,
            )
        else:
            detail = self.parse_detail_html(self.fetch_html(ref.url), url=ref.url)
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
        if not detail.author and extra.get("author"):
            detail.author = str(extra["author"])
        return detail

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1.article-hero__title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""
        author_el = soup.select_one(".article-hero__authors")
        author = author_el.get_text(" ", strip=True) if author_el else None
        content_el = soup.select_one("div.entry-content") or soup.select_one(".wp-block-post-content")
        content_html = str(content_el) if content_el else ""
        published_at = None
        time_el = soup.select_one("time[datetime]")
        if time_el and time_el.get("datetime"):
            published_at = _parse_gmt(str(time_el["datetime"]).replace("+00:00", ""))
        return self._detail_from_fields(
            url=url,
            title=title,
            content_html=content_html,
            summary=None,
            author=author,
            published_at=published_at,
            cover=None,
        )

    def _detail_from_fields(
        self,
        *,
        url: str,
        title: str,
        content_html: str,
        summary: str | None,
        author: str | None,
        published_at: datetime | None,
        cover: str | None,
    ) -> ArticleDetail:
        images = _images_from_html(content_html, self.base_url)
        if cover and cover not in images:
            images.insert(0, cover)
        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=_wp_text(content_html),
            content_html=content_html or None,
            summary=summary,
            author=author,
            published_at=published_at,
            theme="AI",
            keywords=["AI", "TechCrunch"],
            images=images,
            cover_image_url=cover or (images[0] if images else None),
        )

    def _page_from_list_url(self, list_url: str) -> int:
        parsed = urlparse(list_url)
        pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        raw = pairs.get("page", "1")
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 1


def _wp_text(html: str | None) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup.select("script, style, noscript, .jw-player-inline-promo"):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _author_from_post(raw: dict[str, Any]) -> str | None:
    if raw.get("author_name"):
        return str(raw["author_name"]).strip() or None
    yoast = raw.get("yoast_head_json")
    if isinstance(yoast, dict) and yoast.get("author"):
        return str(yoast["author"]).strip() or None
    return None


def _parse_gmt(raw: str | None) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = text.replace("Z", "")
    if "T" not in text:
        return None
    stamp = text[:19]
    try:
        moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return moment.astimezone(BEIJING_TZ).replace(tzinfo=None)


def _images_from_html(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html or "", "lxml")
    images: list[str] = []
    seen: set[str] = set()
    for img in soup.select("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        if any(marker in src.lower() for marker in _SKIP_IMAGE):
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = urljoin(base_url + "/", src)
        if src in seen:
            continue
        seen.add(src)
        images.append(src)
    return images
