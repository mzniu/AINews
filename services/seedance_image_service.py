"""
Seedance / 火山 Ark 兼容的文生图（封面）。
配置环境变量：
  SEEDANCE_API_KEY 或 ARK_API_KEY
  SEEDANCE_IMAGE_API_URL（默认火山 Ark images/generations）
  SEEDANCE_IMAGE_MODEL（默认 doubao-seedream-5-0-lite-260128，Seedream 5.0 lite）
  SEEDANCE_IMAGE_SIZE（默认 2K，或 1024x1024 等）
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests
from loguru import logger

DEFAULT_API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_MODEL = "doubao-seedream-5-0-lite-260128"
DEFAULT_SIZE = "2K"


def build_cover_prompt_from_content(
    content: str,
    title: str = "",
    extra_hint: str = "",
) -> str:
    """根据正文拼封面提示词（中文，适合资讯类横版封面）。"""
    t = (title or "").strip()[:120]
    body = (content or "").strip().replace("\r", "")[:1200]
    hint = (extra_hint or "").strip()[:200]
    parts = [
        "高清科技资讯类横版视频封面，16:9，构图留白便于叠加标题字幕，",
        "画面干净专业、无文字、无水印、无 logo。",
    ]
    if t:
        parts.append(f"主题与标题相关：{t}。")
    if body:
        parts.append(f"内容要点氛围：{body}")
    if hint:
        parts.append(f"额外要求：{hint}")
    return "".join(parts)[:2000]


def _extract_image_url(payload: Any) -> Optional[str]:
    if not payload:
        return None
    if isinstance(payload, str) and payload.startswith("http"):
        return payload
    if not isinstance(payload, dict):
        return None
    if payload.get("url"):
        return str(payload["url"])
    for key in ("image_url", "imageUrl"):
        if payload.get(key):
            return str(payload[key])
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            u = first.get("url") or first.get("image_url")
            if u:
                return str(u)
    imgs = payload.get("images") or payload.get("output") or payload.get("result")
    if isinstance(imgs, list) and imgs:
        el = imgs[0]
        if isinstance(el, str) and el.startswith("http"):
            return el
        if isinstance(el, dict):
            u = el.get("url") or el.get("image_url")
            if u:
                return str(u)
    return None


def generate_cover_image_url(
    prompt: str,
    *,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """
    调用文生图 API，返回 { success, image_url?, error? }。
    """
    api_key = (os.getenv("SEEDANCE_API_KEY") or os.getenv("ARK_API_KEY") or "").strip()
    if not api_key:
        return {"success": False, "error": "未配置 SEEDANCE_API_KEY 或 ARK_API_KEY"}

    api_url = (os.getenv("SEEDANCE_IMAGE_API_URL") or DEFAULT_API_URL).strip()
    model = (os.getenv("SEEDANCE_IMAGE_MODEL") or DEFAULT_MODEL).strip()
    size = (os.getenv("SEEDANCE_IMAGE_SIZE") or DEFAULT_SIZE).strip()

    prompt = (prompt or "").strip()
    if not prompt:
        return {"success": False, "error": "prompt 为空"}

    body: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "response_format": "url",
        "size": size,
    }
    if os.getenv("SEEDANCE_USE_MAX_IMAGES", "").strip().lower() in ("1", "true", "yes"):
        body["max_images"] = 1

    extra = os.getenv("SEEDANCE_IMAGE_REQUEST_EXTRA_JSON", "").strip()
    if extra:
        try:
            body.update(json.loads(extra))
        except json.JSONDecodeError:
            logger.warning("SEEDANCE_IMAGE_REQUEST_EXTRA_JSON 不是合法 JSON，已忽略")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(api_url, headers=headers, json=body, timeout=timeout)
        text = r.text
        try:
            data = r.json()
        except json.JSONDecodeError:
            logger.warning(f"文生图非 JSON 响应: {text[:500]}")
            return {"success": False, "error": f"接口返回非 JSON: HTTP {r.status_code}"}

        if not r.ok:
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                msg = err.get("message") or err.get("code") or str(err)
            else:
                msg = data.get("message") if isinstance(data, dict) else text[:300]
            return {"success": False, "error": f"HTTP {r.status_code}: {msg}"}

        url = _extract_image_url(data)
        if not url:
            logger.warning(f"文生图响应中未解析到 URL: {str(data)[:800]}")
            return {"success": False, "error": "响应中未找到图片 URL，请检查模型与 SEEDANCE_IMAGE_API_URL"}

        return {"success": True, "image_url": url}
    except requests.RequestException as e:
        logger.exception("文生图请求失败")
        return {"success": False, "error": str(e)}
