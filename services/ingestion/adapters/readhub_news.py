"""Readhub topic adapter."""
from __future__ import annotations

import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from services.ingestion.adapters.base import ArticleDetail, ArticleRef
from services.ingestion.http_client import get_text
from services.ingestion.url_utils import canonicalize_url
from src.utils.config import Config

_TOPIC_PATH = re.compile(r"/topic/[A-Za-z0-9]+")
_PAYWALL_MARKERS = ("专业版", "登录后", "收藏专业版")


class ReadhubNewsAdapter:
    adapter_id = "readhub_news"

    def __init__(self, source_id: str, base_url: str, **_: object) -> None:
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")

    def fetch_html(self, url: str) -> str:
        return get_text(url, headers={"User-Agent": Config.USER_AGENT})

    def discover_list(self, list_url: str) -> List[ArticleRef]:
        return self.parse_list_html(self.fetch_html(list_url))

    def fetch_detail(self, ref: ArticleRef) -> ArticleDetail:
        html = self.fetch_html(ref.url)
        return self.parse_detail_html(html, url=ref.url)

    def _abs_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("http"):
            return href
        return urljoin(self.base_url + "/", href.lstrip("/"))

    def parse_list_html(self, html: str) -> List[ArticleRef]:
        soup = BeautifulSoup(html, "lxml")
        items: List[ArticleRef] = []
        seen: set[str] = set()
        for link in soup.find_all("a", href=True):
            href = link.get("href", "").strip()
            if not _TOPIC_PATH.search(href):
                continue
            url = canonicalize_url(self._abs_url(href.split("?")[0]))
            if url in seen:
                continue
            title = link.get_text(strip=True)
            if len(title) < 4:
                continue
            seen.add(url)
            items.append(ArticleRef(url=url, title=title, theme="科技"))
        return items

    def _clean_paragraphs(self, paragraphs: list[str]) -> list[str]:
        cleaned: list[str] = []
        for text in paragraphs:
            if any(marker in text for marker in _PAYWALL_MARKERS):
                continue
            if len(text) < 20:
                continue
            cleaned.append(text)
        return cleaned

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            og = soup.find("meta", property="og:title")
            title = (og.get("content") or "").strip() if og else ""

        summary = None
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            summary = meta["content"].strip()

        content_root = soup.select_one("article") or soup.select_one("main")
        paragraphs: list[str] = []
        images: list[str] = []
        if content_root:
            for p in content_root.select("p"):
                text = p.get_text("\n", strip=True)
                if text:
                    paragraphs.append(text)
            for img in content_root.select("img[src]"):
                src = (img.get("src") or "").strip()
                if src and not src.startswith("data:"):
                    images.append(self._abs_url(src))

        paragraphs = self._clean_paragraphs(paragraphs)
        content_text = "\n\n".join(paragraphs)
        if not summary and paragraphs:
            summary = paragraphs[0][:240]

        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=content_text,
            content_html=None,
            summary=summary,
            published_at=datetime.utcnow(),
            theme="科技",
            keywords=["科技", "AI"],
            images=images,
            cover_image_url=images[0] if images else None,
        )
