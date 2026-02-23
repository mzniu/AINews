"""主要页面路由"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from pathlib import Path
from datetime import datetime
from loguru import logger
import os

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def root():
    """主页"""
    with open(os.path.join("static", "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@router.get("/video-maker", response_class=HTMLResponse)
async def video_maker_page():
    """视频制作页面"""
    with open(os.path.join("static", "video_maker.html"), "r", encoding="utf-8") as f:
        return f.read()

@router.get("/github-video-maker", response_class=HTMLResponse)
async def github_video_maker_page():
    """GitHub项目视频制作页面"""
    with open(os.path.join("static", "github_video_maker.html"), "r", encoding="utf-8") as f:
        return f.read()

@router.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "message": "服务运行正常"}

@router.post("/upload-local-image")
async def upload_local_image(image: UploadFile = File(...)):
    """上传单个本地图片文件"""
    try:
        # 验证文件类型
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp']
        if image.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="不支持的图片格式")
        
        # 验证文件大小（10MB限制）
        content = await image.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=400, detail="文件大小超过10MB限制")
        
        # 重置文件指针
        await image.seek(0)
        
        # 创建上传目录
        upload_dir = Path("data/local_uploads") / datetime.now().strftime("%Y%m%d")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        import uuid
        file_extension = Path(image.filename).suffix if image.filename else ".jpg"
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # 返回相对路径
        relative_path = str(file_path.relative_to(Path("."))).replace("\\", "/")
        image_path = f"/{relative_path}"
        
        logger.info(f"本地图片上传成功: {image.filename} -> {image_path}")
        
        return {
            "success": True,
            "message": "图片上传成功",
            "image_path": image_path,
            "filename": image.filename,
            "size": len(content)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"本地图片上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")