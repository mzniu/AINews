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
        # 这里实现视频生成功能
        # 需要引入moviepy或其他视频处理库
        return {
            "success": True,
            "message": "视频生成完成",
            "video_path": "/path/to/generated/video.mp4",
            "duration": 30.0
        }
    except Exception as e:
        logger.error(f"视频生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")

@router.post("/create-animated-video")
async def create_animated_video(request: CreateAnimatedVideoRequest):
    """创建带动画效果的视频"""
    try:
        # 这里实现带动画的视频生成功能
        return {
            "success": True,
            "message": "带动画视频生成完成",
            "video_path": "/path/to/generated/animated_video.mp4",
            "animation_type": "zoom_in",
            "duration": 30.0
        }
    except Exception as e:
        logger.error(f"带动画视频生成失败: {e}")
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