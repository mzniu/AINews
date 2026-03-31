#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频嵌入服务 - 处理视频文件在生成视频中的嵌入显示
支持将视频片段作为画中画效果嵌入到主视频中
"""

from typing import List, Tuple, Dict
from pathlib import Path
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageDraw
from loguru import logger

class VideoEmbeddingService:
    """视频嵌入处理服务"""
    
    @staticmethod
    def extract_video_frames(video_path: str, max_frames: int = 10) -> List[np.ndarray]:
        """从视频中提取关键帧"""
        try:
            logger.info(f"🔍 提取视频帧: {video_path}")
            
            # 使用OpenCV读取视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"无法打开视频文件: {video_path}")
                return []
            
            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            
            logger.info(f"视频信息: FPS={fps:.2f}, 总帧数={total_frames}, 时长={duration:.2f}秒")
            
            # 计算采样间隔
            if total_frames <= max_frames:
                interval = 1  # 帧数较少时，每帧都取
            else:
                interval = max(1, total_frames // max_frames)
            
            frames = []
            frame_count = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # 按间隔采样
                if frame_count % interval == 0:
                    # 转换颜色空间 BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                    
                    if len(frames) >= max_frames:
                        break
                        
                frame_count += 1
            
            cap.release()
            logger.info(f"✅ 成功提取 {len(frames)} 帧")
            return frames
            
        except Exception as e:
            logger.error(f"提取视频帧失败: {e}")
            return []
    
    @staticmethod
    def create_video_thumbnail(video_path: str, output_path: str, size: Tuple[int, int] = (320, 180)) -> bool:
        """创建视频缩略图"""
        try:
            logger.info(f"🖼️ 创建视频缩略图: {video_path}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return False
            
            # 读取第一帧
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return False
            
            # 转换颜色空间
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 转换为PIL图像并调整大小
            pil_image = Image.fromarray(frame_rgb)
            pil_image = pil_image.resize(size, Image.Resampling.LANCZOS)
            
            # 保存缩略图
            pil_image.save(output_path, 'JPEG', quality=85, optimize=True)
            logger.info(f"✅ 缩略图已保存: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"创建缩略图失败: {e}")
            return False
    
    @staticmethod
    def prepare_video_for_embedding(video_path: str, target_size: Tuple[int, int] = None) -> List[Image.Image]:
        """准备视频用于嵌入显示（保持原始比例）"""
        try:
            logger.info(f"🎬 准备视频嵌入: {video_path}")
            
            # 获取视频原始尺寸
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"无法打开视频文件: {video_path}")
                return []
            
            original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            logger.info(f"视频原始尺寸: {original_width}x{original_height}")
            
            # 提取视频帧
            frames = VideoEmbeddingService.extract_video_frames(video_path, max_frames=15)
            if not frames:
                return []
            
            # 如果指定了目标尺寸，保持原始比例进行缩放
            pil_frames = []
            if target_size:
                target_width, target_height = target_size
                # 计算保持比例的尺寸
                ratio_width = target_width / original_width
                ratio_height = target_height / original_height
                scale_ratio = min(ratio_width, ratio_height)
                
                new_width = int(original_width * scale_ratio)
                new_height = int(original_height * scale_ratio)
                
                logger.info(f"调整尺寸: {original_width}x{original_height} -> {new_width}x{new_height} (比例: {scale_ratio:.2f})")
            else:
                # 使用原始尺寸
                new_width, new_height = original_width, original_height
                logger.info(f"使用原始尺寸: {new_width}x{new_height}")
            
            # 转换为PIL图像并调整大小
            for frame in frames:
                pil_frame = Image.fromarray(frame)
                if new_width != original_width or new_height != original_height:
                    pil_frame = pil_frame.resize((new_width, new_height), Image.Resampling.LANCZOS)
                if pil_frame.mode != 'RGB':
                    pil_frame = pil_frame.convert('RGB')
                pil_frames.append(pil_frame)
            
            logger.info(f"✅ 准备完成: {len(pil_frames)} 帧")
            return pil_frames
            
        except Exception as e:
            logger.error(f"准备视频嵌入失败: {e}")
            return []
    
    @staticmethod
    def blend_video_into_background(background: Image.Image, video_frames: List[Image.Image], 
                                  position: Tuple[int, int], frame_duration: float,
                                  title_info: tuple = None, summary_info: tuple = None) -> List[Image.Image]:
        """将视频帧融合到背景图像中，并添加文字"""
        try:
            logger.info(f"🎨 融合视频到背景: 位置={position}, 帧数={len(video_frames)}")
            
            result_frames = []
            frames_per_second = max(1, len(video_frames))
            
            # 为每个背景帧添加视频
            for i in range(int(frame_duration)):
                # 复制背景
                bg_copy = background.copy()
                
                # 计算当前应该显示的视频帧
                video_frame_index = int((i / frame_duration) * frames_per_second) % len(video_frames)
                video_frame = video_frames[video_frame_index]
                
                # 粘贴视频帧到背景（转换为RGB以避免通道冲突）
                if video_frame.mode != 'RGB':
                    video_frame = video_frame.convert('RGB')
                if bg_copy.mode != 'RGB':
                    bg_copy = bg_copy.convert('RGB')
                
                # 使用paste而不是alpha_composite（因为要去掉透明度）
                bg_copy.paste(video_frame, position)
                
                # 添加文字（如果提供了title_info和summary_info）
                if title_info and summary_info:
                    bg_copy = VideoEmbeddingService._add_text_to_frame(bg_copy, title_info, summary_info)
                
                result_frames.append(bg_copy)
            
            logger.info(f"✅ 融合完成: {len(result_frames)} 帧")
            return result_frames
            
        except Exception as e:
            logger.error(f"视频融合失败: {e}")
            return []
    
    @staticmethod
    def _add_text_to_frame(bg: Image.Image, title_info: tuple, summary_info: tuple) -> Image.Image:
        """在帧上添加标题和摘要文字（参考图片处理样式）"""
        try:
            # 解包标题信息
            t_font, st_font, main_lines, sub_lines, title_y, main_h, margin, text_width = title_info
            # 解包摘要信息
            summary_font, summary_lines, summary_y = summary_info
            
            img_width, img_height = bg.size
            
            # 使用与图片处理相同的文字叠加函数
            from utils.video_utils import (
                _draw_text_overlay,
                _draw_subtitle_yellow_bar,
                MAIN_SUBTITLE_GAP_PX,
            )
            
            # 绘制主标题：白色 + 蓝色光晕（与图片处理一致）
            bg, _ = _draw_text_overlay(
                bg, main_lines, t_font, title_y, img_width, margin, text_width,
                text_color=(255, 255, 255), glow_color=(102, 126, 234), line_spacing=18
            )
            
            # 绘制副标题：黄底黑字（与动画成片一致）
            if sub_lines:
                sub_y = title_y + main_h + MAIN_SUBTITLE_GAP_PX
                bg, _ = _draw_subtitle_yellow_bar(
                    bg, sub_lines, st_font, sub_y, img_width, margin, text_width,
                    line_spacing=14,
                )
            
            # 绘制摘要：白色（与图片处理一致）
            bg, _ = _draw_text_overlay(
                bg, summary_lines, summary_font, summary_y, img_width, margin, text_width,
                text_color=(255, 255, 255), line_spacing=12, align="left",
            )
            
            return bg
            
        except Exception as e:
            logger.error(f"添加文字到帧失败: {e}")
            return bg
    
    @staticmethod
    def create_pip_video_effect(video_paths: List[str], background_template: Image.Image,
                              title_info: tuple, summary_info: tuple, 
                              duration_per_segment: float = 2.7) -> Dict:
        """创建画中画视频效果"""
        try:
            logger.info(f"🎭 创建画中画效果: 视频数={len(video_paths)}")
            
            results = {
                'segments': [],
                'total_duration': 0,
                'success': True
            }
            
            # 视频显示区域设置 - 保持原始比例
            img_width, img_height = background_template.size
            
            # 获取视频原始尺寸
            cap = cv2.VideoCapture(video_paths[0])  # 使用第一个视频获取尺寸信息
            if cap.isOpened():
                video_original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                video_original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                logger.info(f"视频原始尺寸: {video_original_width}x{video_original_height}")
            else:
                # 默认16:9比例
                video_original_width, video_original_height = 1920, 1080
                logger.warning("无法获取视频尺寸，使用默认16:9比例")
            
            # 计算视频显示的最大尺寸（保持原始比例）
            max_video_width = img_width
            max_video_height = int(img_height * 0.6)  # 与图片处理保持一致
            
            # 计算保持比例的尺寸
            ratio_width = max_video_width / video_original_width
            ratio_height = max_video_height / video_original_height
            
            # 修改策略：如果视频宽度小于背景宽度，则以宽度为准进行放大
            if video_original_width < img_width:
                # 视频宽度不足，以宽度为准放大
                scale_ratio = ratio_width
                logger.info(f"视频宽度不足，按宽度放大: {video_original_width} -> {img_width}")
            else:
                # 视频宽度足够，按高度限制缩放
                scale_ratio = min(ratio_width, ratio_height)
                logger.info(f"视频宽度足够，按比例缩放: 限制高度{max_video_height}")
            
            video_width = int(video_original_width * scale_ratio)
            video_height = int(video_original_height * scale_ratio)
            
            logger.info(f"调整后视频尺寸: {video_width}x{video_height} (比例: {scale_ratio:.2f})")
            
            # 计算视频显示位置（在标题和摘要之间居中）
            margin = int(img_width * 0.08)
            text_width = img_width - 2 * margin
            
            # 标题区域高度计算（参考正常图片处理逻辑）
            from utils.video_utils import _load_fonts, _wrap_text
            title_font, subtitle_font, summary_font = _load_fonts()
            draw_placeholder = ImageDraw.Draw(background_template)
            
            # 计算标题高度
            title_parts = title_info[2] if title_info else ['测试标题']  # main_lines
            title_height = sum([draw_placeholder.textbbox((0, 0), line, font=title_font)[3] - 
                               draw_placeholder.textbbox((0, 0), line, font=title_font)[1] + 18 
                               for line in title_parts])
            
            # 计算摘要高度
            summary_lines = summary_info[1] if summary_info else ['测试摘要']
            summary_height = sum([draw_placeholder.textbbox((0, 0), line, font=summary_font)[3] - 
                                 draw_placeholder.textbbox((0, 0), line, font=summary_font)[1] + 12 
                                 for line in summary_lines])
            
            # 计算视频位置（在标题和摘要之间居中）
            title_start_y = int(img_height * 0.15)  # 标题起始位置
            summary_start_y = int(img_height * 0.85) - summary_height  # 摘要起始位置
            
            # 可用垂直空间
            available_height = summary_start_y - 40 - (title_start_y + title_height + 30)
            
            # 如果计算的视频高度超过可用空间，调整视频高度
            if video_height > available_height:
                video_height = available_height
                # 重新计算宽度以保持宽高比（假设原视频是16:9）
                video_width = int(video_height * 16 / 9)
                if video_width > img_width:
                    video_width = img_width
                    video_height = int(video_width * 9 / 16)
            
            # 视频居中位置
            video_x = (img_width - video_width) // 2
            video_y = title_start_y + title_height + 30 + (available_height - video_height) // 2
            video_y = max(title_start_y + title_height + 30, video_y)
            
            for idx, video_path in enumerate(video_paths, 1):
                try:
                    logger.info(f"处理视频 {idx}/{len(video_paths)}: {video_path}")
                    
                    # 准备视频帧（传递目标尺寸以保持比例）
                    video_frames = VideoEmbeddingService.prepare_video_for_embedding(
                        video_path, (video_width, video_height)
                    )
                    
                    if not video_frames:
                        logger.warning(f"跳过视频 {idx}: 无法处理视频文件")
                        continue
                    
                    # 创建该段的背景帧序列
                    segment_frames = VideoEmbeddingService.blend_video_into_background(
                        background_template, video_frames, (video_x, video_y), duration_per_segment,
                        title_info, summary_info
                    )
                    
                    if segment_frames:
                        results['segments'].append({
                            'segment_index': idx,
                            'video_path': video_path,
                            'frames': segment_frames,
                            'duration': duration_per_segment,
                            'position': (video_x, video_y),
                            'size': (video_width, video_height)
                        })
                        results['total_duration'] += duration_per_segment
                        logger.info(f"✅ 视频段 {idx} 处理完成")
                    else:
                        logger.warning(f"❌ 视频段 {idx} 生成失败")
                        
                except Exception as e:
                    logger.error(f"处理视频 {idx} 失败: {e}")
                    continue
            
            logger.info(f"🎬 画中画效果创建完成: 总时长={results['total_duration']:.2f}秒, 段数={len(results['segments'])}")
            return results
            
        except Exception as e:
            logger.error(f"创建画中画效果失败: {e}")
            return {'success': False, 'error': str(e)}

# 导出服务类
video_embedding_service = VideoEmbeddingService()