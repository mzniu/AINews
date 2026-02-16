"""视频服务 - 处理视频生成相关业务逻辑"""
from typing import List, Tuple, Dict
from pathlib import Path
from datetime import datetime
import json as _json
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from loguru import logger


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
            
            # 加载字体（保持与原始版本一致）
            try:
                title_font = ImageFont.truetype("msyhbd.ttc", 66)       # 微软雅黑粗体，更大
                summary_font = ImageFont.truetype("msyh.ttc", 48)       # 微软雅黑常规
            except:
                try:
                    title_font = ImageFont.truetype("simhei.ttf", 66)   # 备选：黑体
                    summary_font = ImageFont.truetype("simhei.ttf", 48)
                except:
                    title_font = ImageFont.load_default()
                    summary_font = ImageFont.load_default()
            
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
                                            
                        # 取消60%高度限制，允许图片延伸到背景底部
                        # 之前的限制代码已移除
                        # max_height = int(img_height * 0.6)
                        # if target_height > max_height:
                        #     target_height = max_height
                        #     ratio = target_height / user_img.height
                        #     target_width = int(user_img.width * ratio)
                        
                        user_img_resized = user_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    
                    # 计算总高度（标题 + 间距 + 图片 + 间距 + 摘要）
                    total_content_height = title_height + 30 + target_height + 40 + summary_height
                    
                    # 标题固定在背景上部15%位置
                    title_start_y = int(img_height * 0.15)
                    current_y = title_start_y
                    
                    # 绘制标题背景（渐变毛玻璃效果）
                    title_bg_y = current_y - 25
                    title_bg_height = title_height + 40
                    overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    # 多层渐变：上下边缘更透明，中间稍实
                    for i in range(title_bg_height):
                        progress = i / title_bg_height
                        if progress < 0.1:
                            alpha = int(220 * (progress / 0.1))
                        elif progress > 0.9:
                            alpha = int(220 * ((1 - progress) / 0.1))
                        else:
                            alpha = 220
                        overlay_draw.rectangle(
                            [(0, title_bg_y + i), (img_width, title_bg_y + i + 1)],
                            fill=(20, 20, 40, alpha)
                        )
                    bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
                    draw = ImageDraw.Draw(bg)  # 重新创建draw对象
                    
                    # 绘制标题（多层光影效果）
                    for line in title_lines:
                        bbox = draw.textbbox((0, 0), line, font=title_font)
                        line_width = bbox[2] - bbox[0]
                        x = margin + (text_width - line_width) // 2
                        
                        # 第1层：柔和外发光（模拟光晕）
                        for dx in range(-3, 4):
                            for dy in range(-3, 4):
                                if dx*dx + dy*dy <= 9:
                                    draw.text((x + dx, current_y + dy), line, font=title_font, 
                                             fill=(102, 126, 234, 60))  # 品牌蓝色光晕
                        
                        # 第2层：深色阴影（增加立体感）
                        draw.text((x + 3, current_y + 3), line, font=title_font, fill=(0, 0, 0))
                        draw.text((x + 2, current_y + 2), line, font=title_font, fill=(10, 10, 30))
                        
                        # 第3层：主文字（纯白）
                        draw.text((x, current_y), line, font=title_font, fill=(255, 255, 0))
                        
                        current_y += bbox[3] - bbox[1] + 18
                    
                    # 标题和图片之间的间距
                    current_y += 30
                    
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
                    
                    # 绘制摘要背景（柔和渐变半透明）
                    current_y = summary_start_y
                    summary_bg_y = current_y - 35
                    summary_bg_height = summary_height + 50
                    overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    for i in range(summary_bg_height):
                        progress = i / summary_bg_height
                        if progress < 0.1:
                            alpha = int(220 * (progress / 0.1))
                        elif progress > 0.9:
                            alpha = int(220 * ((1 - progress) / 0.1))
                        else:
                            alpha = 220
                        overlay_draw.rectangle(
                            [(0, summary_bg_y + i), (img_width, summary_bg_y + i + 1)],
                            fill=(20, 20, 40, alpha)
                        )
                    bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
                    draw = ImageDraw.Draw(bg)  # 重新创建draw对象
                    
                    # 绘制摘要文字
                    for line in summary_lines:
                        bbox = draw.textbbox((0, 0), line, font=summary_font)
                        line_width = bbox[2] - bbox[0]
                        x = margin + (text_width - line_width) // 2
                        
                        # 阴影
                        draw.text((x + 2, current_y + 2), line, font=summary_font, fill=(0, 0, 0))
                        # 文字（亮白色）
                        draw.text((x, current_y), line, font=summary_font, fill=(255, 255, 255))
                        current_y += bbox[3] - bbox[1] + 12
                    
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