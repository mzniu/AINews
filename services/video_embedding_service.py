#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频嵌入服务 - 处理视频文件在生成视频中的嵌入显示
支持将视频片段作为画中画效果嵌入到主视频中
"""

from typing import List, Tuple, Dict, Optional
from pathlib import Path
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageDraw
from loguru import logger

# 画中画：源素材按此帧率均匀采样；合成输出按此帧率重复背景帧
PIP_EMBED_FPS = 12.0
PIP_MAX_SOURCE_FRAMES = 480
# 从源视频读取的时长 = 成片片段时长 × 该系数，再映射回成片时长，相当于约 1/系数 倍速（默认 1.5× 快进）
PIP_SOURCE_DURATION_FACTOR = 1.5


class VideoEmbeddingService:
    """视频嵌入处理服务"""
    
    @staticmethod
    def extract_video_frames(
        video_path: str,
        max_frames: int = 10,
        *,
        target_fps: Optional[float] = None,
        start_sec: float = 0.0,
        duration_sec: Optional[float] = None,
    ) -> List[np.ndarray]:
        """
        从视频中提取帧。
        指定 duration_sec 时只从 [start_sec, start_sec+duration) 对应的时间范围内顺序采样，
        再按 target_fps 在该片段内均匀抽帧（画中画与「配置的秒数」一致，避免整段视频跳剪）。
        """
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
            full_duration = total_frames / fps if fps > 0 else 0.0
            
            if duration_sec is not None:
                t0 = max(0.0, float(start_sec))
                t1 = min(full_duration, t0 + max(0.0, float(duration_sec)))
                if t1 <= t0 and full_duration > 0:
                    t1 = min(full_duration, t0 + 1.0 / max(fps, 1e-6))
                seg_duration = max(1e-9, t1 - t0)
                if fps > 0 and total_frames > 0:
                    seg_len_frames = max(1, int(round(seg_duration * fps)))
                    idx_start = min(total_frames - 1, max(0, int(round(t0 * fps))))
                    idx_end = min(total_frames - 1, idx_start + seg_len_frames - 1)
                else:
                    idx_start, idx_end = 0, max(0, total_frames - 1)
                logger.info(
                    f"画中画片段: [{t0:.2f}s, {t1:.2f}s] → 帧索引 [{idx_start}, {idx_end}] "
                    f"(全片 {full_duration:.2f}s)"
                )
            else:
                idx_start = 0
                idx_end = max(0, total_frames - 1)
                seg_duration = full_duration
                logger.info(
                    f"视频信息: FPS={fps:.2f}, 总帧数={total_frames}, 时长={full_duration:.2f}秒"
                )

            segment_nframes = max(1, idx_end - idx_start + 1)

            if target_fps is not None and seg_duration > 0 and segment_nframes > 0:
                desired = min(
                    max_frames,
                    max(1, int(round(seg_duration * float(target_fps)))),
                )
                desired = min(desired, segment_nframes)
                span = idx_end - idx_start
                if desired <= 1:
                    index_list = [idx_start]
                else:
                    index_list = [
                        idx_start + min(span, int(round(i * span / (desired - 1))))
                        for i in range(desired)
                    ]
            else:
                # 无 target_fps：在片段内按间隔采样
                if segment_nframes <= max_frames:
                    interval = 1
                else:
                    interval = max(1, segment_nframes // max_frames)
                index_list = list(range(idx_start, idx_end + 1, interval))[:max_frames]
                if not index_list:
                    index_list = [idx_start]

            unique_need = sorted(set(index_list))
            want = set(unique_need)
            by_idx: Dict[int, np.ndarray] = {}
            frame_count = 0
            max_need = max(unique_need) if unique_need else 0

            # 顺序读到 idx_end，避免在全片范围内乱跳索引
            while frame_count <= max_need:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_count in want:
                    by_idx[frame_count] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_count += 1

            cap.release()
            frames = [by_idx[i] for i in index_list if i in by_idx]
            logger.info(f"✅ 成功提取 {len(frames)} 帧（片段内顺序采样）")
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
    def prepare_video_for_embedding(
        video_path: str,
        target_size: Tuple[int, int] = None,
        *,
        embed_fps: float = PIP_EMBED_FPS,
        max_source_frames: int = PIP_MAX_SOURCE_FRAMES,
        segment_duration_sec: Optional[float] = None,
        segment_start_sec: float = 0.0,
        source_duration_factor: float = PIP_SOURCE_DURATION_FACTOR,
    ) -> List[Image.Image]:
        """准备视频用于嵌入显示（保持原始比例）。
        segment_duration_sec 为成片中该段的目标时长；从源视频读取
        segment_duration_sec * source_duration_factor 秒内容再抽帧，
        后续仍按 segment_duration_sec 播放，相当于约 source_duration_factor 倍速。
        """
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
            
            read_sec = segment_duration_sec
            if segment_duration_sec is not None and float(source_duration_factor) > 1.0:
                read_sec = float(segment_duration_sec) * float(source_duration_factor)
                logger.info(
                    f"画中画源时长 {read_sec:.2f}s（成片 {segment_duration_sec:.2f}s × {source_duration_factor}），约 {source_duration_factor}× 快进"
                )
            # 先按读取窗口截取时间范围，再在该范围内按 embed_fps 顺序均匀采样
            frames = VideoEmbeddingService.extract_video_frames(
                video_path,
                max_frames=max_source_frames,
                target_fps=embed_fps,
                start_sec=segment_start_sec,
                duration_sec=read_sec,
            )
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
                                  title_info: tuple = None, summary_info: tuple = None,
                                  output_fps: float = PIP_EMBED_FPS,
                                  title_slide_entrance: bool = True) -> List[Image.Image]:
        """将视频帧融合到背景图像中，并添加文字"""
        try:
            logger.info(f"🎨 融合视频到背景: 位置={position}, 帧数={len(video_frames)}")
            
            result_frames = []
            n_vid = len(video_frames)
            if n_vid < 1:
                return []
            num_out = max(1, int(round(float(frame_duration) * float(output_fps))))
            
            # 为每个背景帧添加视频（输出帧率 output_fps，与素材采样一致）
            for i in range(num_out):
                # 复制背景
                bg_copy = background.copy()
                
                # 当前段内时间进度 0..1，映射到素材帧索引
                if num_out <= 1:
                    prog = 0.0
                else:
                    prog = i / (num_out - 1)
                if n_vid == 1:
                    video_frame_index = 0
                else:
                    video_frame_index = min(
                        n_vid - 1,
                        int(round(prog * (n_vid - 1))),
                    )
                video_frame = video_frames[video_frame_index]
                
                # 粘贴视频帧到背景（转换为RGB以避免通道冲突）
                if video_frame.mode != 'RGB':
                    video_frame = video_frame.convert('RGB')
                if bg_copy.mode != 'RGB':
                    bg_copy = bg_copy.convert('RGB')
                
                # 使用paste而不是alpha_composite（因为要去掉透明度）
                bg_copy.paste(video_frame, position)
                
                if title_info:
                    t_frame = (
                        (i / max(num_out - 1, 1)) * float(frame_duration)
                        if num_out > 1
                        else 0.0
                    )
                    bg_copy = VideoEmbeddingService._add_text_to_frame(
                        bg_copy, title_info, summary_info, t_frame,
                        title_slide_entrance=title_slide_entrance,
                    )
                
                result_frames.append(bg_copy)
            
            logger.info(f"✅ 融合完成: {len(result_frames)} 帧")
            return result_frames
            
        except Exception as e:
            logger.error(f"视频融合失败: {e}")
            return []
    
    @staticmethod
    def _add_text_to_frame(
        bg: Image.Image,
        title_info: tuple,
        summary_info: tuple = None,
        t: float = 0.0,
        *,
        title_slide_entrance: bool = True,
    ) -> Image.Image:
        """在帧上添加标题与可选摘要文字；主标题与副标题可自上方滑入（仅首段成片）。"""
        try:
            t_font, st_font, main_lines, sub_lines, title_y, main_h, margin, text_width = title_info
            img_width, img_height = bg.size
            
            from utils.video_utils import (
                _draw_text_overlay,
                _draw_subtitle_yellow_bar,
                MAIN_SUBTITLE_GAP_PX,
                compute_title_slide_offset_y,
                DEFAULT_TITLE_SLIDE_DURATION,
            )
            
            spx = max(80, min(200, int(img_height * 0.07)))
            if title_slide_entrance:
                off = compute_title_slide_offset_y(
                    t,
                    title_slide_delay=0.0,
                    title_slide_duration=DEFAULT_TITLE_SLIDE_DURATION,
                    slide_px=spx,
                )
            else:
                off = 0
            title_y_draw = title_y + off
            
            bg, _ = _draw_text_overlay(
                bg, main_lines, t_font, title_y_draw, img_width, margin, text_width,
                text_color=(255, 255, 255), glow_color=(102, 126, 234), line_spacing=18,
                background_top_y=0,
            )
            
            if sub_lines:
                sub_y = title_y_draw + main_h + MAIN_SUBTITLE_GAP_PX
                bg, _ = _draw_subtitle_yellow_bar(
                    bg, sub_lines, st_font, sub_y, img_width, margin, text_width,
                    line_spacing=14,
                )
            
            if summary_info and summary_info[1]:
                if len(summary_info) >= 4:
                    summary_font, summary_lines, summary_y, hi_kw = summary_info[:4]
                else:
                    summary_font, summary_lines, summary_y = summary_info[:3]
                    hi_kw = []
                bg, _ = _draw_text_overlay(
                    bg, summary_lines, summary_font, summary_y, img_width, margin, text_width,
                    text_color=(255, 255, 255), line_spacing=12, align="left",
                    highlight_keywords=hi_kw or None,
                    background_bottom_y=img_height,
                )
            
            return bg
            
        except Exception as e:
            logger.error(f"添加文字到帧失败: {e}")
            return bg
    
    @staticmethod
    def create_pip_video_effect(video_paths: List[str], background_template: Image.Image,
                              title_info: tuple, summary_info: tuple, 
                              duration_per_segment: float = 2.7,
                              title_slide_entrance: bool = True) -> Dict:
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
            
            # 整幅画布内居中：缩放框与静态图一致（左右各约 20px、上下各约 20px），再水平+垂直居中
            max_video_width = max(1, img_width - 40)
            max_video_height = max(1, img_height - 40)

            ow, oh = video_original_width, video_original_height
            if ow < 1 or oh < 1:
                ow, oh = 1920, 1080
            ar = ow / max(oh, 1)
            scale = min(max_video_width / ow, max_video_height / oh)
            video_width = max(1, int(ow * scale))
            video_height = max(1, int(oh * scale))
            if video_height > max_video_height:
                video_height = max_video_height
                video_width = max(1, int(round(video_height * ar)))
            if video_width > max_video_width:
                video_width = max_video_width
                video_height = max(1, int(round(video_width / ar)))

            logger.info(
                f"画中画尺寸: {video_width}x{video_height}，整幅画布居中"
            )

            video_x = (img_width - video_width) // 2
            video_y = max(0, (img_height - video_height) // 2)
            
            for idx, video_path in enumerate(video_paths, 1):
                try:
                    logger.info(f"处理视频 {idx}/{len(video_paths)}: {video_path}")
                    
                    # 准备视频帧（传递目标尺寸以保持比例）
                    video_frames = VideoEmbeddingService.prepare_video_for_embedding(
                        video_path,
                        (video_width, video_height),
                        segment_duration_sec=duration_per_segment,
                        segment_start_sec=0.0,
                    )
                    
                    if not video_frames:
                        logger.warning(f"跳过视频 {idx}: 无法处理视频文件")
                        continue
                    
                    # 创建该段的背景帧序列
                    segment_frames = VideoEmbeddingService.blend_video_into_background(
                        background_template,
                        video_frames,
                        (video_x, video_y),
                        duration_per_segment,
                        title_info,
                        summary_info,
                        output_fps=PIP_EMBED_FPS,
                        title_slide_entrance=(
                            title_slide_entrance and idx == 1
                        ),
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