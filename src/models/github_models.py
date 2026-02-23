"""
GitHub项目数据模型
定义GitHub项目相关信息的数据结构
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, HttpUrl, model_validator
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


class VideoMetadata(BaseModel):
    """视频元数据"""
    title: str
    subtitle: Optional[str] = None
    summary: str
    tags: List[str]
    ai_generated: bool = True
    confidence_score: Optional[float] = None


class GitHubProject(GitHubProjectBase):
    """完整的GitHub项目信息"""
    images: List[ProjectImage] = []
    screenshot_path: Optional[Path] = None
    video_metadata: Optional[VideoMetadata] = None
    local_storage_path: Optional[Path] = None


class GitHubProjectRequest(BaseModel):
    """处理GitHub项目的请求"""
    github_url: HttpUrl
    include_screenshots: bool = True
    max_images: int = 20
    screenshot_options: Optional[Dict[str, Any]] = None


class ContentGenerationRequest(BaseModel):
    """内容生成请求"""
    project_id: str
    selected_images: List[str]  # 图片ID列表
    custom_title: Optional[str] = None
    custom_summary: Optional[str] = None
    target_language: str = "zh-CN"
    style_preference: Optional[str] = None  # "technical", "casual", "marketing"


class GitHubVideoGenerationRequest(BaseModel):
    """GitHub视频生成请求"""
    # 项目标识（二选一）
    project_id: Optional[str] = None
    github_url: Optional[str] = None
    
    # 处理选项（仅在提供github_url时使用）
    include_screenshots: bool = True
    include_audio: bool = True  # 是否添加背景音乐
    max_images: int = 10
    
    # 自定义内容（可选）
    custom_title: Optional[str] = None
    custom_summary: Optional[str] = None
    
    # 视频选项
    clip_duration: float = 3.0
    effect: str = "none"  # none/gold_sparkle/snowfall/bokeh/firefly/bubble
    
    @model_validator(mode='after')
    def check_project_identifier(self) -> 'GitHubVideoGenerationRequest':
        if not self.project_id and not self.github_url:
            raise ValueError('必须提供project_id或github_url之一')
        return self


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
    total_count: int
    selected_count: int


class ContentGenerationResponse(BaseModel):
    """内容生成响应"""
    success: bool
    project_id: str
    video_metadata: VideoMetadata
    processing_details: Optional[Dict[str, Any]] = None