"""雷锋网 AI 频道 adapter (www.leiphone.com/category/ai)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from services.ingestion.adapters.base import ArticleDetail, ArticleRef
from services.ingestion.url_utils import canonicalize_url
from services.ingestion.view_count import parse_view_count
from src.utils.config import Config

_ARTICLE_PATH = re.compile(r"/category/ai/[A-Za-z0-9]+\.html")


class LeiphoneNewsAdapter:
    adapter_id = "leiphone_news"

    def __init__(self, source_id: str, base_url: str, **_: object) -> None:
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")

    def fetch_html(self, url: str) -> str:
        response = requests.get(
            url,
            timeout=Config.CRAWLER_TIMEOUT,
            headers={"User-Agent": Config.USER_AGENT},
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    def discover_list(self, list_url: str) -> List[ArticleRef]:
        return self.parse_list_html(self.fetch_html(list_url))

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

        for link in soup.select("a.headTit[href]"):
            href = (link.get("href") or "").strip()
            if not _ARTICLE_PATH.search(href):
                continue
            url = canonicalize_url(self._abs_url(href.split("?")[0]))
            if url in seen:
                continue
            title = (link.get("title") or link.get_text(strip=True) or "").strip()
            if len(title) < 6:
                continue
            seen.add(url)
            cover = None
            parent = link.find_parent("li") or link.find_parent("div")
            if parent:
                img = parent.select_one("img[src]")
                if img and img.get("src"):
                    cover = self._abs_url(img["src"])
            items.append(
                ArticleRef(
                    url=url,
                    title=title,
                    theme="AI",
                    keywords=["AI", "人工智能"],
                    cover_image_url=cover,
                )
            )

        if items:
            return items

        for link in soup.find_all("a", href=_ARTICLE_PATH):
            href = link.get("href", "").strip()
            title = (link.get_text(strip=True) or "").strip()
            if len(title) < 6:
                continue
            url = canonicalize_url(self._abs_url(href.split("?")[0]))
            if url in seen:
                continue
            seen.add(url)
            items.append(ArticleRef(url=url, title=title, theme="AI"))
        return items

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1.headTit") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        summary = None
        lead_el = soup.select_one(".article-lead")
        if lead_el:
            summary = re.sub(r"^导语：\s*", "", lead_el.get_text(strip=True))
        if not summary:
            meta = soup.select_one('meta[name="description"]')
            if meta and meta.get("content"):
                summary = meta["content"].strip()

        author = None
        author_el = soup.select_one("td.aut a") or soup.select_one(".article-title .aut a")
        if author_el:
            author = author_el.get_text(strip=True)

        published_at = None
        time_el = soup.select_one("td.time")
        if time_el:
            raw = time_el.get_text(strip=True)
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    published_at = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue

        content_el = soup.select_one(".lph-article-comView") or soup.select_one(".article-content")
        content_html = str(content_el) if content_el else ""
        content_text = content_el.get_text("\n", strip=True) if content_el else ""

        images: list[str] = []
        if content_el:
            for img in content_el.select("img[src], img[data-src]"):
                src = (img.get("data-src") or img.get("src") or "").strip()
                if not src or src.startswith("data:"):
                    continue
                images.append(self._abs_url(src))

        keywords = ["AI", "人工智能"]
        cover = images[0] if images else None

        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=content_text,
            content_html=content_html,
            summary=summary,
            author=author,
            published_at=published_at,
            theme="AI",
            keywords=keywords,
            images=images,
            cover_image_url=cover,
            view_count=parse_view_count(html),
        )
