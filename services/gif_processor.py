#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GIF处理服务 - 将GIF动画转换为视频片段
"""

import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging
from PIL import Image
import imageio
import numpy as np

# MoviePy导入兼容性处理
try:
    from moviepy.editor import ImageSequenceClip, VideoFileClip
except ImportError:
    # 降级到基本的视频处理
    ImageSequenceClip = None
    VideoFileClip = None
    logging.warning("MoviePy未正确安装，部分视频功能可能受限")

import cv2

logger = logging.getLogger(__name__)

class GIFProcessor:
    """GIF动画处理器"""
    
    def __init__(self):
        self.supported_formats = ['.gif']
    
    def is_gif_file(self, file_path: str) -> bool:
        """检查文件是否为GIF格式"""
        try:
            path = Path(file_path)
            return path.suffix.lower() in self.supported_formats
        except Exception:
            return False
    
    def extract_gif_frames(self, gif_path: str) -> Optional[List[np.ndarray]]:
        """提取GIF动画帧"""
        try:
            if not self.is_gif_file(gif_path):
                logger.warning(f"文件不是GIF格式: {gif_path}")
                return None
            
            # 使用imageio读取GIF帧
            reader = imageio.get_reader(gif_path)
            frames = []
            
            for frame in reader:
                # 转换为numpy数组
                if isinstance(frame, np.ndarray):
                    frames.append(frame)
                else:
                    # 如果是PIL Image，转换为numpy数组
                    frames.append(np.array(frame))
            
            reader.close()
            
            if not frames:
                logger.warning(f"GIF文件没有有效帧: {gif_path}")
                return None
                
            logger.info(f"成功提取 {len(frames)} 帧 from {gif_path}")
            return frames
            
        except Exception as e:
            logger.error(f"提取GIF帧失败 {gif_path}: {e}")
            return None
    
    def get_gif_properties(self, gif_path: str) -> Dict:
        """获取GIF属性信息"""
        try:
            if not self.is_gif_file(gif_path):
                return {}
            
            reader = imageio.get_reader(gif_path)
            
            # 获取基本属性
            props = {
                'frame_count': reader.get_length(),
                'duration': reader.get_meta_data().get('duration', 0),
                'loop_count': reader.get_meta_data().get('loop', 0),
                'size': reader.get_meta_data().get('size', (0, 0))
            }
            
            reader.close()
            return props
            
        except Exception as e:
            logger.error(f"获取GIF属性失败 {gif_path}: {e}")
            return {}
    
    def convert_gif_to_video(self, 
                           gif_path: str, 
                           output_path: str,
                           target_fps: Optional[float] = None,
                           target_duration: Optional[float] = None) -> bool:
        """将GIF转换为视频文件"""
        try:
            # 检查MoviePy是否可用
            if ImageSequenceClip is None:
                logger.error("MoviePy不可用，无法进行视频转换")
                return False
            
            # 提取帧
            frames = self.extract_gif_frames(gif_path)
            if not frames:
                return False
            
            # 获取原始属性
            gif_props = self.get_gif_properties(gif_path)
            original_frame_count = len(frames)
            
            # 计算帧率
            if target_fps:
                fps = target_fps
            elif gif_props.get('duration'):
                # 根据原始持续时间计算fps
                total_duration = gif_props['duration'] / 1000.0  # 转换为秒
                fps = original_frame_count / total_duration if total_duration > 0 else 10
            else:
                fps = 10  # 默认帧率
            
            # 如果指定了目标时长，调整帧序列
            if target_duration:
                target_frame_count = int(target_duration * fps)
                if target_frame_count < original_frame_count:
                    # 减少帧数 - 均匀采样
                    indices = np.linspace(0, original_frame_count - 1, target_frame_count, dtype=int)
                    frames = [frames[i] for i in indices]
                elif target_frame_count > original_frame_count:
                    # 增加帧数 - 插值或重复
                    # 简单重复最后一帧
                    frames.extend([frames[-1]] * (target_frame_count - original_frame_count))
            
            # 创建视频片段
            clip = ImageSequenceClip(frames, fps=fps)
            clip.write_videofile(output_path, codec='libx264', audio=False)
            clip.close()
            
            logger.info(f"GIF转换成功: {gif_path} -> {output_path}")
            logger.info(f"帧数: {len(frames)}, FPS: {fps:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"GIF转换失败 {gif_path}: {e}")
            return False
    
    def create_video_segment_from_gif(self,
                                    gif_path: str,
                                    segment_duration: float,
                                    output_path: str) -> bool:
        """创建指定时长的视频片段"""
        try:
            return self.convert_gif_to_video(
                gif_path=gif_path,
                output_path=output_path,
                target_duration=segment_duration
            )
        except Exception as e:
            logger.error(f"创建视频片段失败: {e}")
            return False
    
    def process_gif_for_video(self, gif_path: str, target_duration: float, output_dir: str) -> Optional[str]:
        """处理GIF用于视频生成的便捷函数"""
        try:
            # 生成输出文件路径
            gif_name = Path(gif_path).stem
            output_path = Path(output_dir) / f"{gif_name}_video.mp4"
            
            # 确保输出目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 转换GIF为视频
            success = self.create_video_segment_from_gif(
                gif_path=gif_path,
                segment_duration=target_duration,
                output_path=str(output_path)
            )
            
            if success:
                return str(output_path)
            else:
                return None
                
        except Exception as e:
            logger.error(f"处理GIF失败: {e}")
            return None
    
    def analyze_gif_compatibility(self, gif_path: str) -> Dict:
        """分析GIF与视频处理的兼容性"""
        try:
            analysis = {
                'is_valid': False,
                'issues': [],
                'recommendations': []
            }
            
            # 检查文件是否存在
            if not Path(gif_path).exists():
                analysis['issues'].append('文件不存在')
                return analysis
            
            # 检查是否为GIF格式
            if not self.is_gif_file(gif_path):
                analysis['issues'].append('不是GIF格式文件')
                return analysis
            
            # 获取属性
            props = self.get_gif_properties(gif_path)
            
            if not props:
                analysis['issues'].append('无法读取GIF属性')
                return analysis
            
            # 分析帧数
            frame_count = props.get('frame_count', 0)
            if frame_count == 0:
                analysis['issues'].append('GIF没有动画帧')
            elif frame_count > 100:
                analysis['issues'].append(f'帧数过多({frame_count}帧)，可能导致处理缓慢')
                analysis['recommendations'].append('考虑降低帧率或缩短时长')
            
            # 分析尺寸
            size = props.get('size', (0, 0))
            if size[0] < 100 or size[1] < 100:
                analysis['issues'].append(f'图片尺寸过小 {size}')
                analysis['recommendations'].append('考虑使用更高分辨率的GIF')
            elif size[0] > 1920 or size[1] > 1080:
                analysis['recommendations'].append(f'图片尺寸较大 {size}，建议适当缩小')
            
            # 分析时长
            duration = props.get('duration', 0) / 1000.0  # 转换为秒
            if duration > 30:
                analysis['issues'].append(f'动画时长过长 {duration:.1f}秒')
                analysis['recommendations'].append('建议控制在10秒以内')
            
            analysis['is_valid'] = len(analysis['issues']) == 0
            return analysis
            
        except Exception as e:
            logger.error(f"GIF兼容性分析失败 {gif_path}: {e}")
            return {
                'is_valid': False,
                'issues': [f'分析过程出错: {str(e)}'],
                'recommendations': []
            }

# 单例实例
gif_processor = GIFProcessor()

def process_gif_for_video(gif_path: str, target_duration: float, output_dir: str) -> Optional[str]:
    """处理GIF用于视频生成的便捷函数"""
    try:
        # 生成输出文件路径
        gif_name = Path(gif_path).stem
        output_path = Path(output_dir) / f"{gif_name}_video.mp4"
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 转换GIF为视频
        success = gif_processor.create_video_segment_from_gif(
            gif_path=gif_path,
            segment_duration=target_duration,
            output_path=str(output_path)
        )
        
        if success:
            return str(output_path)
        else:
            return None
            
    except Exception as e:
        logger.error(f"处理GIF失败: {e}")
        return None