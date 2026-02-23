"""
GitHub项目处理主服务
整合所有子服务，提供统一的项目处理接口
"""
import asyncio
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

from src.models.github_models import (
    GitHubProjectRequest, ContentGenerationRequest,
    ProcessResult, ImageSelectionResponse, ContentGenerationResponse,
    GitHubProject, ProjectImage, VideoMetadata
)
from src.utils.github_parser import GitHubProjectParser
from services.github_image_service import ImageManager
from services.github_screenshot_service import (
    SyncGitHubScreenshotService, ScreenshotOptions
)
from services.github_storage_service import StorageConfig, ProjectStorageManager
from services.github_content_service import ContentAnalyzer


class GitHubProcessingService:
    """GitHub项目处理主服务"""
    
    def __init__(self, storage_path: Path = Path("data/github_projects")):
        # 初始化配置和服务
        self.storage_config = StorageConfig(storage_path)
        self.storage_manager = ProjectStorageManager(self.storage_config)
        self.parser = GitHubProjectParser()
        self.image_manager = ImageManager(self.storage_config.projects_dir)
        self.screenshot_service = SyncGitHubScreenshotService()
        self.content_analyzer = ContentAnalyzer()
        
        logger.info("GitHub处理服务初始化完成")
    
    async def process_project_async(self, request: GitHubProjectRequest) -> ProcessResult:
        """
        异步处理GitHub项目
        """
        start_time = time.time()
        
        try:
            logger.info(f"开始处理项目: {request.github_url}")
            
            # 1. 解析项目基本信息
            project_base = self.parser.parse_project(str(request.github_url))
            logger.info(f"项目基本信息解析完成: {project_base.name}")
            
            # 2. 获取README内容
            readme_content, readme_html = self.parser.api_client.get_readme(
                project_base.owner, 
                project_base.name,
                project_base.default_branch
            )
            project_base.readme_content = readme_content
            project_base.readme_html = readme_html
            logger.info("README内容获取完成")
            
            # 3. 提取README中的图片
            readme_images = self.parser.extract_readme_images(
                str(request.github_url), 
                readme_content
            )
            logger.info(f"提取到 {len(readme_images)} 张README图片")
            
            # 4. 截取项目主页截图
            screenshot_path = None
            if request.include_screenshots:
                screenshot_path = self._take_screenshot_async(
                    str(request.github_url), 
                    project_base.id,
                    request.screenshot_options
                )
                logger.info("项目截图完成" if screenshot_path else "项目截图失败")
            
            # 5. 下载处理图片
            downloaded_images = self.image_manager.download_project_images(
                project_base.id, 
                readme_images[:request.max_images]
            )
            logger.info(f"成功下载 {len(downloaded_images)} 张图片")
            
            # 6. 创建完整项目对象
            # 将截图也作为可选图片添加到项目中
            all_images = downloaded_images.copy()
            
            # 如果有截图，将其添加为项目图片
            if screenshot_path and screenshot_path.exists():
                # 创建截图图片对象
                screenshot_image = ProjectImage(
                    id="screenshot_001",
                    url="https://github.com/screenshot",  # 使用占位URL
                    local_path=screenshot_path,
                    source="screenshot",
                    alt_text="项目主页截图",
                    is_selected=False
                )
                all_images.append(screenshot_image)
                logger.info("截图已添加到可选图片列表")
            
            project = GitHubProject(
                **project_base.model_dump(),
                images=all_images,
                screenshot_path=screenshot_path,
                local_storage_path=self.storage_config.projects_dir / project_base.id
            )
            
            # 7. 保存到本地存储
            save_success = self.storage_manager.save_project(project)
            if not save_success:
                raise Exception("保存项目数据失败")
            
            processing_time = time.time() - start_time
            
            logger.info(f"项目处理完成: {project.id}, 耗时: {processing_time:.2f}秒")
            
            return ProcessResult(
                success=True,
                project_id=project.id,
                message="项目处理成功",
                project_info=project,
                processing_time=processing_time
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"项目处理失败: {e}")
            
            return ProcessResult(
                success=False,
                message=str(e),
                processing_time=processing_time
            )
    
    def _take_screenshot_async(self, 
                               github_url: str, 
                               project_id: str,
                               options: Optional[Dict[str, Any]] = None) -> Optional[Path]:
        """同步截图（避免asyncio嵌套问题）"""
        try:
            screenshot_dir = self.storage_config.projects_dir / project_id / "screenshots"
            screenshot_path = screenshot_dir / "project_homepage.jpg"
            
            screenshot_options = ScreenshotOptions(**(options or {}))
            
            # 使用同步接口避免event loop冲突
            success = self.screenshot_service.take_screenshot_sync(
                github_url, 
                screenshot_path, 
                screenshot_options
            )
            
            return screenshot_path if success else None
            
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None
    
    def list_projects(self) -> List[Dict[str, Any]]:
        """列出所有项目"""
        return self.storage_manager.list_projects()
    
    def get_project(self, project_id: str) -> Optional[GitHubProject]:
        """获取项目详情"""
        return self.storage_manager.load_project(project_id)
    
    def delete_project(self, project_id: str) -> bool:
        """删除项目"""
        return self.storage_manager.delete_project(project_id)
    
    def get_available_images(self, project_id: str) -> Optional[ImageSelectionResponse]:
        """获取可选图片"""
        project = self.storage_manager.load_project(project_id)
        if not project:
            return None
        
        selected_count = sum(1 for img in project.images if img.is_selected)
        
        return ImageSelectionResponse(
            project_id=project_id,
            available_images=project.images,
            total_count=len(project.images),
            selected_count=selected_count
        )
    
    def select_images(self, project_id: str, image_ids: List[str]) -> bool:
        """选择图片"""
        project = self.storage_manager.load_project(project_id)
        if not project:
            return False
        
        # 更新图片选择状态
        for image in project.images:
            image.is_selected = image.id in image_ids
        
        # 保存更新
        return self.storage_manager.save_project(project)
    
    async def generate_content_async(self, request: ContentGenerationRequest) -> ContentGenerationResponse:
        """异步生成内容"""
        try:
            # 获取项目信息
            project = self.storage_manager.load_project(request.project_id)
            if not project:
                return ContentGenerationResponse(
                    success=False,
                    project_id=request.project_id,
                    video_metadata=VideoMetadata(
                        title="", summary="", tags=[]
                    ),
                    processing_details={"error": "项目不存在"}
                )
            
            # 根据选择的图片过滤
            if request.selected_images:
                selected_images = [img for img in project.images if img.id in request.selected_images]
                project.images = selected_images
            
            # 生成内容
            video_metadata = self.content_analyzer.analyze_project_content(project)
            
            # 应用自定义内容（如果有）
            if request.custom_title:
                video_metadata.title = request.custom_title
            if request.custom_summary:
                video_metadata.summary = request.custom_summary
            
            # 保存生成的内容到项目
            project.video_metadata = video_metadata
            self.storage_manager.save_project(project)
            
            return ContentGenerationResponse(
                success=True,
                project_id=request.project_id,
                video_metadata=video_metadata,
                processing_details={
                    "generated_fields": ["title", "subtitle", "summary", "tags"],
                    "ai_generated": video_metadata.ai_generated
                }
            )
            
        except Exception as e:
            logger.error(f"内容生成失败: {e}")
            return ContentGenerationResponse(
                success=False,
                project_id=request.project_id,
                video_metadata=VideoMetadata(title="", summary="", tags=[]),
                processing_details={"error": str(e)}
            )
    
    def get_screenshot_path(self, project_id: str) -> Optional[Path]:
        """获取截图路径"""
        project = self.storage_manager.load_project(project_id)
        return project.screenshot_path if project else None
    
    def get_image_path(self, project_id: str, image_id: str) -> Optional[Path]:
        """获取图片路径"""
        project = self.storage_manager.load_project(project_id)
        if not project:
            return None
        
        for image in project.images:
            if image.id == image_id and image.local_path:
                return image.local_path
        
        return None
    
    def get_project_stats(self, project_id: str) -> Optional[Dict[str, Any]]:
        """获取项目统计信息"""
        return self.storage_manager.get_project_stats(project_id)
    
    def cleanup_temp_files(self, project_id: str):
        """清理临时文件"""
        try:
            self.image_manager.cleanup_failed_downloads(project_id)
            logger.info(f"项目 {project_id} 临时文件清理完成")
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")


# 同步接口包装
class SyncGitHubProcessingService:
    """同步接口包装器"""
    
    def __init__(self, storage_path: Path = Path("data/github_projects")):
        self.async_service = GitHubProcessingService(storage_path)
    
    def process_project(self, request: GitHubProjectRequest) -> ProcessResult:
        """同步处理项目"""
        return asyncio.run(self.async_service.process_project_async(request))
    
    def generate_content(self, request: ContentGenerationRequest) -> ContentGenerationResponse:
        """同步生成内容"""
        return asyncio.run(self.async_service.generate_content_async(request))


# 使用示例和测试
async def test_github_service():
    """测试GitHub服务"""
    service = GitHubProcessingService(Path("data/test_github"))
    
    # 测试项目处理
    request = GitHubProjectRequest(
        github_url="https://github.com/torvalds/linux",
        include_screenshots=False,
        max_images=5
    )
    
    result = await service.process_project_async(request)
    print(f"处理结果: {result.success}")
    if result.success:
        print(f"项目ID: {result.project_id}")
        print(f"处理耗时: {result.processing_time:.2f}秒")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_github_service())