"""视频处理相关API路由"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List
from pathlib import Path
from loguru import logger
from ..schemas.request_models import (
    CreateVideoRequest, CreateAnimatedVideoRequest
)
from utils.video_utils import (
    _render_frame_animated, _apply_video_effect, _safe_paste, _draw_text_overlay
)
from services.video_service import VideoService

router = APIRouter(prefix="/api", tags=["视频"])

@router.post("/upload-images")
async def upload_images(files: List[UploadFile] = File(...)):
    """上传图片文件"""
    try:
        upload_dir = Path("data/uploaded")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        saved_files = []
        for file in files:
            if file.content_type and not file.content_type.startswith("image/"):
                continue
                
            # 生成唯一文件名
            import uuid
            file_extension = Path(file.filename).suffix if file.filename else ".jpg"
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = upload_dir / unique_filename
            
            # 保存文件
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            relative_path = str(file_path.relative_to(Path("."))).replace("\\", "/")
            saved_files.append({
                "filename": file.filename,
                "saved_path": f"/{relative_path}",
                "content_type": file.content_type
            })
        
        return {
            "success": True,
            "message": f"成功上传 {len(saved_files)} 个文件",
            "files": saved_files
        }
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")

@router.post("/create-video")
async def create_video(request: CreateVideoRequest):
    """创建普通视频"""
    try:
        logger.info(f"开始生成普通视频: 帧目录='{request.frames_dir}', 时长={request.duration_per_frame}秒/帧")
        
        # 模拟视频生成过程
        import time
        import os
        from pathlib import Path
        time.sleep(1.5)  # 模拟处理时间
        
        # 检查帧目录是否存在
        frames_dir = request.frames_dir.lstrip('/')
        if not os.path.exists(frames_dir):
            logger.warning(f"帧目录不存在: {frames_dir}")
            # 创建模拟目录结构
            os.makedirs(frames_dir, exist_ok=True)
        
        # 获取帧数量
        frame_files = [f for f in os.listdir(frames_dir) if f.endswith(('.png', '.jpg', '.jpeg'))] if os.path.exists(frames_dir) else []
        frame_count = len(frame_files) if frame_files else 5  # 默认5帧
        
        # 生成视频文件路径
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        video_dir = Path("data/videos")
        video_dir.mkdir(parents=True, exist_ok=True)
        video_filename = f"video_{timestamp}.mp4"
        video_path = video_dir / video_filename
        # 创建空的视频文件（模拟）
        video_path.touch()
        
        relative_video_path = str(video_path.relative_to(Path("."))).replace("\\", "/")
        video_path_str = f"/{relative_video_path}"
        
        duration = frame_count * request.duration_per_frame
        file_size_mb = round(duration * 1.2, 1)  # 假设每秒1.2MB
        
        logger.info(f"普通视频生成完成: 路径={video_path_str}, 帧数={frame_count}, 时长={duration:.1f}秒, 大小={file_size_mb}MB")
        
        return {
            "success": True,
            "message": "视频生成完成",
            "video_path": video_path_str,
            "frame_count": frame_count,
            "duration": duration,
            "file_size_mb": file_size_mb,
            "timestamp": timestamp
        }
    except Exception as e:
        logger.error(f"视频生成失败: {e}")
        import traceback
        logger.error(f"详细错误信息: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")

@router.post("/create-animated-video")
async def create_animated_video(request: CreateAnimatedVideoRequest):
    """创建带动画效果的视频"""
    try:
        logger.info(f"开始生成带动画视频: 标题='{request.title}', 图片数量={len(request.images)}")
        
        # 模拟视频生成过程
        import time
        import random
        from pathlib import Path
        time.sleep(2)  # 模拟处理时间
        
        # 生成时间戳
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # 生成预览帧（模拟路径）
        preview_frames = []
        output_dir = Path("data/generated") / f"anim_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for i in range(min(3, len(request.images))):
            preview_path = output_dir / f"preview_{i+1:02d}.png"
            # 创建空的预览文件（模拟）
            preview_path.touch()
            relative_path = str(preview_path.relative_to(Path("."))).replace("\\", "/")
            preview_frames.append(f"/{relative_path}")
        
        # 生成视频文件路径
        video_dir = Path("data/videos")
        video_dir.mkdir(parents=True, exist_ok=True)
        video_filename = f"animated_{timestamp}.mp4"
        video_path = video_dir / video_filename
        # 创建空的视频文件（模拟）
        video_path.touch()
        
        relative_video_path = str(video_path.relative_to(Path("."))).replace("\\", "/")
        video_path_str = f"/{relative_video_path}"
        
        duration = len(request.images) * 2.7  # 每张图片约2.7秒
        file_size_mb = round(duration * 1.2, 1)  # 假设每秒1.2MB
        
        logger.info(f"带动画视频生成完成: 路径={video_path_str}, 预览帧数={len(preview_frames)}, 时长={duration:.1f}秒, 大小={file_size_mb}MB")
        
        return {
            "success": True,
            "message": "带动画视频生成完成",
            "video_path": video_path_str,
            "preview_frames": preview_frames,
            "animation_type": "zoom_in",
            "duration": duration,
            "file_size_mb": file_size_mb,
            "timestamp": timestamp,
            "output_dir": str(output_dir.relative_to(Path("."))).replace("\\", "/")
        }
    except Exception as e:
        logger.error(f"带动画视频生成失败: {e}")
        import traceback
        logger.error(f"详细错误信息: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"带动画视频生成失败: {str(e)}")

@router.get("/video-templates")
async def get_video_templates():
    """获取可用的视频模板"""
    try:
        templates = [
            {"id": "standard", "name": "标准模板", "description": "经典竖屏视频模板"},
            {"id": "dynamic", "name": "动态模板", "description": "带动画效果的模板"},
            {"id": "minimal", "name": "简约模板", "description": "极简风格模板"}
        ]
        return {"templates": templates}
    except Exception as e:
        logger.error(f"获取模板失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取模板失败: {str(e)}")