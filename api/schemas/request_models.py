"""API 请求数据模型"""
from pydantic import BaseModel, Field, HttpUrl, model_validator
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
    zoom_end_scale: float = 1.08   # 结束缩放比例（较轻微放大）


class GenerateSummaryRequest(BaseModel):
    """生成AI摘要请求"""
    content: str
    images: List[str] = []
    title: str = ""
    voiceover_min_chars: int = Field(default=120, ge=20, le=4000)
    voiceover_max_chars: int = Field(default=400, ge=20, le=8000)

    @model_validator(mode="after")
    def normalize_voiceover_range(self):
        if self.voiceover_min_chars > self.voiceover_max_chars:
            self.voiceover_min_chars, self.voiceover_max_chars = (
                self.voiceover_max_chars,
                self.voiceover_min_chars,
            )
        return self


class GenerateImageRequest(BaseModel):
    """生成视频关键帧请求"""
    summary: str
    images: List[str] = []
    title: str = ""
    main_line1: str = ""
    main_line2: str = ""
    subtitle: str = ""
    title_font_key: Optional[str] = None  # 与 create-animated-video 一致，见 /api/list-title-fonts


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
    summary: str
    # 支持两种格式：字符串数组（向后兼容）或带时长的对象数组
    images: List[Union[str, ImageWithDuration]] = []
    audio_path: str = ""
    title: str = ""  # 向后兼容：旧版 main|副标题，整段主标题会参与自动换行
    main_line1: str = ""  # 主标题第一行，14～18 汉字当量，单行绘制
    main_line2: str = ""  # 主标题第二行，16～20 汉字当量，单行绘制
    subtitle: str = ""  # 副标题，14～16 汉字当量，单行
    show_summary: bool = True  # False：画面上不绘制摘要（口播在后续步骤）
    # block：整块摘要自下而上；line_uniform：方案 A，在 [入场, 成片结束] 内均分时段逐行上滑
    summary_scroll_mode: str = "line_uniform"
    background_image_path: Optional[str] = None  # 成片背景图，须为 static/ 下可访问路径
    title_font_key: Optional[str] = None  # 主标题字体预设，见 /api/list-title-fonts
    first_image_effect: Optional[str] = None  # GitHub页可用：side_flip_rounded，将第一张静态图做30度侧翻圆角卡片并渐进放大
    # 摘要高亮：在「标签」串中解析 #词；或直接使用下列词在摘要中匹配着色（长词优先；服务端会收束为每词≤5字）
    tags: Optional[str] = None
    summary_highlight_keywords: Optional[List[str]] = None


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


class SearchImagesRequest(BaseModel):
    """网页搜图（开发用：百度图片 acjson）"""
    query: str = Field(..., min_length=1, max_length=200)
    engine: str = Field(default="baidu")
    page: int = Field(default=0, ge=0, le=50)
    page_size: int = Field(default=20, ge=1, le=60)


class ImportRemoteImageRequest(BaseModel):
    """将远程图片 URL 下载到 data/local_uploads，供选图与成片使用"""
    url: str = Field(..., min_length=8, max_length=4096)
    referer: Optional[str] = None


class RelatedImageCrawlRequest(BaseModel):
    """基于当前文章调用大模型生成搜索词，并抓取相关网页图片"""
    title: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=50000)
    source_url: str = Field(default="", max_length=4096)
    query: Optional[str] = Field(default=None, max_length=200)
    search_sources: List[str] = Field(default_factory=lambda: ["baidu", "bing", "toutiao"])
    # 每个搜索源搜索几页，而不是总共打开几页
    max_pages: int = Field(default=5, ge=1, le=10)
    # 防止多源多页时一次打开过多候选网页；前端暂不暴露
    max_crawl_pages: int = Field(default=18, ge=1, le=60)
    max_images_per_page: int = Field(default=6, ge=1, le=12)


class GenerateCoverImageRequest(BaseModel):
    """根据正文生成封面图（Seedance/火山 Ark 文生图）"""
    content: str = Field(default="", max_length=50000)
    title: str = Field(default="", max_length=500)
    prompt: Optional[str] = None  # 若填写则完全作为生图 prompt，忽略自动拼接
    extra_hint: Optional[str] = Field(default=None, max_length=500)  # 追加到自动 prompt