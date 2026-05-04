"""
网页搜图（开发用）：请求百度图片 acjson 接口并解析结果。
注意：依赖第三方页面结构，易失效；商业使用请遵守 robots/服务条款与版权。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List
import requests
from loguru import logger

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BAIDU_REFERER = "https://image.baidu.com/"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": DEFAULT_UA,
            "Referer": BAIDU_REFERER,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    return s


def search_baidu_images(
    query: str,
    *,
    page: int = 0,
    page_size: int = 20,
    timeout: float = 20.0,
) -> List[Dict[str, Any]]:
    """
    调用百度图片搜索 acjson，返回缩略图/原图链接等。
    page: 从 0 开始；pn = page * page_size
    """
    q = (query or "").strip()
    if not q:
        return []

    page_size = max(1, min(60, int(page_size)))
    page = max(0, int(page))
    pn = page * page_size

    url = "https://image.baidu.com/search/acjson"
    params = {
        "tn": "resultjson_com",
        "word": q,
        "queryWord": q,
        "pn": pn,
        "rn": page_size,
        "ie": "utf-8",
        "oe": "utf-8",
        "ipn": "rj",
        "ct": "201326592",
        "fp": "result",
        "is": "",
        "fr": "",
    }

    try:
        r = _session().get(url, params=params, timeout=timeout)
        r.raise_for_status()
        text = r.text
        # 少数情况下夹杂非 JSON 前缀，尝试截取第一个 {
        if not text.strip().startswith("{"):
            m = re.search(r"\{[\s\S]*\}\s*$", text)
            if m:
                text = m.group(0)
        data = json.loads(text)
    except Exception as e:
        logger.warning(f"百度搜图请求失败: {e}")
        return []

    raw_list = data.get("data") or []
    out: List[Dict[str, Any]] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        thumb = item.get("thumbURL") or item.get("replaceUrl")
        if not thumb:
            continue
        # 广告/占位
        if str(item.get("adType", "0")) not in ("0", ""):
            continue

        middle = item.get("middleURL") or ""
        obj = item.get("objURL") or ""

        def _http(u: Any) -> bool:
            s = (u or "").strip() if isinstance(u, str) else ""
            return s.startswith(("http://", "https://"))

        # objURL 有时为站内编码串，优先选用可直连的 https
        download_url = None
        for cand in (obj, middle, thumb):
            if cand and _http(cand):
                download_url = str(cand).strip()
                break
        if not download_url:
            continue
        title = (
            item.get("fromPageTitleEnc")
            or item.get("di")
            or item.get("title", "")
            or ""
        )
        if isinstance(title, str) and title:
            title = re.sub(r"<[^>]+>", "", title)

        host = item.get("fromURLHost") or ""
        out.append(
            {
                "thumb_url": thumb,
                "image_url": download_url,
                "title": str(title)[:200],
                "host": str(host)[:120],
                "referer": BAIDU_REFERER,
            }
        )

    return out


def search_images(
    query: str,
    engine: str = "baidu",
    page: int = 0,
    page_size: int = 20,
) -> List[Dict[str, Any]]:
    engine = (engine or "baidu").strip().lower()
    if engine == "baidu":
        return search_baidu_images(query, page=page, page_size=page_size)
    if engine in ("sogou", "360", "so"):
        logger.warning(f"搜图引擎暂未实现: {engine}")
        return []
    return search_baidu_images(query, page=page, page_size=page_size)
