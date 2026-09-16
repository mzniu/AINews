"""IT之家频道 adapter (it.ithome.com)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from services.ingestion.adapters.base import ArticleDetail, ArticleRef
from services.ingestion.http_client import get_text, post_json
from services.ingestion.url_utils import canonicalize_url
from services.ingestion.view_count import parse_view_count
from src.utils.config import Config

_ARTICLE_PATH = re.compile(r"/0/\d+/\d+\.htm")
_OT_FRAC = re.compile(r"(\.\d{6})\d+")
_SKIP_IMAGE = ("t.png", "/images/v2/", "data:")
BEIJING = timezone(timedelta(hours=8))


def parse_ithome_ot(raw: str | None) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    text = _OT_FRAC.sub(r"\1", text)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class IthomeNewsAdapter:
    adapter_id = "ithome_news"

    def __init__(
        self,
        source_id: str,
        base_url: str,
        *,
        max_load_more: int = 4,
        **_: object,
    ) -> None:
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")
        self.max_load_more = max(0, int(max_load_more))

    def fetch_html(self, url: str) -> str:
        return get_text(url, headers={"User-Agent": Config.USER_AGENT})

    def discover_list(self, list_url: str) -> List[ArticleRef]:
        html = self.fetch_html(list_url)
        items = self.parse_list_html(html)
        seen = {item.url for item in items}
        domain = self._channel_domain(list_url)
        for _ in range(self.max_load_more):
            ot_ms = self._last_ot_ms(items)
            if ot_ms is None:
                break
            payload = self.fetch_load_more(domain, ot_ms)
            content = (payload or {}).get("content") if isinstance(payload, dict) else None
            if not isinstance(content, dict) or int(content.get("count") or 0) <= 0:
                break
            added = 0
            for item in self.parse_list_html(str(content.get("html") or "")):
                if item.url in seen:
                    continue
                seen.add(item.url)
                items.append(item)
                added += 1
            if added == 0:
                break
        return items

    def fetch_load_more(self, domain: str, ot_ms: int) -> dict[str, Any] | None:
        url = f"{self.base_url}/category/domainpage?domain={domain}&subdomain=&ot={ot_ms}"
        response = post_json(
            url,
            headers={
                "User-Agent": Config.USER_AGENT,
                "Referer": f"{self.base_url}/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    def fetch_detail(self, ref: ArticleRef) -> ArticleDetail:
        html = self.fetch_html(ref.url)
        detail = self.parse_detail_html(html, url=ref.url)
        if not detail.summary and ref.summary:
            detail.summary = ref.summary
        if not detail.theme and ref.theme:
            detail.theme = ref.theme
        if not detail.keywords and ref.keywords:
            detail.keywords = ref.keywords
        if not detail.cover_image_url and ref.cover_image_url:
            detail.cover_image_url = ref.cover_image_url
        if not detail.published_at and ref.published_at:
            detail.published_at = ref.published_at
        if detail.view_count is None and ref.view_count is not None:
            detail.view_count = ref.view_count
        return detail

    def parse_list_html(self, html: str) -> List[ArticleRef]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("#list ul.bl > li")
        if not cards:
            cards = [li for li in soup.select("li") if li.select_one("a.title[href]")]
        items: List[ArticleRef] = []
        seen: set[str] = set()
        for card in cards:
            link = card.select_one("a.title[href]")
            if link is None:
                continue
            href = (link.get("href") or "").strip().split("?")[0]
            if not _ARTICLE_PATH.search(href):
                continue
            url = canonicalize_url(self._abs_url(href))
            if url in seen:
                continue
            title = (link.get("title") or link.get_text(strip=True) or "").strip()
            if len(title) < 6:
                continue
            seen.add(url)
            summary_el = card.select_one("div.m")
            ot_el = card.select_one("div.c[data-ot]")
            published_at = parse_ithome_ot(ot_el.get("data-ot") if ot_el else None)
            cover = None
            img = card.select_one("img[data-original], img[src]")
            if img:
                cover = self._image_url(img.get("data-original") or img.get("src"))
            tags = [a.get_text(strip=True) for a in card.select(".tags a") if a.get_text(strip=True)]
            ot_ms = None
            if published_at is not None:
                dt = published_at if published_at.tzinfo else published_at.replace(tzinfo=BEIJING)
                ot_ms = int(dt.timestamp() * 1000)
            items.append(
                ArticleRef(
                    url=url,
                    title=title,
                    summary=summary_el.get_text(strip=True) if summary_el else None,
                    published_at=published_at,
                    theme="IT",
                    keywords=["IT", *tags],
                    cover_image_url=cover,
                    extra={"ot_ms": ot_ms} if ot_ms else {},
                )
            )
        return items

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        summary = None
        meta = soup.select_one('meta[name="description"]')
        if meta and meta.get("content"):
            summary = meta["content"].strip()

        author = None
        author_el = soup.select_one("#author_baidu strong")
        if author_el:
            author = author_el.get_text(strip=True)

        published_at = None
        time_el = soup.select_one("#pubtime_baidu")
        if time_el:
            raw = time_el.get_text(strip=True)
            for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    published_at = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue

        content_el = soup.select_one("#paragraph") or soup.select_one(".post_content")
        if content_el:
            content_el = BeautifulSoup(str(content_el), "lxml")
            body = content_el.select_one("#paragraph") or content_el.select_one(".post_content") or content_el
            for noisy in body.select(".related_post, script, style, .hot_tags"):
                noisy.decompose()
            content_html = str(body)
            content_text = body.get_text("\n", strip=True)
        else:
            content_html = ""
            content_text = ""

        images: list[str] = []
        if content_el:
            body = content_el.select_one("#paragraph") or content_el.select_one(".post_content") or content_el
            for img in body.select("img"):
                src = self._image_url(img.get("data-original") or img.get("data-src") or img.get("src"))
                if src and src not in images:
                    images.append(src)

        keywords = ["IT"]
        meta_kw = soup.select_one('meta[name="keywords"]')
        if meta_kw and meta_kw.get("content"):
            for part in str(meta_kw["content"]).split(","):
                text = part.strip()
                if text and text not in keywords:
                    keywords.append(text)

        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=content_text,
            content_html=content_html,
            summary=summary,
            author=author,
            published_at=published_at,
            theme="IT",
            keywords=keywords,
            images=images,
            cover_image_url=images[0] if images else None,
            view_count=parse_view_count(html),
        )

    def _abs_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("http"):
            return href
        return urljoin(self.base_url + "/", href.lstrip("/"))

    def _image_url(self, src: str | None) -> str | None:
        value = (src or "").strip()
        if not value or any(token in value for token in _SKIP_IMAGE):
            return None
        return self._abs_url(value.split("?")[0] if "x-bce-process" in value else value)

    def _channel_domain(self, list_url: str) -> str:
        host = (urlparse(list_url or self.base_url).hostname or "").lower()
        head = host.split(".")[0]
        if head and head not in {"www", "ithome"}:
            return head
        return "it"

    def _last_ot_ms(self, items: List[ArticleRef]) -> int | None:
        for item in reversed(items):
            extra = item.extra or {}
            if extra.get("ot_ms"):
                return int(extra["ot_ms"])
            if item.published_at is not None:
                dt = item.published_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=BEIJING)
                return int(dt.timestamp() * 1000)
        return None
