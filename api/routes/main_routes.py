"""主要页面路由"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
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

@router.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "message": "服务运行正常"}