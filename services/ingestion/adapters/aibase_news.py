"""AIbase news/daily adapter."""
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

_ARTICLE_PATH = re.compile(r"/zh/(?:news|daily)/\d+")


class AibaseNewsAdapter:
    adapter_id = "aibase_news"

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
            if not _ARTICLE_PATH.search(href):
                continue
            url = canonicalize_url(self._abs_url(href.split("?")[0]))
            if url in seen:
                continue
            title = link.get_text(strip=True)
            if len(title) < 6:
                continue
            seen.add(url)
            items.append(ArticleRef(url=url, title=title, theme="AI"))
        return items

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
        content_text = ""
        content_html = ""
        images: list[str] = []
        if content_root:
            for noisy in content_root.select("nav, header, footer, script, style"):
                noisy.decompose()
            content_html = str(content_root)
            content_text = content_root.get_text("\n", strip=True)
            for img in content_root.select("img[src]"):
                src = (img.get("src") or "").strip()
                if src and not src.startswith("data:"):
                    images.append(self._abs_url(src))

        if not summary and content_text:
            summary = content_text[:240]

        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=content_text,
            content_html=content_html or None,
            summary=summary,
            published_at=datetime.utcnow(),
            theme="AI",
            keywords=["AI", "人工智能"],
            images=images,
            cover_image_url=images[0] if images else None,
        )
