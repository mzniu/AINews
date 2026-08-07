"""量子位 adapter (www.qbitai.com)."""
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

_ARTICLE_PATH = re.compile(r"/\d{4}/\d{2}/\d+\.html")


class QbitaiNewsAdapter:
    adapter_id = "qbitai_news"

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

        for link in soup.select("a[href]"):
            href = (link.get("href") or "").strip()
            if not _ARTICLE_PATH.search(href):
                continue
            url = canonicalize_url(self._abs_url(href.split("?")[0]))
            if url in seen:
                continue
            title = (link.get_text(strip=True) or "").strip()
            if len(title) < 4:
                continue
            seen.add(url)
            cover = None
            img = link.select_one("img[src]")
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
        return items

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        article_el = soup.select_one("div.article")
        title_el = article_el.select_one("h1") if article_el else soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else ""

        summary = None
        summary_el = soup.select_one("div.article .zhaiyao")
        if summary_el:
            summary = summary_el.get_text(strip=True)
        if not summary:
            meta = soup.select_one('meta[property="og:description"]')
            if meta and meta.get("content"):
                summary = meta["content"].strip()

        author = None
        author_el = soup.select_one("div.article_info .author a") or soup.select_one(".author a[rel='author']")
        if author_el:
            author = author_el.get_text(strip=True)

        published_at = self._parse_published_at(soup)

        content_html = ""
        content_text = ""
        images: list[str] = []
        if article_el:
            body = article_el
            for noisy in body.select(".article_info, .zhaiyao, script, style"):
                noisy.decompose()
            content_html = str(body)
            content_text = body.get_text("\n", strip=True)
            for img in body.select("img[src], img[data-src]"):
                src = (img.get("data-src") or img.get("src") or "").strip()
                if not src or src.startswith("data:"):
                    continue
                images.append(self._abs_url(src))

        keywords = ["AI", "人工智能"]
        for tag in soup.select(".tags_s a, .article-tags a"):
            text = tag.get_text(strip=True)
            if text and text not in keywords:
                keywords.append(text)

        cover = images[0] if images else None
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image and og_image.get("content") and "logo" not in og_image["content"]:
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
        date_el = soup.select_one("div.article_info .date")
        time_el = soup.select_one("div.article_info .time")
        if date_el:
            date_str = date_el.get_text(strip=True)
            time_str = time_el.get_text(strip=True) if time_el else "00:00:00"
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    return datetime.strptime(f"{date_str} {time_str}", fmt)
                except ValueError:
                    continue
            try:
                return datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass
        return None
