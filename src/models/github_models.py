"""
GitHub项目数据模型
定义GitHub项目相关信息的数据结构
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, model_validator
from pathlib import Path


class GitHubProjectBase(BaseModel):
    """GitHub项目基础信息"""
    id: str
    url: HttpUrl
    name: str
    full_name: str
    description: Optional[str] = None
    language: Optional[str] = None
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    created_at: datetime
    updated_at: datetime
    owner: str
    default_branch: str = "main"
    readme_content: Optional[str] = None
    readme_html: Optional[str] = None


class ProjectImage(BaseModel):
    """项目图片信息"""
    id: str
    url: HttpUrl
    local_path: Optional[Path] = None
    source: str  # "readme" or "screenshot"
    width: Optional[int] = None
    height: Optional[int] = None
    size: Optional[int] = None
    alt_text: Optional[str] = None
    is_selected: bool = False


class ProjectVideo(BaseModel):
    """README 等来源的内嵌视频（可参与成片，作为画中画片段）"""
    id: str
    url: HttpUrl
    local_path: Optional[Path] = None
    source: str = "readme"  # readme
    alt_text: Optional[str] = None
    is_selected: bool = False
    size: Optional[int] = None


class VideoMetadata(BaseModel):
    """视频元数据"""
    title: str
    subtitle: Optional[str] = None
    subtitle2: Optional[str] = None  # 副标题第二行：流量钩子（11-15 汉字当量）
    summary: str
    tags: List[str]
    ai_generated: bool = True
    confidence_score: Optional[float] = None
    # 社交货币方法论：LLM 推断回显（用户不输入）
    target_audience: Optional[str] = None
    praise_tags: Optional[List[str]] = None
    traffic_hook: Optional[str] = None  # 流量钩子类型中文名，如「观众想看结果」


class GitHubProject(GitHubProjectBase):
    """完整的GitHub项目信息"""
    images: List[ProjectImage] = []
    videos: List[ProjectVideo] = []
    screenshot_path: Optional[Path] = None
    video_metadata: Optional[VideoMetadata] = None
    local_storage_path: Optional[Path] = None


class GitHubProjectRequest(BaseModel):
    """处理GitHub项目的请求"""
    github_url: HttpUrl
    include_screenshots: bool = True
    max_images: int = 20
    max_videos: int = 5
    screenshot_options: Optional[Dict[str, Any]] = None


class ContentGenerationRequest(BaseModel):
    """内容生成请求"""
    project_id: str
    selected_images: List[str]  # 图片ID列表
    custom_title: Optional[str] = None
    custom_summary: Optional[str] = None
    target_language: str = "zh-CN"
    style_preference: Optional[str] = None  # "technical", "casual", "marketing"


class GitHubImageClip(BaseModel):
    """GitHub 成片：单张图片 id 与片段时长（秒）"""
    id: str
    duration: float = 3.0


class GitHubVoiceoverRequest(BaseModel):
    """第五步：为基底视频生成 TTS 配音与字幕"""
    base_video_path: str  # 如 /data/videos/animated_xxx.mp4
    script: str
    voice: str = "zh-CN-XiaoxiaoNeural"
    voice_clone_audio_path: Optional[str] = None  # IndexTTS 参考音频路径（/data/voice_clones/*.wav 等）
    mix_bgm: bool = True
    # 混音时相对增益（dB）：BGM 多为负数以压低伴奏；人声 0 为 TTS 原始电平
    bgm_gain_db: float = Field(default=-22.0, ge=-45.0, le=6.0)
    narration_gain_db: float = Field(default=0.0, ge=-24.0, le=24.0)
    burn_subtitles: bool = True
    # IndexTTS 输出后的语速调整，如 +25% 表示加快（默认略快于默认朗读）
    tts_rate: str = "+25%"
    # FFmpeg 烧录字幕（与 libass FontName 一致，须为本机已安装字体名）
    subtitle_fontname: str = Field(default="Microsoft YaHei", max_length=80)
    subtitle_fontsize: int = Field(default=16, ge=10, le=36)
    # 字幕底边距：占画面高度的百分比，越大离画面底边越远（ASS MarginV）
    subtitle_margin_bottom_percent: float = Field(default=11.0, ge=8.0, le=45.0)
    # 字幕左边距：占画面宽度的百分比，用于调整字幕文本区域的左侧位置（ASS MarginL）
    subtitle_margin_left_percent: float = Field(default=4.5, ge=0.0, le=45.0)
    # 每条字幕约多少字（与 TTS 分段一致）
    subtitle_max_chars: int = Field(default=20, ge=8, le=40)


class GitHubVoiceoverResponse(BaseModel):
    success: bool
    message: str = ""
    final_video_path: Optional[str] = None
    srt_path: Optional[str] = None
    tts_audio_path: Optional[str] = None


class GitHubVideoGenerationRequest(BaseModel):
    """GitHub视频生成请求"""
    # 项目标识（二选一）
    project_id: Optional[str] = None
    github_url: Optional[str] = None
    
    # 处理选项（仅在提供github_url时使用）
    include_screenshots: bool = True
    include_audio: bool = True  # 是否添加背景音乐
    audio_path: Optional[str] = None  # 背景音乐文件路径（如 static/music/xxx.mp3），与主页一致
    background_image_path: Optional[str] = None  # 成片背景图（须为 static/ 下路径，如 static/imgs/bg.png）
    max_images: int = 10
    max_videos: int = 5
    
    # 自定义内容（可选）
    custom_title: Optional[str] = None
    custom_summary: Optional[str] = None
    # 第三步编辑：主标题两行（若任一有值则优先于从 title 自动拆分）
    custom_main_line1: Optional[str] = None
    custom_main_line2: Optional[str] = None
    custom_subtitle2: Optional[str] = None  # 副标题第二行（流量钩子）覆盖；为空则沿用 AI 生成值
    title_font_key: Optional[str] = None  # 主标题字体，见 GET /api/list-title-fonts
    
    # 已选图片顺序与每段时长（与前端排序面板一致）；为空则按仓库内全部图片顺序
    image_sequence: Optional[List[GitHubImageClip]] = None
    
    # 视频选项
    clip_duration: float = 3.0
    effect: str = "none"  # none/gold_sparkle/snowfall/bokeh/firefly/bubble
    
    @model_validator(mode='after')
    def check_project_identifier(self) -> 'GitHubVideoGenerationRequest':
        if not self.project_id and not self.github_url:
            raise ValueError('必须提供project_id或github_url之一')
        return self


class GitHubLocalCacheLookup(BaseModel):
    """检查本地是否已有该仓库的下载数据（与 process-project 使用的 project_id 一致）"""

    cached: bool
    project_id: Optional[str] = None


class ProcessResult(BaseModel):
    """处理结果"""
    success: bool
    project_id: Optional[str] = None
    message: str
    project_info: Optional[GitHubProject] = None
    processing_time: Optional[float] = None


class ImageSelectionResponse(BaseModel):
    """图片选择响应"""
    project_id: str
    available_images: List[ProjectImage]
    available_videos: List[ProjectVideo] = []
    total_count: int
    selected_count: int


class SelectAssetsRequest(BaseModel):
    """步骤二：勾选图片与 README 视频"""
    image_ids: List[str] = []
    video_ids: List[str] = []


class ContentGenerationResponse(BaseModel):
    """内容生成响应"""
    success: bool
    project_id: str
    video_metadata: VideoMetadata
    processing_details: Optional[Dict[str, Any]] = None