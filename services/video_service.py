"""视频服务 - 处理视频生成相关业务逻辑"""
from typing import List, Tuple, Dict
from pathlib import Path
from datetime import datetime
import json as _json
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from loguru import logger
from ..utils.video_utils import _load_fonts, _wrap_text, _draw_text_overlay


class VideoService:
    """视频处理服务类"""
    
    @staticmethod
    def create_video_frames(title: str, summary: str, images: List[str]) -> Dict:
        """生成视频关键帧"""
        try:
            if not images:
                return {"success": False, "message": "请至少选择一张图片"}
            
            # 加载背景图
            bg_path = Path("static/imgs/bg.png")
            if not bg_path.exists():
                bg_template = Image.new('RGB', (1080, 1920), color=(102, 126, 234))
            else:
                bg_template = Image.open(bg_path)
            
            img_width, img_height = bg_template.size
            
            # 加载字体
            title_font, subtitle_font, summary_font = VideoService._load_fonts()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path("data/generated") / f"frames_{timestamp}"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            generated_frames = []
            
            # 为每张选中的图片生成一帧
            for idx, img_path in enumerate(images, 1):
                try:
                    # 复制背景图
                    bg = bg_template.copy()
                    
                    # 创建绘制对象
                    draw = ImageDraw.Draw(bg)
                    
                    # 设置文字区域
                    margin = int(img_width * 0.08)
                    text_width = img_width - 2 * margin
                    
                    # 先计算所有元素的高度，以便垂直居中
                    # 计算标题高度
                    title_lines = VideoService._wrap_text(title, title_font, text_width, draw)
                    title_height = sum([draw.textbbox((0, 0), line, font=title_font)[3] - 
                                       draw.textbbox((0, 0), line, font=title_font)[1] + 18 
                                       for line in title_lines])
                    
                    # 计算摘要高度
                    summary_lines = VideoService._wrap_text(summary, summary_font, text_width, draw)
                    summary_height = sum([draw.textbbox((0, 0), line, font=summary_font)[3] - 
                                         draw.textbbox((0, 0), line, font=summary_font)[1] + 12 
                                         for line in summary_lines])
                    
                    # 加载用户图片以获取实际高度
                    user_img_path = Path(img_path.lstrip('/'))
                    target_height = 0
                    target_width = img_width
                    user_img_resized = None
                    
                    if user_img_path.exists():
                        user_img = Image.open(user_img_path)
                        
                        # 缩放用户图片（宽度占背景100%，保持宽高比）
                        ratio = target_width / user_img.width
                        target_height = int(user_img.height * ratio)
                        
                        # 限制最大高度
                        max_height = int(img_height * 0.6)
                        if target_height > max_height:
                            target_height = max_height
                            ratio = target_height / user_img.height
                            target_width = int(user_img.width * ratio)
                        
                        user_img_resized = user_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    
                    # 计算总高度（标题 + 间距 + 图片 + 间距 + 摘要）
                    total_content_height = title_height + 30 + target_height + 40 + summary_height
                    
                    # 标题固定在背景上部15%位置
                    title_start_y = int(img_height * 0.15)
                    current_y = title_start_y
                    
                    # 使用utils中的函数来绘制文字
                    # 绘制标题
                    bg, title_block_height = _draw_text_overlay(
                        bg, title_lines, title_font, title_start_y, 
                        img_width, margin, text_width,
                        text_color=(255, 255, 255), glow_color=(102, 126, 234), line_spacing=18
                    )
                    current_y = title_start_y + title_block_height + 30
                    
                    # 计算摘要的起始位置（距离底部15%）
                    summary_start_y = int(img_height * 0.85) - summary_height
                    
                    # 计算图片的位置（在标题下方和摘要上方之间居中）
                    available_space = summary_start_y - 40 - current_y  # 减去间距
                    image_y = current_y + (available_space - target_height) // 2
                    
                    # 粘贴用户图片
                    if user_img_resized:
                        # 居中粘贴图片
                        paste_x = (img_width - target_width) // 2
                        paste_y = max(current_y, image_y)  # 确保图片在标题下方
                        
                        # 如果用户图片有透明通道，使用它作为mask
                        if user_img_resized.mode == 'RGBA':
                            bg.paste(user_img_resized, (paste_x, paste_y), user_img_resized)
                        else:
                            bg.paste(user_img_resized, (paste_x, paste_y))
                    
                    # 绘制摘要
                    bg, summary_block_height = _draw_text_overlay(
                        bg, summary_lines, summary_font, summary_start_y,
                        img_width, margin, text_width,
                        text_color=(255, 255, 255), line_spacing=12
                    )
                    
                    # 保存关键帧
                    output_path = output_dir / f"frame_{idx:02d}.png"
                    bg.save(output_path, quality=95)
                    
                    relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
                    generated_frames.append({
                        "frame_index": idx,
                        "image_path": f"/{relative_path}",
                        "source_image": img_path
                    })
                    
                    logger.success(f"关键帧 {idx} 生成成功: {output_path}")
                    
                except Exception as frame_error:
                    logger.error(f"生成关键帧 {idx} 失败: {frame_error}")
                    continue
            
            if not generated_frames:
                return {"success": False, "message": "所有关键帧生成失败"}
            
            return {
                "success": True,
                "message": f"成功生成 {len(generated_frames)} 个关键帧",
                "frames": generated_frames,
                "total": len(generated_frames),
                "title": title,
                "summary": summary,
                "output_dir": str(output_dir.relative_to(Path("."))).replace("\\", "/")
            }
            
        except Exception as e:
            logger.error(f"图片生成失败: {e}")
            return {"success": False, "message": f"图片生成失败: {str(e)}"}