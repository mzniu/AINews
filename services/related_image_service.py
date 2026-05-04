"""全网相关图片补充服务。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger
from openai import OpenAI

from services.crawler_service import CrawlerService
from services.image_search_scrape import DEFAULT_UA


class RelatedImageService:
    """调用 DeepSeek 生成搜索词，搜索相关网页并打开页面抓取图片。"""

    SUPPORTED_SEARCH_SOURCES = ("baidu", "bing", "toutiao")
    SEARCH_SOURCE_LABELS = {"baidu": "百度", "bing": "Bing", "toutiao": "头条"}
    RESULTS_PER_SEARCH_PAGE = 6

    BAD_IMAGE_HINTS = (
        "logo", "icon", "avatar", "profile", "sprite", "qrcode", "qr", "weixin",
        "wechat", "favicon", "placeholder", "loading", "blank", "advert", "ads",
        "banner-ad", "share", "button",
    )

    @classmethod
    async def collect_related_images(
        cls,
        *,
        title: str,
        content: str,
        source_url: str = "",
        query: Optional[str] = None,
        search_sources: Optional[List[str]] = None,
        max_pages: int = 5,
        max_crawl_pages: int = 18,
        max_images_per_page: int = 6,
    ) -> Dict[str, Any]:
        generated = cls.generate_search_query(title=title, content=content, user_query=query)
        final_query = generated.get("query") or query or title
        if not final_query:
            raise ValueError("无法生成有效搜索词")

        sources = cls._normalize_search_sources(search_sources)
        search_pages_per_source = max(1, min(10, int(max_pages)))
        pages = cls.search_related_pages(
            final_query,
            source_url=source_url,
            search_sources=sources,
            pages_per_source=search_pages_per_source,
            per_page=cls.RESULTS_PER_SEARCH_PAGE,
        )
        if not pages:
            return {
                "success": True,
                "query": final_query,
                "keywords": generated.get("keywords", []),
                "search_sources": sources,
                "search_pages_per_source": search_pages_per_source,
                "pages": [],
                "images": [],
                "message": "未找到相关页面",
            }

        run_dir = cls._make_run_dir(source_url or final_query)
        crawled_pages: List[Dict[str, Any]] = []
        all_images: List[Dict[str, Any]] = []
        seen_urls = set()

        crawl_limit = max(1, min(60, int(max_crawl_pages)))
        for page_index, page_info in enumerate(pages[:crawl_limit], 1):
            try:
                page_result = await cls._crawl_page_images(
                    page_info,
                    query=final_query,
                    save_dir=run_dir / "images",
                    page_index=page_index,
                    max_images=max_images_per_page,
                    seen_urls=seen_urls,
                )
                crawled_pages.append(page_result)
                all_images.extend(page_result.get("images", []))
                await asyncio.sleep(0.8)
            except Exception as exc:
                logger.warning(f"相关页面抓图失败: {page_info.get('url')} - {exc}")
                failed = dict(page_info)
                failed.update({"success": False, "error": str(exc), "images": []})
                crawled_pages.append(failed)

        all_images.sort(key=lambda item: item.get("score", 0), reverse=True)
        metadata = {
            "source_url": source_url,
            "source_title": title,
            "query": final_query,
            "keywords": generated.get("keywords", []),
            "search_sources": sources,
            "search_pages_per_source": search_pages_per_source,
            "candidate_pages_count": len(pages),
            "crawled_pages_count": len(crawled_pages),
            "created_at": datetime.now().isoformat(),
            "pages": crawled_pages,
            "images": all_images,
        }
        with open(run_dir / "related_images.json", "w", encoding="utf-8") as file:
            json.dump(metadata, file, ensure_ascii=False, indent=2)

        metadata_path = str((run_dir / "related_images.json").relative_to(Path(".")))
        metadata_path = metadata_path.replace("\\", "/")

        return {
            "success": True,
            "query": final_query,
            "keywords": generated.get("keywords", []),
            "search_sources": sources,
            "search_pages_per_source": search_pages_per_source,
            "candidate_pages_count": len(pages),
            "crawled_pages_count": len(crawled_pages),
            "pages": crawled_pages,
            "images": all_images,
            "metadata_file": f"/{metadata_path}",
        }

    @classmethod
    def _normalize_search_sources(cls, sources: Optional[List[str]]) -> List[str]:
        out: List[str] = []
        for raw in sources or cls.SUPPORTED_SEARCH_SOURCES:
            source = str(raw or "").strip().lower()
            if source in cls.SUPPORTED_SEARCH_SOURCES and source not in out:
                out.append(source)
        return out or ["baidu"]

    @staticmethod
    def generate_search_query(*, title: str, content: str, user_query: Optional[str] = None) -> Dict[str, Any]:
        """调用 DeepSeek 为图片补充生成全网搜索词。"""
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key or api_key == "your_deepseek_api_key_here":
            raise ValueError("请在 .env 中配置 DEEPSEEK_API_KEY 后再使用全网补充图片")

        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        prompt = f"""你要为一篇 AI/科技资讯文章生成一个用于全网搜索相关配图素材的中文搜索词。

