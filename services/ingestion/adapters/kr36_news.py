"""36氪 AI 频道 adapter (www.36kr.com/information/AI/)."""
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

_ARTICLE_PATH = re.compile(r"/p/\d+")


class Kr36NewsAdapter:
    adapter_id = "kr36_news"

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

        for block in soup.select(".kr-flow-article-item"):
            link = block.select_one("a.article-item-title[href]")
            if not link:
                continue
            href = link.get("href", "").strip()
            if not _ARTICLE_PATH.search(href):
                continue
            url = canonicalize_url(self._abs_url(href))
            if url in seen:
                continue
            seen.add(url)
            title = (link.get_text(strip=True) or "").strip()
            if not title:
                continue
            desc_el = block.select_one(".article-item-description")
            summary = desc_el.get_text(strip=True) if desc_el else None
            author_el = block.select_one(".kr-flow-bar-author")
            author_name = author_el.get_text(strip=True) if author_el else None
            img_el = block.select_one(".article-item-pic img[src]")
            cover = self._abs_url(img_el["src"]) if img_el and img_el.get("src") else None
            items.append(
                ArticleRef(
                    url=url,
                    title=title,
                    summary=summary,
                    theme="AI",
                    keywords=["AI", "人工智能"] if author_name is None else [],
                    cover_image_url=cover,
                    extra={"list_author": author_name} if author_name else {},
                )
            )

        if items:
            return items

        for link in soup.find_all("a", href=_ARTICLE_PATH):
            href = link.get("href", "").strip()
            title = (link.get_text(strip=True) or "").strip()
            if len(title) < 8:
                continue
            url = canonicalize_url(self._abs_url(href))
            if url in seen:
                continue
            seen.add(url)
            items.append(ArticleRef(url=url, title=title, theme="AI"))
        return items

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1.article-title") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        content_el = soup.select_one("div.article-content") or soup.select_one("article")
        content_html = str(content_el) if content_el else ""
        content_text = content_el.get_text("\n", strip=True) if content_el else ""

        images: list[str] = []
        if content_el:
            for img in content_el.select("img[src], img[data-src]"):
                src = (img.get("data-src") or img.get("src") or "").strip()
                if not src or src.startswith("data:"):
                    continue
                images.append(self._abs_url(src))

        summary_el = soup.select_one('meta[name="description"]')
        summary = summary_el.get("content", "").strip() if summary_el else None

        published_at = self._parse_published_at(soup)
        author = None
        author_el = soup.select_one("a.kr-flow-bar-author") or soup.select_one("span.author-name")
        if author_el:
            author = author_el.get_text(strip=True)

        keywords = ["AI", "人工智能"]
        for tag in soup.select("a.tag, .article-tags a"):
            text = tag.get_text(strip=True)
            if text and text not in keywords:
                keywords.append(text)

        cover = images[0] if images else None
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image and og_image.get("content"):
            cover = self._abs_url(og_image["content"])

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

    def _parse_published_at(self, soup: BeautifulSoup) -> datetime | None:
        meta = soup.select_one('meta[property="article:published_time"]')
        if meta and meta.get("content"):
            raw = meta["content"].strip()
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        time_el = soup.select_one("time[datetime]")
        if time_el and time_el.get("datetime"):
            raw = time_el["datetime"].strip()
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        return None
