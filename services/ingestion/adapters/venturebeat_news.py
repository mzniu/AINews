"""VentureBeat AI channel adapter (RSS list + HTML fallback)."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from services.ingestion.adapters.base import ArticleDetail, ArticleRef
from services.ingestion.http_client import get_text
from services.ingestion.url_utils import canonicalize_url
from src.utils.beijing_time import BEIJING_TZ
from src.utils.config import Config

_AUTHOR_IN_PARENS = re.compile(r"\(([^)]+)\)")
_SKIP_IMAGE = (
    "data:",
    "gravatar",
    "1x1",
    "pixel",
    "emoji",
    ".svg",
    "scorecardresearch",
)


class VenturebeatNewsAdapter:
    adapter_id = "venturebeat_news"

    def __init__(
        self,
        source_id: str,
        base_url: str,
        list_referer: str | None = None,
        **_: object,
    ) -> None:
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")
        self.list_referer = list_referer or f"{self.base_url}/category/ai/feed/"

    def _headers(self, *, accept: str = "text/html") -> dict[str, str]:
        return {
            "User-Agent": Config.USER_AGENT,
            "Referer": self.base_url + "/",
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        }

    def fetch_html(self, url: str) -> str:
        return get_text(url, headers=self._headers())

    def fetch_list_xml(self, list_url: str) -> str:
        return get_text(
            list_url or self.list_referer,
            headers=self._headers(accept="application/rss+xml, application/xml, text/xml"),
        )

    def discover_list(self, list_url: str) -> List[ArticleRef]:
        return self.parse_list_xml(self.fetch_list_xml(list_url))

    def parse_list_xml(self, xml: str) -> List[ArticleRef]:
        soup = BeautifulSoup(xml, "xml")
        items: List[ArticleRef] = []
        seen: set[str] = set()
        for item in soup.find_all("item"):
            link_el = item.find("link")
            url = canonicalize_url((link_el.get_text(strip=True) if link_el else "").strip())
            title = html.unescape((item.title.get_text(strip=True) if item.title else "").strip())
            if not url.startswith("http") or len(title) < 8:
                continue
            if url in seen:
                continue
            seen.add(url)
            content_html = _rss_html(item.find("content:encoded") or item.find("description"))
            summary = _plain_text(content_html)[:400] or None
            cover = None
            enclosure = item.find("enclosure")
            if enclosure and enclosure.get("url"):
                cover = html.unescape(str(enclosure["url"]).strip()) or None
            author = _rss_author(item.find("author"))
            items.append(
                ArticleRef(
                    url=url,
                    title=title,
                    summary=summary,
                    published_at=_parse_rss_date(item.find("pubDate")),
                    theme="AI",
                    keywords=["AI", "VentureBeat"],
                    cover_image_url=cover,
                    extra={
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

    def parse_detail_html(self, html_text: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html_text, "lxml")
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""
        author_el = soup.select_one("[rel=author]") or soup.select_one("a[href*='/author/']")
        author = author_el.get_text(" ", strip=True) if author_el else None
        content_el = soup.select_one("div.article-body") or soup.select_one("article")
        content_html = str(content_el) if content_el else ""
        published_at = None
        time_el = soup.select_one("time[datetime]")
        if time_el and time_el.get("datetime"):
            published_at = _parse_iso_date(str(time_el["datetime"]))
        og = soup.select_one('meta[property="og:image"]')
        cover = (og.get("content") or "").strip() if og else None
        return self._detail_from_fields(
            url=url,
            title=title,
            content_html=content_html,
            summary=None,
            author=author,
            published_at=published_at,
            cover=cover or None,
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
            content_text=_plain_text(content_html),
            content_html=content_html or None,
            summary=summary,
            author=author,
            published_at=published_at,
            theme="AI",
            keywords=["AI", "VentureBeat"],
            images=images,
            cover_image_url=cover or (images[0] if images else None),
        )


def _rss_html(tag) -> str:
    if tag is None:
        return ""
    raw = tag.decode_contents() if hasattr(tag, "decode_contents") else tag.get_text()
    return html.unescape(raw or "").strip()


def _rss_author(tag) -> str | None:
    if tag is None:
        return None
    raw = html.unescape(tag.get_text(" ", strip=True) or "").strip()
    if not raw:
        return None
    match = _AUTHOR_IN_PARENS.search(raw)
    if match:
        return match.group(1).strip() or raw
    if "@" in raw:
        return None
    return raw


def _plain_text(markup: str | None) -> str:
    soup = BeautifulSoup(markup or "", "lxml")
    for tag in soup.select("script, style, noscript"):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _parse_rss_date(tag) -> datetime | None:
    if tag is None:
        return None
    raw = tag.get_text(strip=True)
    if not raw:
        return None
    try:
        moment = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(BEIJING_TZ).replace(tzinfo=None)


def _parse_iso_date(raw: str) -> datetime | None:
    text = (raw or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(BEIJING_TZ).replace(tzinfo=None)


def _images_from_html(markup: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(markup or "", "lxml")
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
