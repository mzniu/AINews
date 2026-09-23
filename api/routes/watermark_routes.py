"""去水印相关API路由"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
from loguru import logger
import cv2
import numpy as np
from PIL import Image, ImageDraw
from datetime import datetime
from services.image_watermark_detect import detect_watermark_regions, merge_regions
from services.watermark_inpaint import get_lama_model, inpaint_regions
from ..schemas.request_models import (
    RemoveWatermarkRequest, DetectWatermarkRequest, DrawBordersRequest, CropImageRequest,
    DrawImageTextRequest,
)

router = APIRouter(prefix="/api", tags=["去水印"])

@router.post("/detect-watermark")
async def detect_watermark(request: DetectWatermarkRequest):
    """自动检测图片中可能的水印区域"""
    try:
        image_path = Path(request.image_path.lstrip('/'))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")

        regions = detect_watermark_regions(image_path)
        logger.info(f"检测到 {len(regions)} 个潜在水印区域")
        return {
            "success": True,
            "regions": regions,
            "message": f"检测完成，发现 {len(regions)} 个区域"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"水印检测失败: {e}")
        return {"success": False, "message": f"检测失败: {str(e)}"}

@router.post("/remove-watermark")
async def remove_watermark(request: RemoveWatermarkRequest):
    """使用LaMa模型去除图片水印"""
    try:
        image_path = Path(request.image_path.lstrip('/'))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")
        
        if not request.regions or len(request.regions) == 0:
            return {"success": False, "message": "请至少框选一个水印区域"}

        timestamp = datetime.now().strftime("%H%M%S")
        output_path = inpaint_regions(
            image_path,
            request.regions,
            output_stem_suffix=f"_clean_{timestamp}",
            expand_px=5,
            allow_mock=True,
        )
        try:
            relative_path = str(output_path.relative_to(Path(".").resolve())).replace("\\", "/")
        except ValueError:
            relative_path = str(output_path).replace("\\", "/")
        logger.success(f"水印去除成功: {output_path}")
        
        return {
            "success": True,
            "message": "水印去除成功",
            "original_path": request.image_path,
            "cleaned_path": f"/{relative_path}",
            "regions_count": len(request.regions)
        }
    except Exception as e:
        logger.error(f"水印去除失败：{e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"水印去除失败：{str(e)}"}

@router.post("/replace-edited-image")
async def replace_edited_image(request: dict):
    """替换编辑后的图片（删除原图，将处理后的图片重命名保存）"""
    try:
        import shutil
        from pathlib import Path
        
        original_path = request.get('original_path', '').lstrip('/')
        new_path = request.get('new_path', '').lstrip('/')
        
        original_file = Path(original_path)
        new_file = Path(new_path)
        
        # 验证文件是否存在
        if not original_file.exists():
            logger.error(f"原文件不存在：{original_path}")
            return {"success": False, "message": "原文件不存在"}
        
        if not new_file.exists():
            logger.error(f"新文件不存在：{new_path}")
            return {"success": False, "message": "新文件不存在"}
        
        # 生成新文件名（带时间戳，避免冲突）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = original_file.stem
        suffix = original_file.suffix
        final_name = f"{stem}_edited_{timestamp}{suffix}"
        final_path = original_file.parent / final_name
        
        logger.info(f"准备替换图片：{original_path} -> {final_path}")
        
        # 方案 A：直接移动新文件到原位置（覆盖原文件）
        # 优点：文件名不变，引用不会失效
        # 缺点：丢失原始备份
        try:
            # 备份原文件（加.bak 后缀）
            backup_path = original_file.with_suffix(original_file.suffix + '.bak')
            shutil.copy2(str(original_file), str(backup_path))
            logger.info(f"已备份原文件：{backup_path}")
            
            # 复制新文件到原位置
            shutil.copy2(str(new_file), str(original_file))
            logger.info(f"已复制新文件到：{original_file}")
            
            # 删除备份
            backup_path.unlink()
            logger.info(f"已删除备份：{backup_path}")
            
            # 删除临时文件
            new_file.unlink()
            logger.info(f"已删除临时文件：{new_file}")
            
            result_path = str(original_file).replace("\\", "/")
            
        except Exception as e:
            logger.error(f"文件操作失败：{e}")
            # 如果出错，回退到方案 B：保留两个文件
            shutil.move(str(new_file), str(final_path))
            original_file.unlink()
            result_path = str(final_path).replace("\\", "/")
            logger.info(f"使用备用方案，新文件路径：{result_path}")
        
        logger.success(f"图片替换成功：{result_path}")
        
        return {
            "success": True,
            "message": "图片替换成功",
            "final_path": result_path
        }
        
    except Exception as e:
        logger.error(f"替换图片失败：{e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"替换图片失败：{str(e)}"}


@router.post("/draw-borders")
async def draw_borders(request: DrawBordersRequest):
    """在图片上烧录矩形边框并保存为新文件"""
    try:
        image_path = Path(request.image_path.lstrip('/'))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")

        if not request.borders:
            return {"success": False, "message": "请至少绘制一个边框"}

        img = Image.open(image_path).convert("RGB")
        img_w, img_h = img.size
        draw = ImageDraw.Draw(img)

        for border in request.borders:
            # 防御性检查：坐标和尺寸合法性
            x1 = max(0, border.x)
            y1 = max(0, border.y)
            x2 = min(img_w - 1, border.x + border.width)
            y2 = min(img_h - 1, border.y + border.height)
            if x2 <= x1 or y2 <= y1:
                continue

            # 颜色格式校验：仅允许 #rrggbb / #rgb
            color_hex = border.color.strip()
            if not color_hex.startswith('#') or len(color_hex) not in (4, 7):
                color_hex = '#ff0000'

            draw.rectangle(
                [(x1, y1), (x2, y2)],
                outline=color_hex,
                width=max(1, border.line_width)
            )

        # 保存结果（复用 watermark_removed 目录）
        output_dir = image_path.parent / "watermark_removed"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        output_path = output_dir / f"{image_path.stem}_bordered_{timestamp}{image_path.suffix}"
        img.save(output_path, quality=95)

        relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
        logger.success(f"边框绘制成功: {output_path}")
        return {
            "success": True,
            "message": f"已绘制 {len(request.borders)} 个边框",
            "result_path": f"/{relative_path}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"绘制边框失败：{e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"绘制边框失败：{str(e)}"}


def _save_cropped_image(src_path: Path, out_path: Path, box: tuple[int, int, int, int]) -> None:
    """按像素框裁剪并保存；支持静态图与 GIF 多帧。"""
    x1, y1, x2, y2 = box
    with Image.open(src_path) as im:
        n_frames = int(getattr(im, "n_frames", 1) or 1)
        is_animated = bool(getattr(im, "is_animated", False)) and n_frames > 1

        if is_animated:
            frames = []
            durations = []
            for i in range(n_frames):
                im.seek(i)
                frame = im.convert("RGBA").crop((x1, y1, x2, y2))
                frames.append(frame)
                durations.append(im.info.get("duration", 100))
            save_kwargs = {
                "save_all": True,
                "append_images": frames[1:],
                "duration": durations,
                "loop": im.info.get("loop", 0),
                "disposal": im.info.get("disposal", 2),
            }
            frames[0].save(out_path, **save_kwargs)
            return

        cropped = im.crop((x1, y1, x2, y2))
        suffix = out_path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            cropped.convert("RGB").save(out_path, quality=95)
        elif suffix == ".png" and cropped.mode in ("RGBA", "LA", "P"):
            cropped.save(out_path)
        elif suffix == ".webp":
            cropped.save(out_path, quality=95)
        elif suffix == ".gif":
            cropped.save(out_path)
        else:
            cropped.convert("RGB").save(out_path, quality=95)


@router.post("/crop-image")
async def crop_image(request: CropImageRequest):
    """按框选区域裁剪图片并保存为新文件"""
    try:
        image_path = Path(request.image_path.lstrip("/"))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")

        with Image.open(image_path) as im:
            img_w, img_h = im.size

        x1 = max(0, min(request.x, img_w - 1))
        y1 = max(0, min(request.y, img_h - 1))
        x2 = max(x1 + 1, min(request.x + request.width, img_w))
        y2 = max(y1 + 1, min(request.y + request.height, img_h))
        if (x2 - x1) < 8 or (y2 - y1) < 8:
            return {"success": False, "message": "裁剪区域过小，请重新框选"}

        output_dir = image_path.parent / "watermark_removed"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        output_path = output_dir / f"{image_path.stem}_cropped_{timestamp}{image_path.suffix}"

        _save_cropped_image(image_path, output_path, (x1, y1, x2, y2))

        relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
        logger.success(f"图片裁剪成功: {output_path} ({x2 - x1}x{y2 - y1})")
        return {
            "success": True,
            "message": f"已裁剪为 {x2 - x1} × {y2 - y1} px",
            "result_path": f"/{relative_path}",
            "width": x2 - x1,
            "height": y2 - y1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"裁剪图片失败：{e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"裁剪图片失败：{str(e)}"}


def _parse_hex_color(color: str, default: str = "#ffffff") -> tuple[int, int, int]:
    c = (color or default).strip()
    if not c.startswith("#") or len(c) not in (4, 7):
        c = default
    if len(c) == 4:
        r = int(c[1] * 2, 16)
        g = int(c[2] * 2, 16)
        b = int(c[3] * 2, 16)
        return r, g, b
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def _draw_texts_on_rgba(img: Image.Image, texts: list) -> Image.Image:
    from utils.video_utils import _load_title_font_truetype

    base = img.convert("RGBA")
    draw = ImageDraw.Draw(base)
    for item in texts:
        font = _load_title_font_truetype(item.font_key, item.font_size)
        fill = _parse_hex_color(item.color)
        try:
            draw.text((item.x, item.y), item.text, font=font, fill=fill, anchor="lt")
        except TypeError:
            draw.text((item.x, item.y), item.text, font=font, fill=fill)
    return base


def _save_image_with_texts(src_path: Path, out_path: Path, texts: list) -> None:
    with Image.open(src_path) as im:
        n_frames = int(getattr(im, "n_frames", 1) or 1)
        is_animated = bool(getattr(im, "is_animated", False)) and n_frames > 1

        if is_animated:
            frames = []
            durations = []
            for i in range(n_frames):
                im.seek(i)
                frames.append(_draw_texts_on_rgba(im, texts))
                durations.append(im.info.get("duration", 100))
            frames[0].save(
                out_path,
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=im.info.get("loop", 0),
                disposal=im.info.get("disposal", 2),
            )
            return

        result = _draw_texts_on_rgba(im, texts)
        suffix = out_path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            result.convert("RGB").save(out_path, quality=95)
        elif suffix == ".webp":
            result.save(out_path, quality=95)
        else:
            result.save(out_path)


@router.post("/draw-image-text")
async def draw_image_text(request: DrawImageTextRequest):
    """在图片上烧录文字（支持选字体与颜色）"""
    try:
        image_path = Path(request.image_path.lstrip("/"))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")
        if not request.texts:
            return {"success": False, "message": "请至少添加一条文字"}

        output_dir = image_path.parent / "watermark_removed"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        output_path = output_dir / f"{image_path.stem}_text_{timestamp}{image_path.suffix}"

        _save_image_with_texts(image_path, output_path, request.texts)

        relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
        logger.success(f"图片文字绘制成功: {output_path} ({len(request.texts)} 条)")
        return {
            "success": True,
            "message": f"已添加 {len(request.texts)} 条文字",
            "result_path": f"/{relative_path}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"绘制图片文字失败：{e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"绘制图片文字失败：{str(e)}"}