要求：
1. 只输出 JSON，不要解释。
2. query 用于搜索相关网页，不是直接搜图片，长度 8～40 字。
3. query 应包含最核心的产品/公司/模型/技术名，以及一个泛化领域词。
4. keywords 输出 3～6 个关键词，方便前端展示。
5. 如果用户给了搜索词，可以优化它，但不要偏离文章主题。

用户搜索词：{user_query or ''}
标题：{title or ''}
正文节选：{(content or '')[:1800]}

JSON 格式：
{{"query":"搜索词", "keywords":["关键词1", "关键词2"]}}
"""
        response = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            messages=[
                {"role": "system", "content": "你是科技媒体编辑，擅长把文章提炼成适合搜索相关网页和配图素材的关键词。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"搜索词 JSON 解析失败，使用标题回退: {raw[:120]}")
            data = {"query": user_query or title, "keywords": []}

        query = str(data.get("query") or user_query or title or "").strip()
        keywords = data.get("keywords") if isinstance(data.get("keywords"), list) else []
        return {"query": query[:80], "keywords": [str(item).strip()[:40] for item in keywords if str(item).strip()]}

    @classmethod
    def search_related_pages(
        cls,
        query: str,
        *,
        source_url: str = "",
        search_sources: Optional[List[str]] = None,
        pages_per_source: int = 1,
        per_page: int = RESULTS_PER_SEARCH_PAGE,
    ) -> List[Dict[str, Any]]:
        """按搜索源分别翻页搜索相关页面。max_pages 在接口层表示每个源的搜索页数。"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": DEFAULT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        source_netloc = urlparse(source_url).netloc if source_url else ""
        seen = set()
        out: List[Dict[str, Any]] = []
        sources = cls._normalize_search_sources(search_sources)
        page_count = max(1, min(10, int(pages_per_source)))
        per_page = max(1, min(10, int(per_page)))

        for search_source in sources:
            for page_no in range(page_count):
                search_url = cls._build_search_url(search_source, query, page_no)
                try:
                    response = session.get(search_url, timeout=15)
                    response.raise_for_status()
                except requests.RequestException as exc:
                    logger.warning(f"{search_source} 相关页面搜索失败(page={page_no + 1}): {exc}")
                    continue

                soup = BeautifulSoup(response.text, "lxml")
                candidates = cls._extract_search_candidates(soup, search_source)
                accepted_on_page = 0
                for candidate in candidates:
                    href = candidate.get("href", "").strip()
                    title = candidate.get("title", "").strip()
                    if not href or not title or href.startswith(("javascript:", "#")):
                        continue
                    resolved = cls._resolve_search_result_url(session, href, search_source)
                    if not resolved or not resolved.startswith(("http://", "https://")):
                        continue
                    parsed = urlparse(resolved)
                    if cls._is_search_engine_url(parsed.netloc) or (source_netloc and parsed.netloc == source_netloc and resolved == source_url):
                        continue
                    key = resolved.split("#", 1)[0]
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({
                        "title": title[:160],
                        "url": resolved,
                        "source": parsed.netloc,
                        "search_source": search_source,
                        "search_source_label": cls.SEARCH_SOURCE_LABELS.get(search_source, search_source),
                        "search_page": page_no + 1,
                        "snippet": candidate.get("snippet", "")[:240],
                    })
                    accepted_on_page += 1
                    if accepted_on_page >= per_page:
                        break
        return out

    @staticmethod
    def _build_search_url(search_source: str, query: str, page_no: int) -> str:
        q = quote_plus(query)
        if search_source == "bing":
            first = page_no * 10 + 1
            return f"https://www.bing.com/search?q={q}&first={first}"
        if search_source == "toutiao":
            return f"https://so.toutiao.com/search?keyword={q}&pd=information&dvpf=pc&page_num={page_no + 1}"
        pn = page_no * 10
        return f"https://www.baidu.com/s?wd={q}&pn={pn}"

    @classmethod
    def _extract_search_candidates(cls, soup: BeautifulSoup, search_source: str) -> List[Dict[str, str]]:
        if search_source == "bing":
            return cls._extract_bing_candidates(soup)
        if search_source == "toutiao":
            return cls._extract_toutiao_candidates(soup)
        return cls._extract_baidu_candidates(soup)

    @staticmethod
    def _extract_baidu_candidates(soup: BeautifulSoup) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        anchors = soup.select("div.result a[href], div.c-container a[href], h3 a[href]")
        for anchor in anchors:
            parent = anchor.find_parent("div")
            out.append({
                "href": anchor.get("href", ""),
                "title": anchor.get_text(" ", strip=True),
                "snippet": parent.get_text(" ", strip=True) if parent else "",
            })
        return out

    @staticmethod
    def _extract_bing_candidates(soup: BeautifulSoup) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for item in soup.select("li.b_algo"):
            anchor = item.select_one("h2 a[href]") or item.select_one("a[href]")
            if not anchor:
                continue
            snippet = item.select_one(".b_caption p") or item.select_one("p")
            out.append({
                "href": anchor.get("href", ""),
                "title": anchor.get_text(" ", strip=True),
                "snippet": snippet.get_text(" ", strip=True) if snippet else item.get_text(" ", strip=True),
            })
        return out

    @staticmethod
    def _extract_toutiao_candidates(soup: BeautifulSoup) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        selectors = [
            "a[href*='toutiao.com'][href]",
            "a[href*='www.ixigua.com'][href]",
            "a[href*='mp.weixin.qq.com'][href]",
            "a[href^='http'][href]",
        ]
        seen = set()
        for selector in selectors:
            for anchor in soup.select(selector):
                href = anchor.get("href", "").strip()
                title = anchor.get_text(" ", strip=True)
                if not href or not title or href in seen:
                    continue
                seen.add(href)
                parent = anchor.find_parent(["div", "article", "section"])
                out.append({
                    "href": href,
                    "title": title,
                    "snippet": parent.get_text(" ", strip=True) if parent else title,
                })
        return out

    @staticmethod
    def _is_search_engine_url(netloc: str) -> bool:
        host = (netloc or "").lower()
        return any(x in host for x in ("baidu.com", "bing.com", "toutiao.com/search", "so.toutiao.com"))

    @staticmethod
    def _resolve_search_result_url(session: requests.Session, href: str, search_source: str) -> str:
        if not href.startswith("http"):
            return href
        parsed = urlparse(href)
        if "baidu.com" not in parsed.netloc and search_source != "toutiao":
            return href
        try:
            response = session.get(href, timeout=8, allow_redirects=True, stream=True)
            return response.url or href
        except requests.RequestException:
            return href

    @classmethod
    async def _crawl_page_images(
        cls,
        page_info: Dict[str, Any],
        *,
        query: str,
        save_dir: Path,
        page_index: int,
        max_images: int,
        seen_urls: set,
    ) -> Dict[str, Any]:
        from playwright.async_api import async_playwright

        url = page_info["url"]
        images: List[Dict[str, Any]] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1366, "height": 900})
            try:
                try:
                    await page.goto(url, wait_until="networkidle", timeout=22000)
                except Exception:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1800)
                title = await page.title()
                raw_images = await page.evaluate(
                    """() => Array.from(document.images).map((img) => ({
                        src: img.currentSrc || img.src || img.dataset.src || img.dataset.original || '',
                        alt: img.alt || img.title || '',
                        width: img.naturalWidth || img.width || 0,
                        height: img.naturalHeight || img.height || 0
                    }))"""
                )
            finally:
                await browser.close()

        ranked = cls._rank_images(raw_images, query=query, seen_urls=seen_urls)
        save_dir.mkdir(parents=True, exist_ok=True)
        for image_index, image in enumerate(ranked[:max_images], 1):
            download_index = page_index * 100 + image_index
            result = CrawlerService.download_image(image["url"], save_dir, download_index, page_url=url)
            if not result.get("success"):
                continue
            item = {
                "url": image["url"],
                "local_path": result.get("local_path"),
                "format": result.get("format"),
                "alt": image.get("alt", ""),
                "width": image.get("width", 0),
                "height": image.get("height", 0),
                "score": image.get("score", 0),
                "source_page": url,
                "source_title": title or page_info.get("title", ""),
                "success": True,
            }
            images.append(item)

        result_page = dict(page_info)
        result_page.update({
            "success": True,
            "title": title or page_info.get("title", ""),
            "images_count": len(images),
            "images": images,
        })
        return result_page

    @classmethod
    def _rank_images(cls, raw_images: List[Dict[str, Any]], *, query: str, seen_urls: set) -> List[Dict[str, Any]]:
        query_parts = [part.lower() for part in re.split(r"\s+", query or "") if part]
        ranked: List[Dict[str, Any]] = []
        for raw in raw_images or []:
            src = str(raw.get("src") or "").strip()
            if not src.startswith(("http://", "https://")) or src in seen_urls:
                continue
            lower = src.lower()
            if lower.startswith("data:") or lower.endswith(".svg"):
                continue
            if any(hint in lower for hint in cls.BAD_IMAGE_HINTS):
                continue

            width = int(raw.get("width") or 0)
            height = int(raw.get("height") or 0)
            if width and height and (width < 220 or height < 140):
                continue

            alt = str(raw.get("alt") or "")[:200]
            score = 30
            if width >= 800 and height >= 400:
                score += 35
            elif width >= 500 and height >= 280:
                score += 20
            if width and height:
                ratio = width / max(height, 1)
                if 0.7 <= ratio <= 2.2:
                    score += 15
            alt_lower = alt.lower()
            if alt and any(part and part in alt_lower for part in query_parts):
                score += 15
            if any(ext in lower for ext in (".jpg", ".jpeg", ".png", ".webp")):
                score += 5

            seen_urls.add(src)
            ranked.append({
                "url": src,
                "alt": alt,
                "width": width,
                "height": height,
                "score": score,
            })

        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked

    @staticmethod
    def _make_run_dir(seed: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:8]
        path = Path("data/related_images") / f"{digest}_{timestamp}"
        path.mkdir(parents=True, exist_ok=True)
        return path