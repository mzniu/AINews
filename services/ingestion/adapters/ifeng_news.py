"""Ifeng tech article adapter."""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from services.ingestion.adapters.base import ArticleDetail, ArticleRef
from services.ingestion.http_client import get_text
from services.ingestion.url_utils import canonicalize_url
from src.utils.config import Config

_ARTICLE_PATH = re.compile(r"/c/[A-Za-z0-9]+")


class IfengNewsAdapter:
    adapter_id = "ifeng_news"

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
            items.append(ArticleRef(url=url, title=title, theme="科技"))
        return items

    def _extract_doc_data(self, html: str) -> dict:
        match = re.search(r"var allData\s*=\s*(\{.*?\});\s*\n", html, re.S)
        if not match:
            raise ValueError("ifeng allData not found")
        data = json.loads(match.group(1))
        doc = data.get("docData")
        if not isinstance(doc, dict):
            raise ValueError("ifeng docData missing")
        return doc

    def _parse_content_list(self, raw: str) -> tuple[str, str, list[str]]:
        if not raw:
            return "", "", []
        try:
            items = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return raw, raw, []
        parts: list[str] = []
        html_parts: list[str] = []
        images: list[str] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            fragment = str(item.get("data") or "")
            if not fragment:
                continue
            html_parts.append(fragment)
            frag_soup = BeautifulSoup(fragment, "lxml")
            text = frag_soup.get_text("\n", strip=True)
            if text:
                parts.append(text)
            for img in frag_soup.select("img[src]"):
                src = (img.get("src") or "").strip()
                if src:
                    images.append(self._abs_url(src))
        return "\n\n".join(parts), "\n".join(html_parts), images

    def parse_detail_html(self, html: str, *, url: str) -> ArticleDetail:
        soup = BeautifulSoup(html, "lxml")
        doc = self._extract_doc_data(html)
        title = str(doc.get("title") or "").strip()
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""
        summary = str(doc.get("summary") or "").strip() or None
        content_data = doc.get("contentData") or {}
        content_list = content_data.get("contentList") if isinstance(content_data, dict) else ""
        content_text, content_html, images = self._parse_content_list(str(content_list or ""))

        published_at = None
        raw_time = doc.get("newsTime") or doc.get("createTime")
        if raw_time:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    published_at = datetime.strptime(str(raw_time)[:19], fmt)
                    break
                except ValueError:
                    continue

        cover = images[0] if images else None
        if not cover and doc.get("bdImg"):
            cover = self._abs_url(str(doc["bdImg"]))

        return ArticleDetail(
            url=canonicalize_url(url),
            title=title,
            content_text=content_text,
            content_html=content_html or None,
            summary=summary,
            author=str(doc.get("author") or "").strip() or None,
            published_at=published_at,
            theme="科技",
            keywords=["科技", "AI"],
            images=images,
            cover_image_url=cover,
        )
