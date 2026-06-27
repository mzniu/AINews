"""
GitHub项目处理API路由
提供GitHub项目内容抓取、图片处理和内容生成功能的REST API
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse
from typing import List, Optional
from pathlib import Path
import asyncio
from loguru import logger

from src.models.github_models import (
    GitHubProjectRequest, ContentGenerationRequest,
    ProcessResult, ImageSelectionResponse, ContentGenerationResponse,
    GitHubProject, GitHubVideoGenerationRequest,
    GitHubVoiceoverRequest, GitHubVoiceoverResponse,
    SelectAssetsRequest,
    GitHubLocalCacheLookup,
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


@router.get("/local-cache", response_model=GitHubLocalCacheLookup)
async def github_local_cache_lookup(github_url: str):
    """
    根据仓库链接判断本地是否已有已处理/已下载的数据（存在 metadata.json）。
    不访问网络，仅查磁盘；用于前端「是否使用已下载内容」提示。
    """
    try:
        service = get_github_service()
        pid = service.find_cached_project_id(github_url)
        if pid:
            return GitHubLocalCacheLookup(cached=True, project_id=pid)
        return GitHubLocalCacheLookup(cached=False, project_id=None)
    except Exception as e:
        logger.warning(f"本地缓存查询失败: {e}")
        return GitHubLocalCacheLookup(cached=False, project_id=None)


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
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
        if response.total_count == 0:
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 无可用图片或视频")
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取项目图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图片失败: {str(e)}")


@router.post("/projects/{project_id}/select-images")
async def select_project_images(project_id: str, request: Request):
    """
    选择项目图片与 README 视频。
    兼容旧版：请求体为 JSON 字符串数组时仅更新图片。
    新版：{"image_ids": [...], "video_ids": [...]}
    """
    try:
        import json
        service = get_github_service()
        raw = await request.body()
        text = (raw.decode() or "").strip()
        if not text:
            data = []
        else:
            data = json.loads(text)
        if isinstance(data, list):
            success = service.select_assets(project_id, data, [])
        else:
            body = SelectAssetsRequest.model_validate(data)
            success = service.select_assets(
                project_id, body.image_ids, body.video_ids
            )
        
        if success:
            return {"success": True, "message": "选择已更新"}
        else:
            raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"选择素材时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"选择失败: {str(e)}")


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


@router.post("/projects/{project_id}/refresh-screenshot")
async def refresh_project_screenshot(project_id: str):
    """
    仅重新截取 GitHub 项目主页截图并更新本地元数据。
    不重新下载 README、README 图片与视频，适用于首次截图失败时单独重试。
    """
    try:
        service = get_github_service()
        ok, msg = await service.refresh_project_homepage_screenshot_async(project_id)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {
            "success": True,
            "message": msg,
            "project_id": project_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"单独刷新主页截图失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新截图失败: {str(e)}")


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
            filename=f"{project_id}_screenshot.jpg",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
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
        
        # 确定媒体类型，避免 GIF / WebP 预览被浏览器按 PNG 解释导致动图不可见
        suffix = image_path.suffix.lower()
        media_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml',
        }
        media_type = media_type_map.get(suffix, 'application/octet-stream')
        
        return FileResponse(
            image_path,
            media_type=media_type,
            filename=image_path.name,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图片失败: {str(e)}")


@router.get("/projects/{project_id}/videos/{video_id}")
async def get_project_readme_video(project_id: str, video_id: str):
    """流式预览已下载的 README 内嵌视频（本地缓存）。"""
    try:
        service = get_github_service()
        p = service.get_video_path(project_id, video_id)
        if not p or not p.exists():
            raise HTTPException(status_code=404, detail="视频不存在")
        mt = "video/mp4"
        if p.suffix.lower() == ".webm":
            mt = "video/webm"
        elif p.suffix.lower() == ".mov":
            mt = "video/quicktime"
        return FileResponse(
            p,
            media_type=mt,
            filename=p.name,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 README 视频失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取视频失败: {str(e)}")


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
                max_images=request.max_images,
                max_videos=request.max_videos,
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
        
        # 5. 调用现有的视频生成API
        from api.routes.video_routes import create_animated_video
        from api.schemas.request_models import CreateAnimatedVideoRequest, ImageWithDuration

        if not request.include_audio:
            audio_path = ""
        else:
            ap = (request.audio_path or "").strip()
            audio_path = ap if ap else "static/music/background.mp3"

        if request.image_sequence:
            id_to_path = {
                im.id: str(im.local_path)
                for im in project.images
                if im.local_path and im.local_path.exists()
            }
            id_to_path.update({
                v.id: str(v.local_path)
                for v in project.videos
                if v.local_path and v.local_path.exists()
            })
            images_payload = []
            for clip in request.image_sequence:
                p = id_to_path.get(clip.id)
                if p:
                    images_payload.append(
                        ImageWithDuration(path=p, duration=float(clip.duration))
                    )
            if not images_payload:
                raise HTTPException(
                    status_code=400,
                    detail="image_sequence 中的素材 id 无法解析为本地文件（支持图片与 README 视频）",
                )
            images_payload = images_payload[:10]
        else:
            selected_imgs = [
                img
                for img in project.images
                if img.is_selected and img.local_path and img.local_path.exists()
            ]
            selected_vids = [
                v
                for v in project.videos
                if v.is_selected and v.local_path and v.local_path.exists()
            ]
            if selected_imgs or selected_vids:
                pool = selected_imgs + selected_vids
            else:
                pool = [
                    img
                    for img in project.images
                    if img.local_path and img.local_path.exists()
                ] + [
                    v
                    for v in project.videos
                    if v.local_path and v.local_path.exists()
                ]
            image_paths = [str(x.local_path) for x in pool]
            if not image_paths:
                raise HTTPException(
                    status_code=400,
                    detail="没有可用的图片或 README 视频用于生成",
                )
            images_payload = image_paths[:10]

        from utils.title_units import (
            split_main_title_to_two_lines,
        )

        _has_line_fields = (
            request.custom_main_line1 is not None or request.custom_main_line2 is not None
        )
        _nonempty_custom = (request.custom_main_line1 or "").strip() or (
            request.custom_main_line2 or ""
        ).strip()
        if _has_line_fields and _nonempty_custom:
            m1 = (request.custom_main_line1 or "").strip()
            m2 = (request.custom_main_line2 or "").strip()
        else:
            m1, m2 = split_main_title_to_two_lines(video_metadata.title or "")
        sub = (video_metadata.subtitle or "").strip()
        sub2 = (request.custom_subtitle2 if request.custom_subtitle2 is not None else (video_metadata.subtitle2 or "")).strip()
        video_request = CreateAnimatedVideoRequest(
            title="",
            main_line1=m1,
            main_line2=m2,
            subtitle=sub,
            subtitle2=sub2,
            summary=video_metadata.summary,
            images=images_payload,
            audio_path=audio_path,
            show_summary=False,
            background_image_path=request.background_image_path,
            title_font_key=request.title_font_key,
            first_image_effect="side_flip_rounded",
            summary_highlight_keywords=list(video_metadata.tags)
            if getattr(video_metadata, "tags", None)
            else None,
        )
        
        # 6. 生成视频（画面上不叠摘要，摘要用于第五步口播）
        video_result = await create_animated_video(video_request)
        from starlette.responses import JSONResponse

        if isinstance(video_result, JSONResponse):
            import json

            body = json.loads(video_result.body.decode())
            raise HTTPException(
                status_code=int(video_result.status_code),
                detail=body.get("message", "视频生成失败"),
            )

        video_path = video_result.get("video_path") if isinstance(video_result, dict) else None

        return ContentGenerationResponse(
            success=True,
            project_id=project_id,
            video_metadata=video_metadata,
            processing_details={
                "video_generated": True,
                "video_path": video_path,
                "video_result": video_result if isinstance(video_result, dict) else {},
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成GitHub视频时发生错误: {e}")
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")


@router.post("/projects/{project_id}/voiceover", response_model=GitHubVoiceoverResponse)
async def github_render_voiceover(project_id: str, request: GitHubVoiceoverRequest):
    """第五步：为已生成的基底视频添加 TTS 配音与字幕（硬字幕可选）。"""
    service = get_github_service()
    if not service.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")

    base = request.base_video_path.strip().lstrip("/")
    base_path = Path(base)
    if not base_path.is_file():
        raise HTTPException(status_code=400, detail=f"基底视频不存在: {request.base_video_path}")

    from services.github_voiceover_service import render_voiceover_for_video

    ok, msg, final_url, srt_url, tts_audio_url = await render_voiceover_for_video(
        base_video_path=base_path,
        script=request.script,
        voice=request.voice or "zh-CN-XiaoxiaoNeural",
        voice_clone_audio_path=request.voice_clone_audio_path,
        mix_bgm=request.mix_bgm,
        bgm_gain_db=request.bgm_gain_db,
        narration_gain_db=request.narration_gain_db,
        burn_subtitles=request.burn_subtitles,
        tts_rate=(request.tts_rate or "+25%").strip(),
        subtitle_fontname=request.subtitle_fontname or "Microsoft YaHei",
        subtitle_fontsize=request.subtitle_fontsize,
        subtitle_margin_bottom_percent=float(request.subtitle_margin_bottom_percent),
        subtitle_margin_left_percent=float(request.subtitle_margin_left_percent),
        subtitle_max_chars=request.subtitle_max_chars,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=msg or "配音合成失败")
    return GitHubVoiceoverResponse(
        success=True,
        message=msg or "完成",
        final_video_path=final_url,
        srt_path=srt_url,
        tts_audio_path=tts_audio_url,
    )


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