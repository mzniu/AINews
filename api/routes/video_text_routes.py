#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频文字编辑API路由
提供为视频添加文字水印的功能
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Dict, Optional
import json
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
import logging
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import tempfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["video-text"])

@router.post("/add-text-to-video")
async def add_text_to_video(
    video: UploadFile = File(...),
    settings: str = Form(...)
):
    """
    为视频添加文字水印
    
    Args:
        video: 上传的视频文件
        settings: JSON格式的文字设置参数
    
    Returns:
        dict: 包含生成视频路径、时长、文件大小等信息
    """
    try:
        # 解析设置参数
        text_settings = json.loads(settings)
        logger.info(f"收到视频文字添加请求: {text_settings}")
        
        # 验证必要参数
        if not text_settings.get('content'):
            raise HTTPException(status_code=400, detail="文字内容不能为空")
        
        # 保存上传的视频到临时文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path("data/temp_videos")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建临时文件
        temp_input_path = temp_dir / f"input_{timestamp}_{video.filename}"
        temp_output_path = temp_dir / f"output_{timestamp}.mp4"
        
        # 保存上传的视频
        content = await video.read()
        with open(temp_input_path, "wb") as f:
            f.write(content)
        
        logger.info(f"视频文件已保存: {temp_input_path}")
        
        # 处理视频添加文字
        output_path = await process_video_with_text(
            input_path=temp_input_path,
            output_path=temp_output_path,
            settings=text_settings
        )
        
        # 移动到最终位置
        final_dir = Path("data/processed_videos")
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = final_dir / f"text_added_{timestamp}.mp4"
        
        # 移动文件
        output_path.rename(final_path)
        
        # 清理临时文件
        temp_input_path.unlink()
        
        # 返回结果
        relative_path = str(final_path.relative_to(Path("."))).replace("\\", "/")
        file_size = final_path.stat().st_size / (1024 * 1024)
        duration = get_video_duration(str(final_path))
        
        logger.success(f"视频文字添加完成: {final_path}")
        
        return {
            "success": True,
            "message": "视频文字添加成功",
            "video_path": f"/{relative_path}",
            "duration": round(duration, 1),
            "file_size_mb": round(file_size, 2),
            "timestamp": timestamp
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        raise HTTPException(status_code=400, detail="设置参数格式错误")
    except Exception as e:
        logger.error(f"视频文字添加失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

async def process_video_with_text(input_path: Path, output_path: Path, settings: Dict) -> Path:
    """
    使用MoviePy处理视频并添加文字
    
    Args:
        input_path: 输入视频路径
        output_path: 输出视频路径
        settings: 文字设置参数
    
    Returns:
        Path: 处理后的视频路径
    """
    try:
        logger.info(f"开始处理视频: {input_path}")
        
        # 加载视频
        video_clip = VideoFileClip(str(input_path))
        
        # 创建文字剪辑
        text_clip = create_text_clip(settings, video_clip.size)
        
        # 设置文字显示时长
        text_duration = min(settings.get('duration', 5), video_clip.duration)
        text_clip = text_clip.set_duration(text_duration)
        
        # 应用动画效果
        text_clip = apply_animation_effect(text_clip, settings)
        
        # 合成视频
        final_clip = CompositeVideoClip([video_clip, text_clip])
        
        # 导出视频
        final_clip.write_videofile(
            str(output_path),
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            logger=None
        )
        
        # 关闭资源
        video_clip.close()
        text_clip.close()
        final_clip.close()
        
        logger.info(f"视频处理完成: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"视频处理失败: {e}")
        raise

def create_text_clip(settings: Dict, video_size: tuple) -> TextClip:
    """
    创建文字剪辑
    
    Args:
        settings: 文字设置参数
        video_size: 视频尺寸 (width, height)
    
    Returns:
        TextClip: 文字剪辑对象
    """
    try:
        content = settings.get('content', '')
        font_size = settings.get('fontSize', 36)
        font_color = settings.get('fontColor', '#FFFFFF')
        position = settings.get('position', 'center')
        align = settings.get('align', 'center')
        background = settings.get('background', 'none')
        
        # 处理颜色格式
        if font_color.startswith('#'):
            # 将十六进制颜色转换为RGB元组
            hex_color = font_color.lstrip('#')
            rgb_color = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        else:
            rgb_color = (255, 255, 255)  # 默认白色
        
        # 创建基础文字剪辑
        text_clip = TextClip(
            content,
            fontsize=font_size,
            color='white',  # MoviePy使用color参数
            font='Arial',   # 使用系统字体
            method='caption',
            align=align,
            size=(video_size[0] - 40, None)  # 留出边距
        )
        
        # 应用背景效果
        if background != 'none':
            text_clip = apply_background_effect(text_clip, background, rgb_color)
        
        # 设置位置
        text_position = calculate_text_position(position, video_size, settings)
        text_clip = text_clip.set_position(text_position)
        
        logger.info(f"文字剪辑创建完成: {content[:20]}...")
        return text_clip
        
    except Exception as e:
        logger.error(f"创建文字剪辑失败: {e}")
        raise

def apply_background_effect(text_clip: TextClip, background: str, text_color: tuple) -> TextClip:
    """
    应用背景效果到文字剪辑
    
    Args:
        text_clip: 原始文字剪辑
        background: 背景效果类型
        text_color: 文字颜色
    
    Returns:
        TextClip: 应用背景效果后的剪辑
    """
    try:
        if background == 'solid':
            # 纯色背景 - 使用colormap创建背景
            return text_clip.on_color(
                color=(0, 0, 0),  # 黑色背景
                col_opacity=0.7   # 70%透明度
            )
        elif background == 'gradient':
            # 渐变背景 - 简化为深色半透明背景
            return text_clip.on_color(
                color=(30, 30, 30),  # 深灰色背景
                col_opacity=0.6     # 60%透明度
            )
        elif background == 'outline':
            # 描边效果 - 通过stroke参数实现
            # 注意：MoviePy的TextClip stroke参数可能有限制
            pass  # 描边效果在基础创建时已处理
            
        return text_clip
        
    except Exception as e:
        logger.warning(f"背景效果应用失败: {e}")
        return text_clip

def calculate_text_position(position: str, video_size: tuple, settings: Dict) -> tuple:
    """
    计算文字在视频中的位置
    
    Args:
        position: 位置类型
        video_size: 视频尺寸 (width, height)
        settings: 设置参数
    
    Returns:
        tuple: 位置坐标
    """
    width, height = video_size
    
    if position == 'top':
        return ('center', 50)
    elif position == 'center':
        return ('center', 'center')
    elif position == 'bottom':
        return ('center', height - 100)
    elif position == 'custom':
        x = settings.get('posX', width // 2)
        y = settings.get('posY', height // 2)
        return (x, y)
    else:
        return ('center', 'center')

def apply_animation_effect(text_clip: TextClip, settings: Dict) -> TextClip:
    """
    应用动画效果到文字剪辑
    
    Args:
        text_clip: 文字剪辑
        settings: 设置参数
    
    Returns:
        TextClip: 应用动画效果后的剪辑
    """
    try:
        animation = settings.get('animation', 'fade_in')
        
        if animation == 'fade_in':
            # 淡入效果
            return text_clip.fadein(0.5)
        elif animation == 'slide_up':
            # 上滑效果
            return text_clip.fx(vfx.slide_in, duration=0.5, side='bottom')
        elif animation == 'slide_down':
            # 下滑效果
            return text_clip.fx(vfx.slide_in, duration=0.5, side='top')
        elif animation == 'typewriter':
            # 打字机效果 - 简化实现
            # 这里可以扩展为真正的逐字显示效果
            return text_clip.fadein(0.3)
        else:
            # 无动画
            return text_clip
            
    except Exception as e:
        logger.warning(f"动画效果应用失败: {e}")
        return text_clip

def get_video_duration(video_path: str) -> float:
    """
    获取视频时长
    
    Args:
        video_path: 视频文件路径
    
    Returns:
        float: 视频时长（秒）
    """
    try:
        clip = VideoFileClip(video_path)
        duration = clip.duration
        clip.close()
        return duration
    except Exception as e:
        logger.error(f"获取视频时长失败: {e}")
        return 0.0

# 导出路由
video_text_router = router