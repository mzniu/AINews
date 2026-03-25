"""API 请求数据模型"""
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Union


class FetchRequest(BaseModel):
    """抓取 URL 请求"""
    url: HttpUrl


class FetchResponse(BaseModel):
    """抓取响应"""
    success: bool
    message: str
    data: Optional[dict] = None


class ImageWithDuration(BaseModel):
    """带时长的图片信息"""
    path: str
    duration: Optional[float] = None  # null 表示使用视频原始时长
    has_zoom: bool = True  # 是否启用放大效果
    zoom_start_scale: float = 1.0  # 起始缩放比例
    zoom_end_scale: float = 1.15   # 结束缩放比例


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
    duration_per_frame: float = 3.5
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
    # 支持两种格式：字符串数组（向后兼容）或带时长的对象数组
    images: List[Union[str, ImageWithDuration]] = []
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