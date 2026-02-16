#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频缩略图生成服务
为视频文件生成第一帧缩略图，用于在图片选择器中显示
"""

from pathlib import Path
import cv2
from PIL import Image
from loguru import logger

class VideoThumbnailService:
    """视频缩略图生成服务"""
    
    @staticmethod
    def generate_video_thumbnail(video_path: str, thumbnail_path: str, 
                               size: tuple = (320, 180)) -> bool:
        """
        为视频生成缩略图
        
        Args:
            video_path: 视频文件路径
            thumbnail_path: 缩略图保存路径
            size: 缩略图尺寸 (width, height)
            
        Returns:
            bool: 是否生成成功
        """
        try:
            logger.info(f"📸 生成视频缩略图: {video_path}")
            
            # 使用OpenCV读取视频第一帧
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"无法打开视频文件: {video_path}")
                return False
            
            # 读取第一帧
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                logger.error(f"无法读取视频帧: {video_path}")
                return False
            
            # 转换颜色空间 BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 转换为PIL图像
            pil_image = Image.fromarray(frame_rgb)
            
            # 调整尺寸并保持质量
            pil_image = pil_image.resize(size, Image.Resampling.LANCZOS)
            
            # 保存缩略图
            thumbnail_dir = Path(thumbnail_path).parent
            thumbnail_dir.mkdir(parents=True, exist_ok=True)
            
            pil_image.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
            
            logger.info(f"✅ 视频缩略图生成成功: {thumbnail_path}")
            return True
            
        except Exception as e:
            logger.error(f"生成视频缩略图失败: {e}")
            return False
    
    @staticmethod
    def batch_generate_thumbnails(video_paths: list, output_dir: str) -> dict:
        """
        批量生成视频缩略图
        
        Args:
            video_paths: 视频文件路径列表
            output_dir: 缩略图输出目录
            
        Returns:
            dict: {video_path: thumbnail_path} 的映射
        """
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        for i, video_path in enumerate(video_paths, 1):
            try:
                video_name = Path(video_path).stem
                thumbnail_path = str(output_dir_path / f"{video_name}_thumb.jpg")
                
                if VideoThumbnailService.generate_video_thumbnail(video_path, thumbnail_path):
                    results[video_path] = thumbnail_path
                    logger.info(f"✅ 批量处理 {i}/{len(video_paths)}: {video_path}")
                else:
                    results[video_path] = None
                    logger.warning(f"❌ 批量处理 {i}/{len(video_paths)}: {video_path}")
                    
            except Exception as e:
                logger.error(f"批量处理视频 {i} 失败: {e}")
                results[video_path] = None
        
        return results

# 导出服务实例
video_thumbnail_service = VideoThumbnailService()