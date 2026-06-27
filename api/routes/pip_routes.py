"""PiP (Picture-in-Picture) video composition route.

POST /api/pip-compose — overlay a digital human video onto the main video
at the specified corner using ffmpeg overlay filter.
"""

import asyncio
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

PROJECT_ROOT = Path.cwd()
PIP_OUTPUT_DIR = Path("data/pip_outputs")

router = APIRouter(tags=["画中画"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class PipComposeRequest(BaseModel):
    main_video_path: str = Field(..., description="主视频路径（/data/...）")
    pip_video_path: str = Field(..., description="数字人视频路径（/data/...）")
    pip_size_pct: float = Field(default=0.28, ge=0.1, le=0.95, description="PiP宽度占主视频比例")
    pip_position: Literal["bottom-right", "bottom-left", "top-right", "top-left"] = Field(
        default="bottom-right", description="PiP显示位置"
    )
    pip_margin: int = Field(default=30, ge=0, le=2000, description="PiP距边缘像素（兼容旧字段，未指定 x/y 时使用）")
    pip_margin_x: Optional[int] = Field(default=None, ge=0, le=2000, description="PiP横向边距（到左或右）")
    pip_margin_y: Optional[int] = Field(default=None, ge=0, le=2000, description="PiP纵向边距（到顶或底）")
    pip_shape: Literal["rect", "circle", "rounded"] = Field(default="rect", description="PiP形状蒙版")
    pip_corner_radius: int = Field(default=24, ge=0, le=200, description="圆角矩形圆角半径(px,基于缩放后)")
    audio_source: Literal["main", "pip"] = Field(default="main", description="音频来源")
    # 框选裁剪（针对 PiP 源视频，比例 0~1；任一为空表示不裁剪）
    pip_crop_x: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pip_crop_y: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pip_crop_w: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    pip_crop_h: Optional[float] = Field(default=None, gt=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_path(value: str) -> Path:
    """Resolve and validate a /data/ or /static/ relative path."""
    if not value or not value.strip():
        raise ValueError("路径不能为空")
    raw = value.strip().replace("\\", "/")
    if raw.startswith("/data/") or raw.startswith("/static/"):
        raw = raw.lstrip("/")
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    allowed = [root / "data", root / "static"]
    if not any(base in resolved.parents or resolved == base for base in allowed):
        raise ValueError("仅允许使用项目 data/static 目录下的文件")
    if not resolved.is_file():
        raise FileNotFoundError(f"文件不存在: {value}")
    return resolved


def _public_url(path: Path) -> str:
    return "/" + str(path.as_posix()).lstrip("/")


def _build_filter_complex(
    pip_size_pct: float,
    pip_position: str,
    pip_margin_x: int,
    pip_margin_y: int,
    pip_shape: str,
    pip_corner_radius: int = 24,
    crop: Optional[tuple] = None,  # (x, y, w, h) fractions 0~1
) -> str:
    """Build the ffmpeg -filter_complex string for PiP overlay."""
    mx = max(0, int(pip_margin_x))
    my = max(0, int(pip_margin_y))
    pos_map = {
        "bottom-right": f"W-w-{mx}:H-h-{my}",
        "bottom-left":  f"{mx}:H-h-{my}",
        "top-right":    f"W-w-{mx}:{my}",
        "top-left":     f"{mx}:{my}",
    }
    overlay_pos = pos_map.get(pip_position, f"W-w-{mx}:H-h-{my}")

    # 可选裁剪：放在 scale 之前
    if crop is not None:
        cx, cy, cw, ch = crop
        crop_filter = f"crop=iw*{cw}:ih*{ch}:iw*{cx}:ih*{cy},"
    else:
        crop_filter = ""

    scale_filter = f"scale=iw*{pip_size_pct}:-2"

    if pip_shape == "circle":
        # 圆形蒙版：geq 生成 alpha 通道
        filter_complex = (
            f"[1:v]{crop_filter}{scale_filter},"
            f"format=rgba,"
            f"geq='r=r(X\\,Y):g=g(X\\,Y):b=b(X\\,Y)"
            f":a=255*gte(pow(min(W\\,H)/2\\,2)\\,pow(X-W/2\\,2)+pow(Y-H/2\\,2))'[pip];"
            f"[0:v][pip]overlay={overlay_pos}[vout]"
        )
    elif pip_shape == "rounded":
        # 圆角矩形蒙版：四角圆形剔除，其他保留
        r = max(0, int(pip_corner_radius))
        # 像素 (X,Y) 落在四角圆形外 → 透明
        # 落在中心矩形或边缘条带 → 不透明
        # 公式：若 (X<r 且 Y<r) 取距 (r,r) 的距离；同理其他角；其余 alpha=255
        alpha_expr = (
            f"if(lt(X\\,{r})*lt(Y\\,{r})\\,"
            f"255*lte(hypot(X-{r}\\,Y-{r})\\,{r})\\,"
            f"if(gt(X\\,W-{r})*lt(Y\\,{r})\\,"
            f"255*lte(hypot(X-(W-{r})\\,Y-{r})\\,{r})\\,"
            f"if(lt(X\\,{r})*gt(Y\\,H-{r})\\,"
            f"255*lte(hypot(X-{r}\\,Y-(H-{r}))\\,{r})\\,"
            f"if(gt(X\\,W-{r})*gt(Y\\,H-{r})\\,"
            f"255*lte(hypot(X-(W-{r})\\,Y-(H-{r}))\\,{r})\\,"
            f"255))))"
        )
        filter_complex = (
            f"[1:v]{crop_filter}{scale_filter},"
            f"format=rgba,"
            f"geq='r=r(X\\,Y):g=g(X\\,Y):b=b(X\\,Y):a={alpha_expr}'[pip];"
            f"[0:v][pip]overlay={overlay_pos}[vout]"
        )
    else:
        filter_complex = (
            f"[1:v]{crop_filter}{scale_filter}[pip];"
            f"[0:v][pip]overlay={overlay_pos}[vout]"
        )
    return filter_complex


def _compose_pip_sync(
    main_path: Path,
    pip_path: Path,
    output_path: Path,
    pip_size_pct: float,
    pip_position: str,
    pip_margin_x: int,
    pip_margin_y: int,
    pip_shape: str,
    audio_source: str,
    pip_corner_radius: int = 24,
    crop: Optional[tuple] = None,
) -> None:
    """Run ffmpeg synchronously (called via asyncio.to_thread)."""
    filter_complex = _build_filter_complex(
        pip_size_pct, pip_position, pip_margin_x, pip_margin_y, pip_shape,
        pip_corner_radius=pip_corner_radius, crop=crop,
    )
    audio_map = "0:a" if audio_source == "main" else "1:a"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(main_path),
        "-i", str(pip_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", audio_map,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        "-shortest",
        str(output_path),
    ]
    logger.info(f"PiP ffmpeg: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        stderr_tail = result.stderr[-1200:] if result.stderr else "(无错误输出)"
        raise RuntimeError(f"ffmpeg PiP合成失败 (exit {result.returncode}):\n{stderr_tail}")


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/api/pip-compose")
async def pip_compose(request: PipComposeRequest):
    """将数字人视频以画中画形式叠加到主视频指定角落。"""
    try:
        main_path = _resolve_path(request.main_video_path)
        pip_path = _resolve_path(request.pip_video_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    PIP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    output_path = PIP_OUTPUT_DIR / f"pip_{ts}_{uid}.mp4"

    # 组装 crop 元组（四个值都给定才生效）
    crop_tuple = None
    if (
        request.pip_crop_x is not None
        and request.pip_crop_y is not None
        and request.pip_crop_w is not None
        and request.pip_crop_h is not None
    ):
        cx = max(0.0, min(1.0, request.pip_crop_x))
        cy = max(0.0, min(1.0, request.pip_crop_y))
        cw = max(0.01, min(1.0 - cx, request.pip_crop_w))
        ch = max(0.01, min(1.0 - cy, request.pip_crop_h))
        crop_tuple = (cx, cy, cw, ch)

    try:
        margin_x = request.pip_margin_x if request.pip_margin_x is not None else request.pip_margin
        margin_y = request.pip_margin_y if request.pip_margin_y is not None else request.pip_margin
        await asyncio.to_thread(
            _compose_pip_sync,
            main_path,
            pip_path,
            output_path,
            request.pip_size_pct,
            request.pip_position,
            int(margin_x),
            int(margin_y),
            request.pip_shape,
            request.audio_source,
            request.pip_corner_radius,
            crop_tuple,
        )
    except RuntimeError as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("PiP合成异常")
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "success": True,
        "message": "画中画合成成功",
        "output_url": _public_url(output_path),
    }
