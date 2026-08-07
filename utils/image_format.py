"""Image extension sniffing and resolution (content-type, URL, magic bytes)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

_CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/x-ms-bmp": ".bmp",
}

_VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def sniff_image_ext(data: bytes) -> Optional[str]:
    """Detect image format from file header magic bytes."""
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


def sniff_image_kind(data: bytes) -> Optional[str]:
    """Return short kind: gif, webp, png, jpeg, bmp."""
    ext = sniff_image_ext(data)
    if not ext:
        return None
    if ext == ".jpg":
        return "jpeg"
    return ext.lstrip(".")


def guess_ext_from_content_type(content_type: str) -> Optional[str]:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _CONTENT_TYPE_EXT:
        return _CONTENT_TYPE_EXT[ct]
    for mime, ext in _CONTENT_TYPE_EXT.items():
        if mime.split("/")[-1] in ct:
            return ext
    return None


def guess_ext_from_url(url: str) -> Optional[str]:
    suf = Path(urlparse(url).path).suffix.lower()
    if suf == ".jpeg":
        return ".jpg"
    if suf in _VALID_IMAGE_EXTS:
        return suf
    return None


def resolve_image_ext(
    data: bytes,
    *,
    content_type: Optional[str] = None,
    url: Optional[str] = None,
    fallback: str = ".jpg",
) -> str:
    """Pick the best extension: magic bytes > Content-Type > URL path."""
    return (
        sniff_image_ext(data)
        or (guess_ext_from_content_type(content_type) if content_type else None)
        or (guess_ext_from_url(url) if url else None)
        or fallback
    )


def sniff_file_kind(path: str | Path) -> Optional[str]:
    """Read file header and return kind (gif, webp, ...), or None."""
    try:
        with open(path, "rb") as f:
            return sniff_image_kind(f.read(16))
    except OSError:
        return None
