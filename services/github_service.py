"""
GitHub项目处理主服务
整合所有子服务，提供统一的项目处理接口
"""
import asyncio
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import quote
from urllib.parse import urlparse
from PIL import Image, ImageChops
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
from utils.title_units import format_main_title_two_lines


class GitHubProcessingService:
    """GitHub项目处理主服务"""

    STAR_HISTORY_IMAGE_ID = "star_history"
    
    def __init__(self, storage_path: Path = Path("data/github_projects")):
        # 初始化配置和服务
        self.storage_config = StorageConfig(storage_path)
        self.storage_manager = ProjectStorageManager(self.storage_config)
        self.parser = GitHubProjectParser()
        self.image_manager = ImageManager(self.storage_config.projects_dir)
        self.screenshot_service = SyncGitHubScreenshotService()
        self.content_analyzer = ContentAnalyzer()
        
        logger.info("GitHub处理服务初始化完成")
    
    def _process_project_sync(self, request: GitHubProjectRequest) -> ProcessResult:
        """
        同步处理 GitHub 项目（网络/磁盘密集）。
        由 process_project_async 放入线程池执行，避免阻塞 ASGI 事件循环。
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
                readme_content,
                project_base.default_branch,
                readme_html,
            )
            logger.info(f"提取到 {len(readme_images)} 张README图片")

            readme_videos = self.parser.extract_readme_videos(
                str(request.github_url),
                readme_content,
                project_base.default_branch,
                readme_html,
            )[: request.max_videos]
            logger.info(f"提取到 {len(readme_videos)} 个 README 视频（上限 {request.max_videos}）")
            
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
            readme_images = self._prioritize_readme_images(readme_images)
            downloaded_images = self.image_manager.download_project_images(
                project_base.id, 
                readme_images[:request.max_images]
            )
            logger.info(f"成功下载 {len(downloaded_images)} 张图片")

            downloaded_videos = self.image_manager.download_project_videos(
                project_base.id,
                readme_videos,
            )
            logger.info(f"成功下载 {len(downloaded_videos)} 个 README 视频")
            
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
                videos=downloaded_videos,
                screenshot_path=screenshot_path,
                local_storage_path=self.storage_config.projects_dir / project_base.id
            )

            # 7. 生成 Star History 曲线图，作为可选素材加入图片列表
            self._ensure_star_history_image_in_project(project)
            
            # 8. 保存到本地存储
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

    async def process_project_async(self, request: GitHubProjectRequest) -> ProcessResult:
        """与并发 HTTP 请求并行：实际处理在线程池中运行。"""
        return await asyncio.to_thread(self._process_project_sync, request)

    def _refresh_project_homepage_screenshot_sync(
        self,
        project_id: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """
        仅重新截取 GitHub 项目主页截图并写回 metadata（不重新拉取 README/图片）。
        用于首次截图失败或需更新主页画面时单独重试。
        """
        project = self.storage_manager.load_project(project_id)
        if not project:
            return False, "项目不存在"
        github_url = str(project.url).strip()
        if not github_url:
            return False, "项目缺少仓库 URL"

        screenshot_path = self._take_screenshot_async(
            github_url, project_id, options
        )
        if not screenshot_path or not screenshot_path.exists():
            self._strip_stale_homepage_screenshot(project_id)
            return (
                False,
                "主页截图未成功（真实浏览器未截取到页面）。"
                "常见原因：未安装 Playwright 浏览器，请在项目目录执行 playwright install chromium；"
                "或网络无法访问 GitHub。若仅需占位图可设置环境变量 GITHUB_SCREENSHOT_ALLOW_FALLBACK=1。",
            )

        project.screenshot_path = screenshot_path
        found = False
        for img in project.images:
            if img.id == "screenshot_001":
                img.local_path = screenshot_path
                img.source = "screenshot"
                found = True
                break
        if not found:
            project.images.append(
                ProjectImage(
                    id="screenshot_001",
                    url="https://github.com/screenshot",
                    local_path=screenshot_path,
                    source="screenshot",
                    alt_text="项目主页截图",
                    is_selected=False,
                )
            )

        if not self.storage_manager.save_project(project):
            return False, "保存项目数据失败"
        logger.info(f"项目 {project_id} 主页截图已单独更新: {screenshot_path}")
        return True, "主页截图已更新"

    def _strip_stale_homepage_screenshot(self, project_id: str) -> None:
        """删除磁盘上的旧主页截图并从元数据移除 screenshot_001，避免列表仍显示历史占位图。"""
        shot = (
            self.storage_config.projects_dir
            / project_id
            / "screenshots"
            / "project_homepage.jpg"
        )
        if shot.is_file():
            try:
                shot.unlink()
                logger.info(f"已删除无效/过期的主页截图文件: {shot}")
            except OSError as e:
                logger.warning(f"删除旧截图失败: {e}")
        project = self.storage_manager.load_project(project_id)
        if not project:
            return
        project.images = [img for img in project.images if img.id != "screenshot_001"]
        project.screenshot_path = None
        self.storage_manager.save_project(project)

    async def refresh_project_homepage_screenshot_async(
        self,
        project_id: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        return await asyncio.to_thread(
            self._refresh_project_homepage_screenshot_sync, project_id, options
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

    def find_cached_project_id(self, github_url: str) -> Optional[str]:
        """
        根据仓库 URL 解析 owner/repo，若本地已存在该项目的 metadata.json 则返回 project_id。
        不调用 GitHub API，仅用于判断是否已有「已下载」的本地数据。
        """
        try:
            from src.utils.github_parser import GitHubUrlParser

            info = GitHubUrlParser.parse_github_url(str(github_url).strip())
            pid = f"{info['owner']}_{info['repo']}"
            meta = self.storage_config.projects_dir / pid / self.storage_manager.metadata_file
            if meta.is_file():
                return pid
        except Exception as e:
            logger.debug(f"本地缓存检查跳过: {e}")
        return None

    def get_project(self, project_id: str) -> Optional[GitHubProject]:
        """获取项目详情"""
        return self.storage_manager.load_project(project_id)
    
    def delete_project(self, project_id: str) -> bool:
        """删除项目"""
        return self.storage_manager.delete_project(project_id)
    
    def _ensure_homepage_screenshot_in_project(self, project: GitHubProject) -> bool:
        """
        若磁盘上已有 screenshots/project_homepage.jpg，保证 images 中存在 screenshot_001
        且 local_path 指向该文件（便于替换文件后列表与接口一致）。
        """
        base = project.local_storage_path or (
            self.storage_config.projects_dir / project.id
        )
        shot = Path(base) / "screenshots" / "project_homepage.jpg"
        if not shot.is_file():
            return False
        try:
            shot_resolved = shot.resolve()
        except OSError:
            shot_resolved = shot
        changed = False
        for img in project.images:
            if img.id != "screenshot_001":
                continue
            lp = Path(img.local_path) if img.local_path else None
            if not lp:
                img.local_path = shot
                changed = True
            else:
                try:
                    if lp.resolve() != shot_resolved:
                        img.local_path = shot
                        changed = True
                except OSError:
                    img.local_path = shot
                    changed = True
            project.screenshot_path = shot
            return changed
        project.images.append(
            ProjectImage(
                id="screenshot_001",
                url="https://github.com/screenshot",
                local_path=shot,
                source="screenshot",
                alt_text="项目主页截图",
                is_selected=False,
            )
        )
        project.screenshot_path = shot
        return True

    def _star_history_url_for_project(self, project: GitHubProject) -> str:
        """Star History SVG URL for this repository."""
        repos = quote(project.full_name, safe="/")
        return f"https://api.star-history.com/svg?repos={repos}&type=Date"

    def _prioritize_readme_images(self, images: List[ProjectImage]) -> List[ProjectImage]:
        """Prefer product screenshots from README tables over badges/shields."""
        low_value_hosts = (
            "img.shields.io",
            "shields.io",
            "badge.fury.io",
            "badgen.net",
            "app.codacy.com",
            "codecov.io",
            "sonarcloud.io",
            "snyk.io",
            "repobeats.axiom.co",
            "trendshift.io",
        )

        def priority(item: tuple[int, ProjectImage]) -> tuple[int, int]:
            index, image = item
            url = str(image.url)
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            path = parsed.path.lower()
            is_badge = host in low_value_hosts or any(
                marker in path for marker in ("badge", "shield", "status")
            )
            is_repo_asset = "raw.githubusercontent.com" in host or "/raw/" in path
            if is_repo_asset and not is_badge:
                return (0, index)
            if not is_badge:
                return (1, index)
            return (2, index)

        prioritized = [image for _, image in sorted(enumerate(images), key=priority)]
        if prioritized != images:
            logger.info(
                "README 图片已按素材价值排序：项目截图优先，徽章类图片后置"
            )
        return prioritized

    def _crop_star_history_whitespace(self, image_path: Path) -> bool:
        """Trim the large white canvas around Star History charts."""
        try:
            if not image_path.is_file() or image_path.stat().st_size <= 0:
                return False

            with Image.open(image_path) as image:
                rgb_image = image.convert("RGB")
                white_bg = Image.new("RGB", rgb_image.size, (255, 255, 255))
                diff = ImageChops.difference(rgb_image, white_bg).convert("L")
                content_mask = diff.point(lambda value: 255 if value > 10 else 0)
                bbox = content_mask.getbbox()

                if not bbox:
                    return False

                padding = 24
                left = max(0, bbox[0] - padding)
                top = max(0, bbox[1] - padding)
                right = min(rgb_image.width, bbox[2] + padding)
                bottom = min(rgb_image.height, bbox[3] + padding)

                if (
                    left <= 2
                    and top <= 2
                    and rgb_image.width - right <= 2
                    and rgb_image.height - bottom <= 2
                ):
                    return False

                cropped = rgb_image.crop((left, top, right, bottom))
                cropped.save(image_path, quality=95)
                logger.info(
                    f"Star History 曲线图已裁剪空白: {rgb_image.width}x{rgb_image.height} -> "
                    f"{cropped.width}x{cropped.height}"
                )
                return True
        except Exception as exc:
            logger.warning(f"Star History 曲线图裁剪失败: {image_path}, {exc}")
            return False

    def _ensure_star_history_image_in_project(self, project: GitHubProject) -> bool:
        """
        生成并登记 Star History 曲线图。

        Star History API 返回 SVG；视频合成阶段需要 PIL 可读取的位图，
        因此这里用浏览器把 SVG 页面截图成 JPG 后作为普通图片素材。
        """
        base = project.local_storage_path or (
            self.storage_config.projects_dir / project.id
        )
        image_dir = Path(base) / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / "star_history.jpg"
        star_url = self._star_history_url_for_project(project)

        if not image_path.is_file() or image_path.stat().st_size <= 0:
            ok = self.screenshot_service.take_screenshot_sync(
                star_url,
                image_path,
                ScreenshotOptions(
                    width=1280,
                    height=720,
                    full_page=False,
                    quality=92,
                    wait_time=1200,
                    timeout=45000,
                    hide_elements=[],
                    font_scale=1.0,
                ),
            )
            if not ok or not image_path.is_file() or image_path.stat().st_size <= 0:
                logger.warning(f"Star History 曲线图生成失败: {star_url}")
                return False

        self._crop_star_history_whitespace(image_path)

        changed = False
        for img in project.images:
            if img.id != self.STAR_HISTORY_IMAGE_ID:
                continue
            if str(img.url) != star_url:
                img.url = star_url
                changed = True
            if Path(img.local_path) != image_path if img.local_path else True:
                img.local_path = image_path
                changed = True
            if img.source != "star_history":
                img.source = "star_history"
                changed = True
            if img.alt_text != "Star 历史曲线图":
                img.alt_text = "Star 历史曲线图"
                changed = True
            return changed

        project.images.append(
            ProjectImage(
                id=self.STAR_HISTORY_IMAGE_ID,
                url=star_url,
                local_path=image_path,
                source="star_history",
                alt_text="Star 历史曲线图",
                is_selected=False,
            )
        )
        logger.info(f"Star History 曲线图已添加到可选素材: {image_path}")
        return True

    def get_available_images(self, project_id: str) -> Optional[ImageSelectionResponse]:
        """获取可选图片与 README 视频"""
        project = self.storage_manager.load_project(project_id)
        if not project:
            return None

        changed = False
        if self._ensure_homepage_screenshot_in_project(project):
            changed = True
        if self._ensure_star_history_image_in_project(project):
            changed = True
        if changed:
            self.storage_manager.save_project(project)
        
        sel_img = sum(1 for img in project.images if img.is_selected)
        sel_vid = sum(1 for v in project.videos if v.is_selected)
        n_img = len(project.images)
        n_vid = len(project.videos)
        
        return ImageSelectionResponse(
            project_id=project_id,
            available_images=project.images,
            available_videos=project.videos,
            total_count=n_img + n_vid,
            selected_count=sel_img + sel_vid
        )
    
    def select_images(self, project_id: str, image_ids: List[str]) -> bool:
        """选择图片（仅更新图片；兼容旧前端）"""
        return self.select_assets(project_id, image_ids, [])

    def select_assets(
        self, project_id: str, image_ids: List[str], video_ids: List[str]
    ) -> bool:
        """勾选图片与 README 视频"""
        project = self.storage_manager.load_project(project_id)
        if not project:
            return False
        
        for image in project.images:
            image.is_selected = image.id in image_ids
        for vid in project.videos:
            vid.is_selected = vid.id in video_ids
        
        return self.storage_manager.save_project(project)
    
    def _generate_content_sync(self, request: ContentGenerationRequest) -> ContentGenerationResponse:
        """同步生成内容；在线程池中运行。"""
        try:
            # 获取项目信息
            project = self.storage_manager.load_project(request.project_id)
            if not project:
                return ContentGenerationResponse(
                    success=False,
                    project_id=request.project_id,
                    video_metadata=VideoMetadata(
                        title="", subtitle="", summary="", tags=[]
                    ),
                    processing_details={"error": "项目不存在"},
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

            # 与 index / 成片一致：主标题规范为两行（换行符），便于第三步展示
            video_metadata.title = format_main_title_two_lines(video_metadata.title)
            
            # 保存生成的内容到项目
            project.video_metadata = video_metadata
            self.storage_manager.save_project(project)
            
            return ContentGenerationResponse(
                success=True,
                project_id=request.project_id,
                video_metadata=video_metadata,
                processing_details={
                    "generated_fields": ["title", "subtitle", "summary", "tags"],
                    "ai_generated": video_metadata.ai_generated,
                    "compliance": self.content_analyzer.last_compliance,
                }
            )
            
        except Exception as e:
            logger.error(f"内容生成失败: {e}")
            return ContentGenerationResponse(
                success=False,
                project_id=request.project_id,
                video_metadata=VideoMetadata(
                    title="", subtitle="", summary="", tags=[]
                ),
                processing_details={"error": str(e)},
            )

    async def generate_content_async(self, request: ContentGenerationRequest) -> ContentGenerationResponse:
        return await asyncio.to_thread(self._generate_content_sync, request)

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

        # 元数据未同步但磁盘已有主页截图时仍返回路径（避免列表/预览 404）
        if image_id == "screenshot_001":
            shot = self.storage_config.projects_dir / project_id / "screenshots" / "project_homepage.jpg"
            if shot.is_file():
                return shot
        
        return None

    def get_video_path(self, project_id: str, video_id: str) -> Optional[Path]:
        """获取 README 视频的本地路径"""
        project = self.storage_manager.load_project(project_id)
        if not project:
            return None
        for v in project.videos:
            if v.id == video_id and v.local_path:
                return v.local_path
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