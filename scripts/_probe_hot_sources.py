"""Probe hot source APIs."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from services.ingestion.http_client import get_text
from src.utils.config import Config

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
headers = {"User-Agent": Config.USER_AGENT}


def probe_readhub_rsc():
    html = (ROOT / "tests/fixtures/readhub/topic_sample.html").read_text(encoding="utf-8")
    chunks = re.findall(r"self\.__next_f\.push\(\[1,\"(.*?)\"\]\)", html)
    print("rsc chunks", len(chunks))
    for i, chunk in enumerate(chunks[:5]):
        decoded = chunk.encode("utf-8").decode("unicode_escape")
        if "title" in decoded or "summary" in decoded:
            print("chunk", i, decoded[:500])


def probe_apis():
    session = requests.Session()
    session.headers.update(headers)
    urls = [
        "https://api.readhub.cn/topic?id=8fKxQZqJqZ",
        "https://readhub.cn/api/topic?id=8fKxQZqJqZ",
    ]
    for url in urls:
        try:
            r = session.get(url, timeout=15)
            print(url, r.status_code, r.text[:300])
        except Exception as exc:
            print(url, exc)


def probe_aibase():
    html = get_text("https://www.aibase.com/zh/news", headers=headers)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        data = json.loads(m.group(1))
        print("aibase list keys", data.get("props", {}).get("pageProps", {}).keys())
    detail = get_text("https://www.aibase.com/zh/news/18123", headers=headers)
  # find real news id from list
    ids = re.findall(r"/zh/news/(\d+)", html)
    print("aibase news ids", ids[:5])
    if ids:
        nid = ids[0]
        detail = get_text(f"https://www.aibase.com/zh/news/{nid}", headers=headers)
        (ROOT / "tests/fixtures/aibase/detail_sample.html").write_text(detail, encoding="utf-8")
        m2 = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', detail, re.S)
        if m2:
            d = json.loads(m2.group(1))
            pp = d.get("props", {}).get("pageProps", {})
            print("aibase detail pageProps", list(pp.keys()))
            article = pp.get("newsDetail") or pp.get("detail") or pp.get("data") or {}
            if isinstance(article, dict):
                print("title", article.get("title"))
                print("content len", len(str(article.get("content") or article.get("contentHtml") or "")))


def probe_ifeng_article():
    html = get_text("https://tech.ifeng.com/", headers=headers)
    urls = re.findall(r"https?://tech\.ifeng\.com/c/[A-Za-z0-9]+", html)
    print("ifeng article urls", urls[:5])
    if urls:
        detail = get_text(urls[0], headers=headers)
        (ROOT / "tests/fixtures/ifeng/detail_sample.html").write_text(detail[:800000], encoding="utf-8")
        print("ifeng detail len", len(detail))
        for pat in [r'"title":"([^"]+)"', r'<h1[^>]*>(.*?)</h1>', r'class="index_title"']:
            m = re.search(pat, detail, re.S)
            if m:
                print("match", pat, m.group(1)[:80] if m.lastindex else "yes")


def probe_sina():
    html = get_text("https://tech.sina.cn/", headers=headers)
    urls = re.findall(r"https?://[^\s\"']+sina\.cn[^\s\"']*", html)
    print("sina urls sample", urls[:8])
    article_urls = [u for u in urls if "/article" in u or "/detail" in u or re.search(r"/[a-z]/\d", u)]
    print("sina article urls", article_urls[:5])


def probe_readhub_home():
    html = get_text("https://readhub.cn/", headers=headers)
    topics = re.findall(r'href="(/topic/[A-Za-z0-9]+)"', html)
    print("readhub home topics", topics[:5])
    if not topics:
        return
    url = "https://readhub.cn" + topics[0]
    th = get_text(url, headers=headers)
    (FIX / "readhub" / "topic_sample.html").write_text(th, encoding="utf-8")
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(th, "lxml")
    print("readhub topic url", url)
    print("readhub title", soup.title.string if soup.title else None)
    h1 = soup.select_one("h1")
    print("readhub h1", (h1.get_text(strip=True)[:100] if h1 else None))
    paras = [p.get_text(strip=True) for p in soup.select("p") if len(p.get_text(strip=True)) > 40]
    print("readhub paras", len(paras), paras[0][:120] if paras else "none")


def probe_aibase_news():
    for url in [
        "https://www.aibase.com/zh/news",
        "https://www.aibase.com/news",
        "https://news.aibase.com/",
    ]:
        try:
            html = get_text(url, headers=headers)
            ids = re.findall(r"/zh/news/(\d+)", html)
            print(url, "ids", ids[:5], "len", len(html))
            if ids:
                nid = ids[0]
                detail = get_text(f"https://www.aibase.com/zh/news/{nid}", headers=headers)
                (FIX / "aibase" / "detail_sample.html").write_text(detail, encoding="utf-8")
                m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', detail, re.S)
                if m:
                    pp = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
                    article = pp.get("newsDetail") or pp.get("detail") or {}
                    print("aibase title", article.get("title") if isinstance(article, dict) else None)
                return
        except Exception as exc:
            print(url, exc)


if __name__ == "__main__":
    probe_readhub_home()
    probe_aibase_news()
