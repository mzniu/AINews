"""Sina tech/mobile article adapter."""
from __future__ import annotations

import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from services.ingestion.adapters.base import ArticleDetail, ArticleRef
from services.ingestion.http_client import get_text
from services.ingestion.json_ld import extract_news_article_ld
from services.ingestion.url_utils import canonicalize_url
from src.utils.config import Config

_DETAIL_PATH = re.compile(r"/detail-|article_|/article/")
_SKIP_IMAGE = ("data:", "t.png")


class SinaTechNewsAdapter:
    adapter_id = "sina_tech_news"

    def __init__(self, source_id: str, base_url: str, **_: object) -> None:
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")

    def fetch_html(self, url: str) -> str:
        return get_text(url, headers={"User-Agent": Config.USER_AGENT})

    def discover_list(self, list_url: str) -> List[ArticleRef]:
        return self.parse_list_html(self.fetch_html(list_url))

    def fetch_detail(self, ref: ArticleRef) -> ArticleDetail:
        html = self.fetch_html(ref.url)
        detail = self.parse_detail_html(html, url=ref.url)
        if not detail.summary and ref.summary:
            detail.summary = ref.summary
        if not detail.published_at and ref.published_at:
            detail.published_at = ref.published_at
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
        for link in soup.find_all("a", href=True):
            href = link.get("href", "").strip()
            if not _DETAIL_PATH.search(href):
                continue
            url = canonicalize_url(self._abs_url(href.split("?")[0]))
            if url in seen:
                continue
            title = link.get_text(strip=True)
            if len(title) < 6:
                continue
            seen.add(url)
            items.append(ArticleRef(url=url, title=title, theme="科技"))
        return items

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        ld = extract_news_article_ld(soup) or {}

        title = str(ld.get("headline") or "").strip()
        if not title:
            title_el = soup.select_one("h1.art_tit_h1") or soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            og = soup.find("meta", property="og:title")
            title = (og.get("content") or "").strip() if og else ""

        summary = str(ld.get("description") or "").strip() or None
        if not summary:
            meta = soup.find("meta", attrs={"name": "description"})
            summary = meta.get("content").strip() if meta and meta.get("content") else None

        content_text = str(ld.get("articleBody") or "").strip()
        content_html = ""
        images: list[str] = []
        content_el = soup.select_one("section.art_content") or soup.select_one(".art_content")
        if content_el:
            for noisy in content_el.select("script, style"):
                noisy.decompose()
            if not content_text:
                content_text = content_el.get_text("\n", strip=True)
            content_html = str(content_el)
            for img in content_el.select("img[src], img[data-src]"):
                src = (img.get("data-src") or img.get("src") or "").strip()
                if not src or any(skip in src for skip in _SKIP_IMAGE):
                    continue
                images.append(self._abs_url(src))

        published_at = None
        raw_date = ld.get("datePublished")
        if raw_date:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    published_at = datetime.strptime(str(raw_date)[:19], fmt)
                    break
                except ValueError:
                    continue
        if published_at is None:
            meta_time = soup.find("meta", property="article:published_time")
            if meta_time and meta_time.get("content"):
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        published_at = datetime.strptime(meta_time["content"][:19], fmt)
                        break
                    except ValueError:
                        continue

        author = None
        if ld.get("author"):
            author_data = ld["author"]
            if isinstance(author_data, dict):
                author = author_data.get("name")
            elif isinstance(author_data, list) and author_data:
                first = author_data[0]
                author = first.get("name") if isinstance(first, dict) else str(first)
            else:
                author = str(author_data)
        if not author:
            meta_author = soup.find("meta", property="article:author")
            author = meta_author.get("content") if meta_author else None

        cover = images[0] if images else None
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            cover = self._abs_url(og_image["content"])

        keywords = list(ld.get("keywords") or [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=content_text,
            content_html=content_html or None,
            summary=summary,
            author=author,
            published_at=published_at,
            theme="科技",
            keywords=keywords or ["科技", "AI"],
            images=images,
            cover_image_url=cover,
        )
