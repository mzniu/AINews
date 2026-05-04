"""网页搜图 API（百度 acjson + 远程图片拉取入库）"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException
from loguru import logger

from api.schemas.request_models import ImportRemoteImageRequest, SearchImagesRequest
from services.image_search_scrape import BAIDU_REFERER, DEFAULT_UA, search_images

router = APIRouter(prefix="/api", tags=["搜图"])

_MAX_BYTES = 10 * 1024 * 1024
_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/x-ms-bmp": ".bmp",
}


def _sniff_image_ext(data: bytes) -> Optional[str]:
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:2] == b"BM":
        return ".bmp"
    return None


def _guess_ext_from_url(url: str) -> Optional[str]:
    p = urlparse(url)
    suf = Path(p.path).suffix.lower()
    if suf in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        return ".jpg" if suf == ".jpeg" else suf
    return None


@router.post("/search-images")
async def api_search_images(body: SearchImagesRequest) -> Dict[str, Any]:
    """
    返回缩略图与可选大图 URL；点击后请再调 /api/import-remote-image 入库。
    依赖第三方接口，仅供开发验证。
    """
    q = (body.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query 不能为空")

    items = search_images(
        q,
        engine=body.engine,
        page=body.page,
        page_size=body.page_size,
    )
    return {"success": True, "query": q, "engine": body.engine, "items": items}


@router.post("/import-remote-image")
async def api_import_remote_image(body: ImportRemoteImageRequest) -> Dict[str, Any]:
    """下载远程图片到 data/local_uploads，路径与 /upload-local-image 一致。"""
    raw = (body.url or "").strip()
    if not raw.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="仅支持 http/https URL")

    referer = (body.referer or "").strip() or BAIDU_REFERER
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": referer,
    }

    try:
        r = requests.get(raw, headers=headers, timeout=25, stream=True)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"拉取远程图片失败: {raw[:80]}... {e}")
        raise HTTPException(status_code=502, detail=f"下载失败: {e}") from e

    ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()

    chunks: List[bytes] = []
    total = 0
    for chunk in r.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > _MAX_BYTES:
            raise HTTPException(status_code=400, detail="图片超过 10MB 限制")
        chunks.append(chunk)
    content = b"".join(chunks)
    if len(content) < 32:
        raise HTTPException(status_code=400, detail="文件过小或为空")

    ext: Optional[str] = _EXT.get(ct) if ct in _EXT else None
    if not ext and ct in ("", "application/octet-stream"):
        ext = _sniff_image_ext(content)
    if not ext:
        ext = _guess_ext_from_url(raw)
    if not ext and ct and ct.startswith("image/"):
        ext = _sniff_image_ext(content)
    if not ext:
        ext = _sniff_image_ext(content)
    if not ext:
        if ct and not ct.startswith("image/") and ct != "application/octet-stream":
            raise HTTPException(status_code=400, detail=f"无法识别为图片: {ct}")
        raise HTTPException(status_code=400, detail="无法识别图片格式")

    upload_dir = Path("data/local_uploads") / datetime.now().strftime("%Y%m%d")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{uuid.uuid4()}{ext}"
    with open(file_path, "wb") as f:
        f.write(content)

    relative_path = str(file_path.relative_to(Path("."))).replace("\\", "/")
    image_path = f"/{relative_path}"

    logger.info(f"远程图片已保存: {raw[:100]} -> {image_path}")

    return {
        "success": True,
        "message": "图片已保存",
        "image_path": image_path,
        "size": len(content),
    }
