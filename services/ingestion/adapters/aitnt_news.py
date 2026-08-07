"""AITNT news site adapter (travel.aitntnews.com)."""
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


class AitntNewsAdapter:
    adapter_id = "aitnt_news"

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

    def parse_list_html(self, html: str) -> List[ArticleRef]:
        soup = BeautifulSoup(html, "lxml")
        items: List[ArticleRef] = []
        seen: set[str] = set()
        for article in soup.select("article.news-item"):
            link = article.select_one("a[href*='newDetail.html']")
            if not link or not link.get("href"):
                continue
            url = canonicalize_url(urljoin(self.base_url + "/", link["href"]))
            if url in seen:
                continue
            seen.add(url)
            title = (link.get_text(strip=True) or "").strip()
            if not title:
                h3 = article.select_one("h3")
                title = h3.get_text(strip=True) if h3 else ""
            desc_el = article.select_one(".news-description")
            summary = desc_el.get_text(strip=True) if desc_el else None
            theme_link = article.select_one("a[href*='newList.html']")
            theme = theme_link.get_text(strip=True) if theme_link else None
            img = article.select_one("img.news-image")
            cover = urljoin(self.base_url + "/", img["src"]) if img and img.get("src") else None
            published_at = None
            time_match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", article.get_text(" ", strip=True))
            if time_match:
                published_at = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M")
            keywords: list[str] = []
            kw_match = re.search(r"关键词:\s*([^\n]+)", article.get_text("\n", strip=True))
            if kw_match:
                keywords = [k.strip() for k in kw_match.group(1).split(",") if k.strip()]
            view_count = parse_view_count(article.get_text(" ", strip=True))
            items.append(
                ArticleRef(
                    url=url,
                    title=title,
                    summary=summary,
                    published_at=published_at,
                    theme=theme,
                    keywords=keywords,
                    cover_image_url=cover,
                    view_count=view_count,
                )
            )
        return items

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        title_div = soup.select_one("div[style*='font-size: 30px']")
        title = title_div.get_text(strip=True) if title_div else ""
        content_el = soup.select_one("div.new-content")
        content_html = str(content_el) if content_el else ""
        content_text = content_el.get_text("\n", strip=True) if content_el else ""
        images: list[str] = []
        if content_el:
            for img in content_el.select("img[src]"):
                src = img.get("src", "").strip()
                if not src or src.startswith("data:"):
                    continue
                images.append(urljoin(self.base_url + "/", src))
        keywords: list[str] = []
        for a in soup.select("div.new-content ~ div a[href*='searchList']"):
            text = a.get_text(strip=True)
            if text:
                keywords.append(text)
        published_at = None
        meta_text = soup.get_text(" ", strip=True)
        time_match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", meta_text)
        if time_match:
            published_at = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M")
        cover = images[0] if images else None
        view_count = parse_view_count(soup.get_text(" ", strip=True))
        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=content_text,
            content_html=content_html,
            keywords=keywords,
            images=images,
            cover_image_url=cover,
            published_at=published_at,
            view_count=view_count,
        )
