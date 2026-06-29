#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GIF处理API路由
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import asyncio
import json
import logging
from typing import List, Optional

from services.gif_processor import gif_processor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gif", tags=["GIF Processing"])

@router.post("/process-gif")
async def process_gif_for_video(
    gif_path: str = Form(...),
    target_duration: float = Form(...),
    output_dir: str = Form("data/temp_videos")
):
    """处理GIF用于视频生成"""
    try:
        logger.info(f"处理 GIF/WebP: {gif_path}, 目标时长: {target_duration}秒")
        
        if not gif_processor.is_convertible_to_mp4_animation(gif_path):
            raise HTTPException(status_code=400, detail="仅支持 .gif 或 .webp")

        analysis = {}
        if gif_processor.is_gif_file(gif_path):
            analysis = gif_processor.analyze_gif_compatibility(gif_path)
            if not analysis.get("is_valid"):
                logger.warning(f"GIF兼容性问题: {analysis.get('issues')}")
        
        # 处理GIF转换
        result_path = await asyncio.to_thread(
            gif_processor.process_gif_for_video,
            gif_path=gif_path,
            target_duration=target_duration,
            output_dir=output_dir,
        )
        
        if result_path:
            return {
                "success": True,
                "video_path": result_path,
                "message": "GIF/WebP 处理成功",
                "gif_analysis": analysis
            }
        else:
            raise HTTPException(status_code=500, detail="GIF处理失败")
            
    except Exception as e:
        logger.error(f"GIF处理错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch-process-gifs")
async def batch_process_gifs(
    gif_paths: List[str] = Form(...),
    target_duration: float = Form(...),
    output_dir: str = Form("data/temp_videos")
):
    """批量处理多个 GIF 或 WebP（转 MP4 片段）"""
    try:
        logger.info(
            "POST /api/gif/batch-process-gifs: %d 个 GIF/WebP → MP4, target_duration=%.2fs, output_dir=%s",
            len(gif_paths),
            target_duration,
            output_dir,
        )

        async def _process_one(gif_path: str):
            try:
                if not gif_processor.is_convertible_to_mp4_animation(gif_path):
                    return {
                        "original_path": gif_path,
                        "status": "failed",
                        "error": "仅支持 .gif 或 .webp",
                    }
                result = await asyncio.to_thread(
                    gif_processor.process_gif_for_video,
                    gif_path=gif_path,
                    target_duration=target_duration,
                    output_dir=output_dir,
                )
                if result:
                    return {
                        "original_path": gif_path,
                        "video_path": result,
                        "status": "success",
                    }
                return {
                    "original_path": gif_path,
                    "status": "failed",
                    "error": "转换失败",
                }
            except Exception as e:
                return {
                    "original_path": gif_path,
                    "status": "failed",
                    "error": str(e),
                }

        # 并发处理所有 GIF（每个在独立线程，避免阻塞 event loop）
        results = await asyncio.gather(*[_process_one(p) for p in gif_paths])
        results = list(results)
        failed_count = sum(1 for r in results if r.get("status") != "success")

        return {
            "success": True,
            "results": results,
            "total_processed": len(gif_paths),
            "successful": len(gif_paths) - failed_count,
            "failed": failed_count
        }
        
    except Exception as e:
        logger.error(f"批量GIF处理错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analyze-gif")
async def analyze_gif(gif_path: str):
    """分析GIF文件属性和兼容性"""
    try:
        if not Path(gif_path).exists():
            raise HTTPException(status_code=404, detail="GIF文件不存在")
        
        if not gif_processor.is_gif_file(gif_path):
            raise HTTPException(status_code=400, detail="不是GIF文件")
        
        # 获取详细信息
        properties = gif_processor.get_gif_properties(gif_path)
        analysis = gif_processor.analyze_gif_compatibility(gif_path)
        
        return {
            "success": True,
            "properties": properties,
            "analysis": analysis,
            "is_animated": properties.get('frame_count', 0) > 1
        }
        
    except Exception as e:
        logger.error(f"GIF分析错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/extract-frames")
async def extract_gif_frames(gif_path: str, max_frames: Optional[int] = 50):
    """提取GIF帧用于预览"""
    try:
        if not Path(gif_path).exists():
            raise HTTPException(status_code=404, detail="GIF文件不存在")
        
        frames = gif_processor.extract_gif_frames(gif_path)
        
        if not frames:
            raise HTTPException(status_code=400, detail="无法提取GIF帧")
        
        # 限制返回帧数
        if max_frames and len(frames) > max_frames:
            # 均匀采样
            import numpy as np
            indices = np.linspace(0, len(frames) - 1, max_frames, dtype=int)
            frames = [frames[i] for i in indices]
        
        # 转换为base64用于前端显示（简化版本）
        frame_info = []
        for i, frame in enumerate(frames[:10]):  # 只返回前10帧作为预览
            frame_info.append({
                "frame_index": i,
                "shape": frame.shape if hasattr(frame, 'shape') else 'unknown'
            })
        
        return {
            "success": True,
            "total_frames": len(frames),
            "preview_frames": frame_info,
            "message": f"提取了 {min(len(frames), 10)} 帧用于预览"
        }
        
    except Exception as e:
        logger.error(f"GIF帧提取错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))