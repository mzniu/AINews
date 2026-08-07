"""Probe candidate news sources and write verification report to disk."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.config import Config

HEADERS = {"User-Agent": Config.USER_AGENT}
REPORT_JSON = ROOT / "data" / "ingestion" / "source_candidates_report.json"
REPORT_MD = ROOT / "docs" / "ingestion_source_candidates.md"


@dataclass
class CandidateResult:
    id: str
    name: str
    list_url: str
    status: str
    http_status: int | None = None
    list_links: int = 0
    detail_url: str | None = None
    detail_chars: int = 0
    detail_images: int = 0
    needs_playwright: bool = False
    needs_proxy: bool = False
    recommendation: str = "pending"
    notes: list[str] = field(default_factory=list)
    error: str | None = None


CANDIDATES = [
    {
        "id": "aitnt_travel",
        "name": "AITNT Travel",
        "list_url": "http://travel.aitntnews.com/?index=1",
        "link_pattern": r"newDetail\.html\?newId=",
        "content_selector": "div.new-content",
        "integrated": True,
    },
    {
        "id": "kr36_ai",
        "name": "36氪 AI",
        "list_url": "https://www.36kr.com/information/AI/",
        "link_pattern": r"/p/\d+",
        "content_selector": "div.article-content",
        "integrated": True,
    },
    {
        "id": "qbitai",
        "name": "量子位",
        "list_url": "https://www.qbitai.com/",
        "link_pattern": r"/\d{4}/\d{2}/\d+\.html",
        "content_selector": "div.article",
        "integrated": True,
    },
    {
        "id": "jiqizhixin",
        "name": "机器之心",
        "list_url": "https://www.jiqizhixin.com/articles",
        "link_pattern": r"/articles/\d{4}-\d{2}-\d+",
        "content_selector": "article, .article-content",
        "needs_proxy": True,
    },
    {
        "id": "leiphone_ai",
        "name": "雷锋网 AI",
        "list_url": "https://www.leiphone.com/category/ai",
        "link_pattern": r"/article/\d+\.html|/category/ai/",
        "content_selector": ".article-content, .lph-article-comView",
    },
    {
        "id": "huxiu_ai",
        "name": "虎嗅 AI",
        "list_url": "https://www.huxiu.com/channel/21.html",
        "link_pattern": r"/article/\d+\.html",
        "content_selector": ".article-content, .article__content",
    },
    {
        "id": "geekpark",
        "name": "极客公园",
        "list_url": "https://www.geekpark.net/column/304",
        "link_pattern": r"/news/\d+",
        "content_selector": ".article-content, article",
    },
    {
        "id": "aitnt_tech",
        "name": "AITNT Tech",
        "list_url": "http://tech.aitntnews.com/?index=1",
        "link_pattern": r"newDetail\.html\?newId=",
        "content_selector": "div.new-content",
        "notes": ["与 travel 同结构，建议复用 aitnt_news"],
    },
    {
        "id": "venturebeat_ai",
        "name": "VentureBeat AI",
        "list_url": "https://venturebeat.com/category/ai/",
        "link_pattern": r"/\d{4}/\d{2}/\d{2}/",
        "content_selector": "article .article-content, .entry-content",
        "notes": ["英文源"],
    },
]


def fetch(url: str) -> tuple[int, str]:
    response = requests.get(url, timeout=20, headers=HEADERS)
    response.encoding = response.apparent_encoding or "utf-8"
    return response.status_code, response.text


def extract_links(html: str, pattern: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    regex = re.compile(pattern)
    seen: set[str] = set()
    links: list[tuple[str, str]] = []
    base = base_url.rstrip("/")
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not regex.search(href):
            continue
        if href.startswith("/"):
            full = base + href
        elif href.startswith("http"):
            full = href
        else:
            continue
        full = full.split("?")[0]
        title = (anchor.get_text(strip=True) or "").strip()
        if full in seen or len(title) < 4:
            continue
        seen.add(full)
        links.append((title, full))
    return links


def probe_detail(url: str, content_selector: str) -> tuple[int, int]:
    status, html = fetch(url)
    if status >= 400:
        return 0, 0
    soup = BeautifulSoup(html, "lxml")
    best = 0
    images = 0
    for sel in [s.strip() for s in content_selector.split(",")]:
        el = soup.select_one(sel)
        if not el:
            continue
        text_len = len(el.get_text(strip=True))
        if text_len > best:
            best = text_len
            images = len(el.select("img"))
    if best == 0:
        paras = [p.get_text(strip=True) for p in soup.select("p")]
        best = sum(len(p) for p in paras if len(p) > 30)
        images = len(soup.select("img"))
    return best, images


def classify(result: CandidateResult, integrated: bool) -> None:
    if result.error:
        result.status = "fail"
        result.recommendation = "不推荐"
        return
    if result.list_links == 0:
        result.status = "fail"
        result.recommendation = "需 Playwright / 反爬" if result.http_status == 200 else "不可用"
        result.needs_playwright = result.http_status == 200
        return
    if result.detail_chars < 200:
        result.status = "partial"
        result.recommendation = "需进一步 Spike"
        result.needs_playwright = True
        return
    result.status = "pass"
    if integrated:
        result.recommendation = "已接入"
    elif result.needs_proxy:
        result.recommendation = "备选（需代理）"
    else:
        result.recommendation = "推荐接入"


def probe_candidate(raw: dict) -> CandidateResult:
    result = CandidateResult(
        id=raw["id"],
        name=raw["name"],
        list_url=raw["list_url"],
        status="pending",
        needs_proxy=bool(raw.get("needs_proxy")),
    )
    result.notes.extend(raw.get("notes") or [])
    try:
        status, html = fetch(raw["list_url"])
        result.http_status = status
        if status >= 400:
            result.error = f"HTTP {status}"
            classify(result, raw.get("integrated", False))
            return result
        if len(html) < 8000 and raw["id"] == "jiqizhixin":
            result.notes.append(f"页面过短({len(html)}B)，疑似反爬")
            result.needs_proxy = True
        links = extract_links(html, raw["link_pattern"], raw["list_url"])
        result.list_links = len(links)
        if not links:
            classify(result, raw.get("integrated", False))
            return result
        result.detail_url = links[0][1]
        chars, images = probe_detail(result.detail_url, raw["content_selector"])
        result.detail_chars = chars
        result.detail_images = images
        classify(result, raw.get("integrated", False))
    except Exception as exc:
        result.error = str(exc)
        classify(result, raw.get("integrated", False))
    return result


def render_markdown(results: list[CandidateResult], generated_at: str) -> str:
    lines = [
        "# 资讯入库备选源验证清单",
        "",
        f"> 自动生成于 {generated_at}，由 `scripts/probe_ingestion_candidates.py` 产出。",
        "",
        "## 已接入",
        "",
        "| ID | 名称 | 列表 URL | 状态 | 详情字数 | 图片 |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in results:
        if row.recommendation != "已接入":
            continue
        lines.append(
            f"| `{row.id}` | {row.name} | {row.list_url} | {row.status} | {row.detail_chars} | {row.detail_images} |"
        )
    lines.extend(
        [
            "",
            "## 备选（待接入）",
            "",
            "| 推荐度 | ID | 名称 | 列表链接数 | 详情字数 | Playwright | 代理 | 说明 |",
            "|---|---|---|---:|---:|---|---|---|",
        ]
    )
    for row in results:
        if row.recommendation == "已接入":
            continue
        note = "; ".join(row.notes) if row.notes else (row.error or "")
        lines.append(
            f"| {row.recommendation} | `{row.id}` | {row.name} | {row.list_links} | "
            f"{row.detail_chars} | {'是' if row.needs_playwright else '否'} | "
            f"{'是' if row.needs_proxy else '否'} | {note} |"
        )
    lines.extend(
        [
            "",
            "## 接入优先级建议",
            "",
            "1. **雷锋网 AI** / **虎嗅 AI** — 静态 HTML 概率高，中文 AI 垂直",
            "2. **AITNT 其他子站** — 复用 `aitnt_news` 适配器即可",
            "3. **极客公园** — 需 Spike 确认列表结构",
            "4. **机器之心** — 需代理或 Playwright",
            "5. **VentureBeat** — 英文源，按需接入",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    results = [probe_candidate(item) for item in CANDIDATES]
    payload: dict[str, Any] = {
        "generated_at": generated_at,
        "results": [asdict(row) for row in results],
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(render_markdown(results, generated_at), encoding="utf-8")
    print(f"Wrote {REPORT_JSON}")
    print(f"Wrote {REPORT_MD}")
    for row in results:
        print(f"- {row.id}: {row.status} / {row.recommendation} links={row.list_links} chars={row.detail_chars}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
