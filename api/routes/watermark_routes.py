"""去水印相关API路由"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
from loguru import logger
import cv2
import numpy as np
from PIL import Image, ImageDraw
from datetime import datetime
from ..schemas.request_models import (
    RemoveWatermarkRequest, DetectWatermarkRequest, DrawBordersRequest
)

router = APIRouter(prefix="/api", tags=["去水印"])

def merge_regions(regions):
    """合并重叠的水印区域"""
    if not regions:
        return []
    
    merged = []
    for region in regions:
        merged.append(region.copy())
    
    i = 0
    while i < len(merged):
        j = i + 1
        while j < len(merged):
            r1, r2 = merged[i], merged[j]
            # 检查是否重叠
            if (r1['x'] < r2['x'] + r2['width'] and 
                r1['x'] + r1['width'] > r2['x'] and
                r1['y'] < r2['y'] + r2['height'] and
                r1['y'] + r1['height'] > r2['y']):
                # 合并区域
                x1 = min(r1['x'], r2['x'])
                y1 = min(r1['y'], r2['y'])
                x2 = max(r1['x'] + r1['width'], r2['x'] + r2['width'])
                y2 = max(r1['y'] + r1['height'], r2['y'] + r2['height'])
                
                merged[i] = {
                    'x': x1,
                    'y': y1,
                    'width': x2 - x1,
                    'height': y2 - y1
                }
                merged.pop(j)
                j = i + 1  # 重新检查
            else:
                j += 1
        i += 1
    
    return merged

def _make_mock_lama():
    class MockLamaModel:
        def __call__(self, image, mask):
            return image.copy()
    return MockLamaModel()


def get_lama_model():
    """获取LaMa去水印模型实例。先尝试 CUDA，失败则回退到 CPU。"""
    import os
    import torch

    try:
        from simple_lama_inpainting import SimpleLama
    except ImportError as e:
        logger.warning(f"LaMa模型未安装: {e}，使用模拟实现")
        return _make_mock_lama()

    # --- 尝试 CUDA ---
    if torch.cuda.is_available():
        try:
            model = SimpleLama(device='cuda')
            if hasattr(model, 'to'):
                model = model.to('cuda')
            logger.info("LaMa模型加载成功 (GPU加速模式)")
            return model
        except Exception as cuda_err:
            logger.warning(f"CUDA 模式初始化失败，回退到 CPU: {cuda_err}")

    # --- 强制 CPU ---
    # simple_lama_inpainting 在 torch.jit.load() 时未指定 map_location，
    # 导致 CUDA 存储的权重被映射到 CUDA 设备，在 CPU-only PyTorch 下崩溃。
    # 通过 monkey-patch 强制注入 map_location='cpu'，确保权重加载到 CPU。
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    _orig_jit_load = torch.jit.load
    try:
        def _cpu_jit_load(f, *args, **kwargs):
            kwargs.setdefault('map_location', torch.device('cpu'))
            return _orig_jit_load(f, *args, **kwargs)
        torch.jit.load = _cpu_jit_load

        model = SimpleLama(device='cpu')
        if hasattr(model, 'to'):
            model = model.to('cpu')
        logger.info("LaMa模型加载成功 (CPU模式)")
        return model
    except Exception as e:
        logger.error(f"LaMa模型加载失败: {e}")
        return _make_mock_lama()
    finally:
        torch.jit.load = _orig_jit_load  # 恢复原始函数

@router.post("/detect-watermark")
async def detect_watermark(request: DetectWatermarkRequest):
    """自动检测图片中可能的水印区域"""
    try:
        image_path = Path(request.image_path.lstrip('/'))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")
        
        img = cv2.imread(str(image_path))
        if img is None:
            return {"success": False, "message": "无法读取图片"}
        
        h, w = img.shape[:2]
        regions = []
        
        # 策略1: 扫描四个角落区域（水印最常出现的位置）
        corner_regions = [
            (int(w * 0.65), int(h * 0.90), int(w * 0.35), int(h * 0.10)),  # 右下角
            (0, int(h * 0.90), int(w * 0.35), int(h * 0.10)),              # 左下角
            (int(w * 0.65), 0, int(w * 0.35), int(h * 0.08)),              # 右上角
            (0, 0, int(w * 0.35), int(h * 0.08)),                          # 左上角
        ]
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        for rx, ry, rw, rh in corner_regions:
            roi = gray[ry:ry+rh, rx:rx+rw]
            if roi.size == 0:
                continue
            
            # 使用Canny边缘检测 + 形态学操作找文字/Logo区域
            edges = cv2.Canny(roi, 50, 150)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
            dilated = cv2.dilate(edges, kernel, iterations=2)
            
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                cx, cy, cw, ch = cv2.boundingRect(cnt)
                area = cw * ch
                roi_area = rw * rh
                # 过滤: 面积合理（不能太小也不能占满整个角落）
                if area < roi_area * 0.01 or area > roi_area * 0.9:
                    continue
                if cw < 20 or ch < 8:
                    continue
                
                # 转换为全图坐标，并适当扩展边界
                pad = 8
                abs_x = max(0, rx + cx - pad)
                abs_y = max(0, ry + cy - pad)
                abs_w = min(w - abs_x, cw + pad * 2)
                abs_h = min(h - abs_y, ch + pad * 2)
                regions.append({'x': abs_x, 'y': abs_y, 'width': abs_w, 'height': abs_h})
        
        # 合并重叠区域
        regions = merge_regions(regions)
        
        # 策略2: 如果角落没检测到，尝试查找半透明文字水印（全图高亮区域）
        if len(regions) == 0:
            # 查找接近白色的大面积文字（常见半透明水印）
            _, bright = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
            kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 10))
            bright_dilated = cv2.dilate(bright, kernel2, iterations=2)
            
            contours2, _ = cv2.findContours(bright_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours2:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                if area > 500 and w > 30 and h > 15:  # 面积和尺寸过滤
                    regions.append({'x': x, 'y': y, 'width': w, 'height': h})
        
        logger.info(f"检测到 {len(regions)} 个潜在水印区域")
        return {
            "success": True,
            "regions": regions,
            "message": f"检测完成，发现 {len(regions)} 个区域"
        }
        
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
        
        # 加载原图
        img = Image.open(image_path).convert("RGB")
        img_width, img_height = img.size
        
        # 根据regions创建mask（白色=需要修复的区域）
        mask = Image.new("L", (img_width, img_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        
        for region in request.regions:
            x = int(region.get('x', 0))
            y = int(region.get('y', 0))
            w = int(region.get('width', 0))
            h = int(region.get('height', 0))
            if w > 0 and h > 0:
                # 稍微扩大区域以获得更好的效果
                expand = 5
                x1 = max(0, x - expand)
                y1 = max(0, y - expand)
                x2 = min(img_width, x + w + expand)
                y2 = min(img_height, y + h + expand)
                mask_draw.rectangle([(x1, y1), (x2, y2)], fill=255)
        
        # 使用LaMa模型进行修复
        simple_lama = get_lama_model()
        result = simple_lama(img, mask)
        
        # 保存结果
        output_dir = image_path.parent / "watermark_removed"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        output_path = output_dir / f"{image_path.stem}_clean_{timestamp}{image_path.suffix}"
        result.save(output_path, quality=95)
        
        relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
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