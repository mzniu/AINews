"""
GitHub项目处理API路由
提供GitHub项目内容抓取、图片处理和内容生成功能的REST API
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from typing import List, Optional
from pathlib import Path
import asyncio
from loguru import logger

from src.models.github_models import (
    GitHubProjectRequest, ContentGenerationRequest,
    ProcessResult, ImageSelectionResponse, ContentGenerationResponse,
    GitHubProject, GitHubVideoGenerationRequest
)
from services.github_service import GitHubProcessingService

router = APIRouter(prefix="/api/github", tags=["GitHub项目处理"])

# 全局服务实例
github_service: Optional[GitHubProcessingService] = None


def get_github_service() -> GitHubProcessingService:
    """获取GitHub服务实例"""
    global github_service
    if github_service is None:
        github_service = GitHubProcessingService()
    return github_service


@router.post("/process-project", response_model=ProcessResult)
async def process_github_project(
    request: GitHubProjectRequest,
    background_tasks: BackgroundTasks
):
    """
    处理GitHub项目
    - 解析项目信息
    - 提取README内容和图片
    - 截取项目主页截图
    - 下载处理图片资源
    """
    try:
        service = get_github_service()
        
        logger.info(f"开始处理GitHub项目: {request.github_url}")
        
        # 异步处理项目
        result = await service.process_project_async(request)
        
        if result.success:
            # 在后台清理临时文件
            background_tasks.add_task(service.cleanup_temp_files, result.project_id)
            logger.info(f"项目处理成功: {result.project_id}")
        else:
            logger.error(f"项目处理失败: {result.message}")
        
        return result
        
    except Exception as e:
        logger.error(f"处理GitHub项目时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.get("/projects", response_model=List[dict])
async def list_projects():
    """
    列出所有已处理的GitHub项目
    """
    try:
        service = get_github_service()
        projects = service.list_projects()
        return projects
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取项目列表失败: {str(e)}")


@router.get("/projects/{project_id}", response_model=GitHubProject)
async def get_project(project_id: str):
    """
    获取特定项目的详细信息
    """
    try:
        service = get_github_service()
        project = service.get_project(project_id)
        
        if not project:
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
        
        return project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取项目信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取项目信息失败: {str(e)}")


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """
    删除项目及其所有数据
    """
    try:
        service = get_github_service()
        success = service.delete_project(project_id)
        
        if success:
            return {"success": True, "message": f"项目 {project_id} 已删除"}
        else:
            raise HTTPException(status_code=500, detail=f"删除项目 {project_id} 失败")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除项目时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/projects/{project_id}/images", response_model=ImageSelectionResponse)
async def get_project_images(project_id: str):
    """
    获取项目的所有图片供选择
    """
    try:
        service = get_github_service()
        response = service.get_available_images(project_id)
        
        if not response:
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在或无图片")
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取项目图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图片失败: {str(e)}")


@router.post("/projects/{project_id}/select-images")
async def select_project_images(project_id: str, selected_image_ids: List[str]):
    """
    选择项目图片
    """
    try:
        service = get_github_service()
        success = service.select_images(project_id, selected_image_ids)
        
        if success:
            return {"success": True, "message": "图片选择已更新"}
        else:
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"选择图片时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"选择图片失败: {str(e)}")


@router.post("/generate-content", response_model=ContentGenerationResponse)
async def generate_video_content(request: ContentGenerationRequest):
    """
    基于项目内容生成视频元数据
    - 自动生成标题、副标题、摘要
    - 提取相关标签
    """
    try:
        service = get_github_service()
        response = await service.generate_content_async(request)
        
        if not response.success:
            raise HTTPException(status_code=400, detail=response.processing_details.get("error", "内容生成失败"))
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成内容时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"内容生成失败: {str(e)}")


@router.get("/projects/{project_id}/screenshot")
async def get_project_screenshot(project_id: str):
    """
    获取项目主页截图
    """
    try:
        service = get_github_service()
        screenshot_path = service.get_screenshot_path(project_id)
        
        if not screenshot_path or not screenshot_path.exists():
            raise HTTPException(status_code=404, detail="截图不存在")
        
        return FileResponse(
            screenshot_path,
            media_type="image/jpeg",
            filename=f"{project_id}_screenshot.jpg"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取截图失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取截图失败: {str(e)}")


@router.get("/projects/{project_id}/images/{image_id}")
async def get_project_image(project_id: str, image_id: str):
    """
    获取项目的特定图片
    """
    try:
        service = get_github_service()
        image_path = service.get_image_path(project_id, image_id)
        
        if not image_path or not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")
        
        # 确定媒体类型
        media_type = "image/jpeg" if image_path.suffix.lower() in ['.jpg', '.jpeg'] else "image/png"
        
        return FileResponse(
            image_path,
            media_type=media_type,
            filename=image_path.name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图片失败: {str(e)}")


@router.get("/projects/{project_id}/stats")
async def get_project_stats(project_id: str):
    """
    获取项目统计信息
    """
    try:
        service = get_github_service()
        stats = service.get_project_stats(project_id)
        
        if not stats:
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取项目统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.post("/batch-process")
async def batch_process_projects(requests: List[GitHubProjectRequest]):
    """
    批量处理多个GitHub项目
    """
    try:
        service = get_github_service()
        results = []
        
        for request in requests:
            try:
                result = await service.process_project_async(request)
                results.append(result)
            except Exception as e:
                results.append(ProcessResult(
                    success=False,
                    message=f"处理失败: {str(e)}",
                    project_id=None
                ))
        
        return {"results": results}
        
    except Exception as e:
        logger.error(f"批量处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量处理失败: {str(e)}")


@router.post("/generate-video", response_model=ContentGenerationResponse)
async def generate_github_video(
    request: GitHubVideoGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    基于GitHub项目内容生成完整视频
    - 自动生成标题、副标题、摘要
    - 使用项目图片制作动画视频
    - 返回视频文件路径
    """
    try:
        service = get_github_service()
        
        # 1. 首先处理项目（如果还没有处理过）
        if not request.project_id:
            # 需要先处理项目
            project_request = GitHubProjectRequest(
                github_url=request.github_url,
                include_screenshots=request.include_screenshots,
                max_images=request.max_images
            )
            process_result = await service.process_project_async(project_request)
            if not process_result.success:
                raise HTTPException(status_code=400, detail=f"项目处理失败: {process_result.message}")
            project_id = process_result.project_id
        else:
            project_id = request.project_id
        
        # 2. 获取项目信息
        project = service.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
        
        # 3. 生成内容
        content_request = ContentGenerationRequest(
            project_id=project_id,
            selected_images=[],  # 使用所有图片
            custom_title=request.custom_title,
            custom_summary=request.custom_summary
        )
        
        content_response = await service.generate_content_async(content_request)
        if not content_response.success:
            raise HTTPException(status_code=400, detail="内容生成失败")
        
        # 4. 准备视频生成参数
        video_metadata = content_response.video_metadata
        
        # 获取图片路径列表
        image_paths = []
        for image in project.images:
            if image.local_path and image.local_path.exists():
                image_paths.append(str(image.local_path))
        
        if not image_paths:
            raise HTTPException(status_code=400, detail="没有可用的图片用于视频生成")
        
        # 5. 调用现有的视频生成API
        from api.routes.video_routes import create_animated_video
        from api.schemas.request_models import CreateAnimatedVideoRequest
        
        # 构造视频生成请求
        audio_path = "static/music/background.mp3" if request.include_audio else ""
        video_request = CreateAnimatedVideoRequest(
            title=f"{video_metadata.title} | {video_metadata.subtitle or ''}".strip(' |'),
            summary=video_metadata.summary,
            images=image_paths[:10],  # 限制图片数量
            audio_path=audio_path  # 根据选项决定是否添加音频
        )
        
        # 6. 生成视频
        video_result = await create_animated_video(video_request)
        
        # 7. 保存视频信息到项目
        # 这里可以扩展项目模型来存储视频信息
        
        return ContentGenerationResponse(
            success=True,
            project_id=project_id,
            video_metadata=video_metadata,
            processing_details={
                "video_generated": True,
                "video_result": video_result if hasattr(video_result, 'dict') else str(video_result)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成GitHub视频时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")


@router.get("/projects/{project_id}/video")
async def get_project_video(project_id: str):
    """
    获取项目生成的视频文件
    """
    try:
        # 查找该项目的视频文件
        from pathlib import Path
        import glob
        
        # 更广泛的视频文件搜索模式
        video_patterns = [
            f"data/generated/anim_*/{project_id}*.mp4",
            f"data/generated/anim_*/*.mp4",  # 不限制项目ID
            f"data/videos/*{project_id}*.mp4",
            f"data/videos/*.mp4"  # 最宽松的匹配
        ]
        
        video_files = []
        for pattern in video_patterns:
            video_files.extend(glob.glob(pattern))
        
        if not video_files:
            # 如果没找到特定项目的视频，返回最新的视频文件
            all_videos = glob.glob("data/generated/anim_*/**/*.mp4", recursive=True)
            all_videos.extend(glob.glob("data/videos/**/*.mp4", recursive=True))
            if all_videos:
                video_files = all_videos
            else:
                raise HTTPException(status_code=404, detail="未找到任何视频文件")
        
        # 返回最新的视频文件
        latest_video = max(video_files, key=lambda x: Path(x).stat().st_mtime)
        
        return FileResponse(
            latest_video,
            media_type="video/mp4",
            filename=f"{project_id}_video.mp4"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取视频文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频失败: {str(e)}")


# 健康检查端点
@router.get("/health")
async def health_check():
    """健康检查"""
    try:
        service = get_github_service()
        # 简单的健康检查
        storage_stats = service.list_projects()
        return {
            "status": "healthy",
            "service": "github_processing",
            "projects_count": len(storage_stats),
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")