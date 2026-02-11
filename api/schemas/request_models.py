"""API请求数据模型"""
from pydantic import BaseModel, HttpUrl
from typing import List, Optional


class FetchRequest(BaseModel):
    """抓取URL请求"""
    url: HttpUrl


class FetchResponse(BaseModel):
    """抓取响应"""
    success: bool
    message: str
    data: Optional[dict] = None


class GenerateSummaryRequest(BaseModel):
    """生成AI摘要请求"""
    content: str
    images: List[str] = []
    title: str = ""


class GenerateImageRequest(BaseModel):
    """生成视频关键帧请求"""
    title: str
    summary: str
    images: List[str] = []


class ProcessImageRequest(BaseModel):
    """处理图片请求"""
    image_path: str
    effect: str = "enhance"


class CreateVideoRequest(BaseModel):
    """创建视频请求"""
    frames_dir: str
    duration_per_frame: float = 2.5
    audio_path: str = ""


class RemoveWatermarkRequest(BaseModel):
    """去除水印请求"""
    image_path: str
    regions: List[dict] = []  # [{x, y, width, height}, ...]


class DetectWatermarkRequest(BaseModel):
    """检测水印请求"""
    image_path: str


class CreateAnimatedVideoRequest(BaseModel):
    """创建带动画视频请求"""
    title: str
    summary: str
    images: List[str] = []
    audio_path: str = ""


class CreateUserVideoRequest(BaseModel):
    """创建用户自定义视频请求"""
    title: str = ""
    subtitle: str = ""
    images: List[str] = []  # JSON array string of image paths
    audio_path: str = "static/music/background.mp3"
    clip_duration: float = 3.0
    effect: str = "none"  # none/gold_sparkle/snowfall/bokeh/firefly/bubble


class UploadImagesRequest(BaseModel):
    """上传图片请求"""
    pass  # 文件上传使用Form数据，这里只是占位