"""视频处理相关API路由"""
import asyncio

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import List, Optional
from pathlib import Path
from datetime import datetime
from loguru import logger
import os
from PIL import Image, ImageDraw
from ..schemas.request_models import (
    CreateVideoRequest, CreateAnimatedVideoRequest, CreateUserVideoRequest
)
from utils.video_utils import (
    _render_frame_animated, _apply_video_effect, _safe_paste, _draw_text_overlay,
    _load_fonts, _wrap_text, _break_summary_by_punctuation, _subtitle_block_height,
    MAIN_SUBTITLE_GAP_PX,
    _scroll_up_effective_distance,
    SCROLL_UP_PIXELS_PER_SEC,
)
from utils.summary_highlights import resolve_highlight_keywords
from utils.title_units import (
    truncate_han_equiv,
    MAIN_LINE1_MAX_UNITS,
    MAIN_LINE2_MAX_UNITS,
    SUBTITLE_MAX_UNITS,
)
from services.video_service import VideoService
from services.video_embedding_service import video_embedding_service
from services.gif_processor import gif_processor
import cv2
import numpy as np

router = APIRouter(prefix="/api", tags=["视频"])


def _resolve_background_image_path(path_str: Optional[str]) -> Path:
    """成片背景图：仅允许项目内 static/ 下的已有文件，否则回退默认底图。"""
    default = Path("static/imgs/bg.png")
    if not path_str or not str(path_str).strip():
        return default
    raw = str(path_str).strip().replace("\\", "/").lstrip("/")
    if ".." in raw:
        return default
    p = Path(raw)
    if not p.is_file():
        return default
    try:
        abs_p = p.resolve()
        static_root = Path("static").resolve()
        if static_root not in abs_p.parents and abs_p != static_root:
            return default
    except (OSError, ValueError):
        return default
    return p


def _perspective_coefficients(src_points, dst_points):
    matrix = []
    for (src_x, src_y), (dst_x, dst_y) in zip(src_points, dst_points):
        matrix.append([dst_x, dst_y, 1, 0, 0, 0, -src_x * dst_x, -src_x * dst_y])
        matrix.append([0, 0, 0, dst_x, dst_y, 1, -src_y * dst_x, -src_y * dst_y])
    vector = np.array(src_points).reshape(8)
    return np.linalg.lstsq(np.array(matrix, dtype=float), vector, rcond=None)[0]


def _apply_side_flip_rounded_card(image: Image.Image, angle_degrees: float = 30.0) -> Image.Image:
    """将图片处理成带圆角的侧翻透视卡片，用于 GitHub 首图特效。"""
    source = image.convert('RGBA')
    width, height = source.size
    if width < 4 or height < 4:
        return source

    radius = max(16, min(width, height) // 16)
    rounded_mask = Image.new('L', (width, height), 0)
    mask_draw = ImageDraw.Draw(rounded_mask)
    mask_draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    rounded = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    rounded.paste(source, (0, 0), rounded_mask)

    # 45 度侧翻的视觉核心是横向压缩与远端边收短；这里保留较大的画面面积，避免内容过窄。
    angle_factor = max(0.55, min(0.9, float(np.cos(np.deg2rad(angle_degrees)))))
    output_width = max(2, int(width * (0.72 + 0.18 * angle_factor)))
    output_height = height
    far_edge_inset = max(8, int(height * (0.08 + 0.08 * (1.0 - angle_factor))))

    src_points = [
        (0, 0),
        (width - 1, 0),
        (width - 1, height - 1),
        (0, height - 1),
    ]
    dst_points = [
        (0, 0),
        (output_width - 1, far_edge_inset),
        (output_width - 1, output_height - 1 - far_edge_inset),
        (0, output_height - 1),
    ]
    coefficients = _perspective_coefficients(src_points, dst_points)
    transform_method = getattr(getattr(Image, 'Transform', Image), 'PERSPECTIVE', Image.PERSPECTIVE)
    resample_method = getattr(getattr(Image, 'Resampling', Image), 'BICUBIC', Image.BICUBIC)
    return rounded.transform(
        (output_width, output_height),
        transform_method,
        coefficients,
        resample=resample_method,
        fillcolor=(0, 0, 0, 0),
    )


def _resolve_animated_title_lines(
    request: CreateAnimatedVideoRequest,
    temp_draw,
    title_font,
    subtitle_font,
    text_width: int,
):
    """
    新格式：main_line1 / main_line2 / subtitle — 主标题两行白字单行绘制；副标题黄底黑字圆角单行。
    长度：主标题第一行 14～18 汉字当量（英文数字计 0.5），服务端截断至 18；
    第二行 16～20 当量，截断至 20；副标题≤16 当量。
    旧格式：仅 title，为「主文|副标题」，主文可自动换行。
    返回 (main_title_lines, sub_title_lines)。
    """
    m1 = truncate_han_equiv((request.main_line1 or "").strip(), MAIN_LINE1_MAX_UNITS)
    m2 = truncate_han_equiv((request.main_line2 or "").strip(), MAIN_LINE2_MAX_UNITS)
    sub = truncate_han_equiv((request.subtitle or "").strip(), SUBTITLE_MAX_UNITS)
    legacy = (request.title or "").strip()

    if m1 or m2 or sub:
        main_title_lines = [x for x in [m1, m2] if x]
        sub_title_lines = [sub] if sub else []
        return main_title_lines, sub_title_lines

    if legacy:
        parts = legacy.split("|", 1)
        main_t = parts[0].strip()
        sub_t = parts[1].strip() if len(parts) > 1 else ""
        main_title_lines = _wrap_text(main_t, title_font, text_width, temp_draw)
        sub_title_lines = (
            _wrap_text(sub_t, subtitle_font, text_width, temp_draw) if sub_t else []
        )
        return main_title_lines, sub_title_lines

    return ["未命名标题"], []


@router.get("/list-videos")
async def list_videos():
    """列出所有已生成的视频文件"""
    try:
        video_dir = Path("data/videos")
        if not video_dir.exists():
            return JSONResponse(status_code=200, content={"success": True, "videos": []})
        
        videos = []
        for video_file in video_dir.glob("*.mp4"):
            if video_file.is_file() and video_file.stat().st_size > 0:  # 只包含非空文件
                stat = video_file.stat()
                
                # 生成封面图片路径
                thumbnail_path = video_file.with_suffix('.jpg')
                thumbnail_exists = thumbnail_path.exists()
                
                videos.append({
                    "filename": video_file.name,
                    "local_path": f"/data/videos/{video_file.name}",
                    "thumbnail_path": f"/data/videos/{thumbnail_path.name}" if thumbnail_exists else None,
                    "size_bytes": stat.st_size,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "success": True,
                    "has_thumbnail": thumbnail_exists
                })
        
        # 按创建时间倒序排列
        videos.sort(key=lambda x: x["created_time"], reverse=True)
        
        logger.info(f"扫描到 {len(videos)} 个视频文件")
        return JSONResponse(status_code=200, content={"success": True, "videos": videos})
        
    except Exception as e:
        logger.error(f"扫描视频文件失败: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@router.get("/extract-thumbnail/{video_filename}")
async def extract_video_thumbnail(video_filename: str):
    """为指定视频文件提取封面图片"""
    try:
        from moviepy import VideoFileClip
        import cv2
        
        video_path = Path("data/videos") / video_filename
        if not video_path.exists():
            return JSONResponse(status_code=404, content={"success": False, "message": "视频文件不存在"})
        
        # 生成缩略图文件名
        thumbnail_filename = video_filename.replace('.mp4', '.jpg')
        thumbnail_path = Path("data/videos") / thumbnail_filename
        
        # 如果缩略图已存在，直接返回
        if thumbnail_path.exists():
            return JSONResponse(status_code=200, content={
                "success": True, 
                "thumbnail_path": f"/data/videos/{thumbnail_filename}",
                "message": "缩略图已存在"
            })
        
        # 提取视频第一帧作为封面
        try:
            # 方法1: 使用moviepy
            clip = VideoFileClip(str(video_path))
            frame = clip.get_frame(0)  # 获取第0秒的帧
            clip.close()
            
            # 转换为PIL图像并保存
            from PIL import Image
            import numpy as np
            pil_image = Image.fromarray(frame)
            
            # 调整尺寸并保持质量
            pil_image = pil_image.resize((320, 180), Image.Resampling.LANCZOS)
            pil_image.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
            
            logger.info(f"成功提取视频封面: {thumbnail_filename}")
            return JSONResponse(status_code=200, content={
                "success": True, 
                "thumbnail_path": f"/data/videos/{thumbnail_filename}",
                "message": "缩略图提取成功"
            })
            
        except Exception as e:
            logger.warning(f"MoviePy提取失败，尝试OpenCV: {e}")
            # 方法2: 使用OpenCV作为备选方案
            try:
                cap = cv2.VideoCapture(str(video_path))
                ret, frame = cap.read()
                if ret:
                    # 转换颜色空间 BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_image = Image.fromarray(frame_rgb)
                    pil_image = pil_image.resize((320, 180), Image.Resampling.LANCZOS)
                    pil_image.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
                    logger.info(f"使用OpenCV成功提取视频封面: {thumbnail_filename}")
                    return JSONResponse(status_code=200, content={
                        "success": True, 
                        "thumbnail_path": f"/data/videos/{thumbnail_filename}",
                        "message": "缩略图提取成功"
                    })
                cap.release()
            except Exception as e2:
                logger.error(f"OpenCV提取也失败: {e2}")
                
        # 如果都失败，返回默认封面
        return JSONResponse(status_code=200, content={
            "success": True, 
            "thumbnail_path": None,
            "message": "使用默认封面"
        })
        
    except Exception as e:
        logger.error(f"提取视频缩略图失败: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

@router.post("/upload-images")
async def upload_images(files: List[UploadFile] = File(...)):
    """上传图片文件"""
    try:
        upload_dir = Path("data/uploaded")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        saved_files = []
        for file in files:
            if file.content_type and not file.content_type.startswith("image/"):
                continue
                
            # 生成唯一文件名
            import uuid
            file_extension = Path(file.filename).suffix if file.filename else ".jpg"
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = upload_dir / unique_filename
            
            # 保存文件
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            relative_path = str(file_path.relative_to(Path("."))).replace("\\", "/")
            saved_files.append({
                "filename": file.filename,
                "saved_path": f"/{relative_path}",
                "content_type": file.content_type
            })
        
        return {
            "success": True,
            "message": f"成功上传 {len(saved_files)} 个文件",
            "files": saved_files
        }
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")

@router.post("/create-video")
async def create_video(request: CreateVideoRequest):
    """创建普通视频"""
    try:
        logger.info(f"开始生成普通视频: 帧目录='{request.frames_dir}', 时长={request.duration_per_frame}秒/帧")
        
        # 模拟视频生成过程
        import time
        import os
        from pathlib import Path
        time.sleep(1.5)  # 模拟处理时间
        
        # 检查帧目录是否存在
        frames_dir = request.frames_dir.lstrip('/')
        if not os.path.exists(frames_dir):
            logger.warning(f"帧目录不存在: {frames_dir}")
            # 创建模拟目录结构
            os.makedirs(frames_dir, exist_ok=True)
        
        # 获取帧数量
        frame_files = [f for f in os.listdir(frames_dir) if f.endswith(('.png', '.jpg', '.jpeg'))] if os.path.exists(frames_dir) else []
        frame_count = len(frame_files) if frame_files else len(request.images) if hasattr(request, 'images') else 5  # 根据实际情况确定帧数
        
        # 生成视频文件路径
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        video_dir = Path("data/videos")
        video_dir.mkdir(parents=True, exist_ok=True)
        video_filename = f"video_{timestamp}.mp4"
        video_path = video_dir / video_filename
        # 创建空的视频文件（模拟）
        video_path.touch()
        
        relative_video_path = str(video_path.relative_to(Path("."))).replace("\\", "/")
        video_path_str = f"/{relative_video_path}"
        
        duration = frame_count * request.duration_per_frame
        file_size_mb = round(duration * 1.2, 1)  # 假设每秒1.2MB
        
        logger.info(f"普通视频生成完成: 路径={video_path_str}, 帧数={frame_count}, 时长={duration:.1f}秒, 大小={file_size_mb}MB")
        
        return {
            "success": True,
            "message": "视频生成完成",
            "video_path": video_path_str,
            "frame_count": frame_count,
            "duration": duration,
            "file_size_mb": file_size_mb,
            "timestamp": timestamp
        }
    except Exception as e:
        logger.error(f"视频生成失败: {e}")
        import traceback
        logger.error(f"详细错误信息: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")

def _create_animated_video_blocking(request: CreateAnimatedVideoRequest):
    """MoviePy 合成（同步、耗时长）；由 create_animated_video 在后台线程中调用，避免阻塞事件循环。"""
    try:
        if not request.images:
            return JSONResponse(status_code=400,
                                content={"success": False, "message": "请至少选择一张图片"})

        # MoviePy 2.x：concatenate 已并入 CompositeVideoClip 模块，请从 moviepy 顶层导入
        from moviepy import (
            VideoClip,
            concatenate_videoclips,
            AudioFileClip,
            concatenate_audioclips,
        )

        FPS = 24
        ENTRANCE_DUR = 0.4     # 小图弹落动画时长
        HOLD_NO_TEXT = 0.8     # 弹落后无文字停顿
        TEXT_FADE_IN = 0.4     # 文字渐入时长
        HOLD_WITH_TEXT = 1.4     # 文字显示后静持时长
        
        DEFAULT_CLIP_DURATION = HOLD_NO_TEXT + TEXT_FADE_IN + HOLD_WITH_TEXT  # 默认每段约 2.7 秒
        _ssm = request.summary_scroll_mode

        # 加载背景和字体
        bg_path = _resolve_background_image_path(
            getattr(request, "background_image_path", None)
        )
        bg_template = Image.open(bg_path) if bg_path.exists() else Image.new('RGB', (1080, 1920), (102, 126, 234))
        img_width, img_height = bg_template.size
        title_font, subtitle_font, summary_font = _load_fonts(
            getattr(request, "title_font_key", None)
        )

        margin = int(img_width * 0.08)
        text_width = img_width - 2 * margin

        # 预计算标题和摘要（新：主标题两行 + 副标题单行；旧：title 为 主|副）
        temp_draw = ImageDraw.Draw(bg_template.copy())
        main_title_lines, sub_title_lines = _resolve_animated_title_lines(
            request, temp_draw, title_font, subtitle_font, text_width
        )
        
        # 计算标题高度
        main_title_height = sum(
            temp_draw.textbbox((0, 0), l, font=title_font)[3] -
            temp_draw.textbbox((0, 0), l, font=title_font)[1] + 18
            for l in main_title_lines
        )
        sub_title_height = (
            _subtitle_block_height(sub_title_lines, subtitle_font, temp_draw)
            if sub_title_lines
            else 0
        )
        title_height = main_title_height + (
            sub_title_height + MAIN_SUBTITLE_GAP_PX if sub_title_height else 0
        )
        
        # 标题起始位置（距离顶部 10%）
        title_start_y = int(img_height * 0.1)
        
        # 构建 title_info
        title_info = (title_font, subtitle_font, main_title_lines, sub_title_lines,
                      title_start_y, main_title_height, margin, text_width)
                
        # 摘要：可选（GitHub 成片可关闭，改由后续步骤口播+字幕）
        if getattr(request, "show_summary", True):
            summary_lines = _wrap_text(
                _break_summary_by_punctuation(request.summary),
                summary_font,
                text_width,
                temp_draw,
            )
            summary_height = sum(
                temp_draw.textbbox((0, 0), l, font=summary_font)[3] -
                temp_draw.textbbox((0, 0), l, font=summary_font)[1] + 12
                for l in summary_lines
            )
            summary_start_y = int(img_height * 0.9) - summary_height
            hi_kw = resolve_highlight_keywords(
                request.summary,
                getattr(request, "tags", None) or "",
                list(getattr(request, "summary_highlight_keywords", None) or []),
            )
            summary_info = (summary_font, summary_lines, summary_start_y, hi_kw)
        else:
            summary_lines = []
            summary_height = 0
            summary_start_y = int(img_height * 0.92)
            summary_info = None

        clips = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("data/generated") / f"anim_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 构建动画队列：打乱后循环分配，保证每张图动画不同
        import random
        all_anim_types = ['zoom_in', 'zoom_out', 'unfold', 'scroll_up',
                          'slide_left', 'slide_right', 'fade_in', 'drop_bounce']
        
        # 处理图片数据：支持字符串或对象两种格式
        processed_images = []
        for img_item in request.images:
            if isinstance(img_item, str):
                # 向后兼容：字符串格式
                processed_images.append({
                    'path': img_item, 
                    'duration': None,
                    'has_zoom': True,  # 默认启用放大效果
                    'zoom_start_scale': 1.0,
                    'zoom_end_scale': 1.25
                })
            else:
                # 对象格式：包含 path 和 duration，以及放大参数
                processed_images.append({
                    'path': img_item.path,
                    'duration': img_item.duration,
                    'has_zoom': getattr(img_item, 'has_zoom', True),
                    'zoom_start_scale': getattr(img_item, 'zoom_start_scale', 1.0),
                    'zoom_end_scale': getattr(img_item, 'zoom_end_scale', 1.15)
                })
        
        num_images = len(processed_images)
        random.shuffle(all_anim_types)
        # 循环分配：图片数 > 动画种类时重复但尽量错开
        anim_queue = []
        for i in range(num_images):
            anim_queue.append(all_anim_types[i % len(all_anim_types)])

        first_clip_already_placed = False
        first_static_image_effect_applied = False
        for idx, img_data in enumerate(processed_images, 1):
            img_path = img_data['path']
            img_duration = img_data['duration']  # 可能为 null（视频）或秒数（图片）
            try:
                _tse = not first_clip_already_placed
                # 检查文件类型（动画 WebP 与 GIF 一样走多帧轨；静态 WebP 走下方静态图）
                is_video = img_path.lower().endswith(('.mp4', '.webm', '.mov'))
                _ap = Path(img_path.lstrip('/'))
                is_gif = _ap.is_file() and gif_processor.is_animation_raster(str(_ap))
                
                if is_video:
                    # 处理视频文件 - 画中画效果
                    logger.info(f"🎬 处理视频文件 (画中画): {img_path}")
                    logger.info(f"   视频路径：{img_path}")
                                    
                    # 使用用户配置的时长，如果没有则使用默认值
                    clip_duration = img_duration if img_duration is not None else DEFAULT_CLIP_DURATION
                    logger.info(f"   目标时长：{clip_duration}秒")
                    
                    # 修复路径问题
                    actual_video_path = img_path.lstrip('/')
                    logger.info(f"   实际视频路径: {actual_video_path}")
                    
                    # 检查文件是否存在
                    if not Path(actual_video_path).exists():
                        logger.error(f"   ❌ 视频文件不存在: {actual_video_path}")
                        logger.warning(f"   ⚠️ 跳过视频文件: {img_path}")
                        continue
                    
                    logger.info(f"   ✅ 视频文件存在")
                    
                    # 创建画中画效果
                    pip_result = video_embedding_service.create_pip_video_effect(
                        [actual_video_path],
                        bg_template,
                        title_info,
                        summary_info,
                        clip_duration,
                        title_slide_entrance=_tse,
                    )
                                        
                    if pip_result.get('success') and pip_result.get('segments'):
                        segment = pip_result['segments'][0]
                        logger.info(f"   🎨 画中画效果创建成功：{len(segment['frames'])} 帧")
                                            
                        # 使用画中画帧创建视频片段
                        def make_pip_frame(t, frames=segment['frames'], duration=clip_duration):
                            frame_index = int((t / duration) * len(frames))
                            frame_index = min(frame_index, len(frames) - 1)
                            return np.array(frames[frame_index])
                                            
                        clip = VideoClip(make_pip_frame, duration=clip_duration).with_fps(FPS)
                        clips.append(clip)
                        first_clip_already_placed = True
                        
                        # 保存预览帧（使用第一帧）
                        if segment['frames']:
                            preview = np.array(segment['frames'][0])
                            preview_path = output_dir / f"preview_{idx:02d}.png"
                            Image.fromarray(preview).save(preview_path, quality=95)
                            logger.info(f"   🖼️ 预览帧保存成功: {preview_path}")
                        
                        continue  # 跳过下面的静态图片处理
                    else:
                        logger.warning(f"   ⚠️ 画中画效果创建失败，使用视频缩略图代替: {img_path}")
                        # 回退到使用视频第一帧作为静态图片
                        try:
                            cap = cv2.VideoCapture(actual_video_path)
                            ret, frame = cap.read()
                            cap.release()
                            
                            if ret:
                                # 转换为PIL图像
                                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                user_img = Image.fromarray(frame_rgb)
                                if user_img.mode != 'RGBA':
                                    user_img = user_img.convert('RGBA')
                                
                                # 继续使用静态图片处理逻辑
                                logger.info(f"   🔄 回退到静态图片处理")
                                # 注意：这里不使用continue，而是让代码继续执行到下面的静态图片处理部分
                                # 因为user_img已经设置好了
                            else:
                                logger.error(f"   ❌ 无法读取视频帧，跳过文件: {img_path}")
                                continue
                        except Exception as e:
                            logger.error(f"   ❌ 视频回退处理失败: {e}")
                            continue
                
                if is_gif:
                    # 处理 GIF / 动画 WebP（多帧）
                    logger.info(f"🔄 处理 GIF/动画 WebP：{img_path}")
                    logger.info(f"   素材路径：{img_path}")
                    
                    # 使用用户配置的时长，如果没有则使用默认值
                    clip_duration = img_duration if img_duration is not None else DEFAULT_CLIP_DURATION
                    logger.info(f"   目标时长：{clip_duration}秒")
                    
                    # 修复路径问题 - 去掉开头的斜杠
                    actual_gif_path = img_path.lstrip('/')
                    logger.info(f"   实际路径: {actual_gif_path}")
                    
                    # 检查文件是否存在
                    if not Path(actual_gif_path).exists():
                        logger.error(f"   ❌ 文件不存在: {actual_gif_path}")
                        logger.warning(f"   ⚠️ 回退到静态图片处理: {img_path}")
                        # 继续使用静态图片处理逻辑
                    else:
                        logger.info(f"   ✅ 文件存在")

                        gif_frames = gif_processor.extract_gif_frames(actual_gif_path)
                        
                        if gif_frames and len(gif_frames) > 0:
                            logger.info(f"   🎬 提取到 {len(gif_frames)} 帧动画")
                            
                            # 将第一帧作为基础图片进行处理
                            first_frame = Image.fromarray(gif_frames[0])
                            if first_frame.mode != 'RGBA':
                                first_frame = first_frame.convert('RGBA')
                            
                            # 缩放GIF帧
                            target_w = img_width
                            ratio = target_w / first_frame.width
                            target_h = int(first_frame.height * ratio)
                            # 取消60%高度限制，允许图片延伸到背景底部
                            # max_h = int(img_height * 0.6)
                            # if target_h > max_h:
                            #     target_h = max_h
                            #     ratio = target_h / first_frame.height
                            #     target_w = int(first_frame.width * ratio)
                            
                            first_frame_resized = first_frame.resize((target_w, target_h), Image.Resampling.LANCZOS)
                            
                            paste_x = (img_width - target_w) // 2
                            # 图片在标题和摘要之间居中
                            available = summary_start_y - 40 - (title_start_y + title_height + 30)
                            final_paste_y = title_start_y + title_height + 30 + (available - target_h) // 2
                            final_paste_y = max(title_start_y + title_height + 30, final_paste_y)
                            
                            logger.info(f"   片段 {idx}: 生成 {clip_duration:.1f}s GIF 动画，尺寸 {target_w}x{target_h}")
                            
                            # ⚠️ 智能动画选择：如果图片高度过大，自动使用向上滚动
                            # 使用原始GIF帧高度来判断（未缩放前）
                            orig_gif_height = gif_frames[0].shape[0]  # 第一帧的高度
                            gif_height_ratio = orig_gif_height / img_height  # 原始高度占屏幕比例
                            
                            # 使用GIF帧创建动画片段
                            anim = anim_queue.pop(0)
                            
                            if gif_height_ratio > 0.7:  # 如果原始GIF高度超过屏幕 70%
                                anim = 'scroll_up'  # 强制使用向上滚动
                                logger.info(f"   片段 {idx} 检测到高图（原始高度 {orig_gif_height}px, 占比 {gif_height_ratio:.1%}），自动使用 scroll_up 动画")
                            else:
                                logger.info(f"   片段 {idx} 动画类型: {anim}")
                            
                            # 创建GIF动画make_frame函数
                            def make_gif_frame_func(t, _bg=bg_template, _frames=gif_frames,
                                                   _px=paste_x, _py=final_paste_y,
                                                   _tw=target_w, _th=target_h,
                                                   _ti=title_info, _si=summary_info,
                                                   _anim=anim, _dur=clip_duration,
                                                   _tse=_tse,
                                                   _slot=available):
                                # 计算当前应该显示哪一帧
                                total_frames = len(_frames)
                                current_frame_index = int((t / _dur) * total_frames) % total_frames
                                current_frame = Image.fromarray(_frames[current_frame_index])
                                
                                # 缩放到目标尺寸
                                resized_frame = current_frame.resize((_tw, _th), Image.Resampling.LANCZOS)
                                if resized_frame.mode != 'RGBA':
                                    resized_frame = resized_frame.convert('RGBA')
                                
                                return _render_frame_animated(
                                    _bg, resized_frame, _px, _py, _tw, _th, img_width, img_height,
                                    _ti, _si, t,
                                    entrance_duration=ENTRANCE_DUR,
                                    hold_with_text_start=HOLD_NO_TEXT,
                                    anim_type=_anim,
                                    title_slide_entrance=_tse,
                                    clip_duration=_dur,
                                    summary_scroll_mode=_ssm,
                                    scroll_viewport_height=_slot,
                                    clip_fps=FPS,
                                )
                            
                            clip = VideoClip(make_gif_frame_func, duration=clip_duration).with_fps(FPS)
                            clips.append(clip)
                            first_clip_already_placed = True
                            logger.info(f"   🎬 GIF动画片段 {idx} 添加成功")
                            if anim == 'scroll_up':
                                _scroll_phase = max(0.0, float(clip_duration) - float(ENTRANCE_DUR))
                                _phase_cap = max(0.05, _scroll_phase)
                                _scroll_dist = _scroll_up_effective_distance(
                                    target_h, available, _scroll_phase
                                )
                                if available is not None and available > 0:
                                    _overflow_px = max(0, target_h - available)
                                else:
                                    _overflow_px = max(1, int(target_h * 0.28))
                                _max_travel_px = SCROLL_UP_PIXELS_PER_SEC * _phase_cap
                                _avg_px_s = (
                                    float(_scroll_dist) / _scroll_phase
                                    if _scroll_phase > 1e-9
                                    else 0.0
                                )
                                logger.info(
                                    "[animated_video_gif] scroll_up 片段 {}: 成片时长={:.3f}s | 入场={:.3f}s | "
                                    "上滑阶段时长={:.3f}s | 缩放后图 {}x{} | 可视槽高={} | overflow≈{}px | "
                                    "匀速上限={} px/s | 速度×阶段位移上限={:.1f}px | 实际上移总位移={}px | 平均速度≈{:.1f} px/s",
                                    idx,
                                    clip_duration,
                                    ENTRANCE_DUR,
                                    _scroll_phase,
                                    target_w,
                                    target_h,
                                    available,
                                    _overflow_px,
                                    SCROLL_UP_PIXELS_PER_SEC,
                                    _max_travel_px,
                                    _scroll_dist,
                                    _avg_px_s,
                                )

                            # 保存预览帧（取中间帧）
                            mid_frame_index = len(gif_frames) // 2
                            mid_frame = Image.fromarray(gif_frames[mid_frame_index])
                            mid_frame_resized = mid_frame.resize((target_w, target_h), Image.Resampling.LANCZOS)
                            if mid_frame_resized.mode != 'RGBA':
                                mid_frame_resized = mid_frame_resized.convert('RGBA')
                            
                            preview = _render_frame_animated(
                                bg_template, mid_frame_resized, paste_x, final_paste_y,
                                target_w, target_h, img_width, img_height,
                                title_info, summary_info, clip_duration,
                                entrance_duration=ENTRANCE_DUR, hold_with_text_start=HOLD_NO_TEXT,
                                anim_type=anim,
                                title_slide_entrance=_tse,
                                clip_duration=clip_duration,
                                summary_scroll_mode=_ssm,
                                scroll_viewport_height=available,
                                clip_fps=FPS,
                            )
                            preview_path = output_dir / f"preview_{idx:02d}.png"
                            Image.fromarray(preview).save(preview_path, quality=95)
                            logger.info(f"   🖼️ 预览帧保存成功: {preview_path}")
                            
                            continue  # 跳过下面的静态图片处理
                        else:
                            logger.warning(f"   ⚠️ GIF帧提取失败，回退到静态图片处理: {img_path}")
                        # 继续使用静态图片处理逻辑
                
                # 原有的静态图片处理逻辑
                user_img_path = Path(img_path.lstrip('/'))
                if not user_img_path.exists():
                    logger.warning(f"图片不存在，跳过: {img_path}")
                    continue

                user_img = Image.open(user_img_path)
                if user_img.mode != 'RGBA':
                    user_img = user_img.convert('RGBA')

                # 缩放
                target_w = img_width - 40
                ratio = target_w / user_img.width
                target_h = int(user_img.height * ratio)
                # 取消60%高度限制，允许图片延伸到背景底部
                # max_h = int(img_height * 0.6)
                # if target_h > max_h:
                #     target_h = max_h
                #     ratio = target_h / user_img.height
                #     target_w = int(user_img.width * ratio)

                user_img_resized = user_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

                use_first_static_card_effect = (
                    not first_static_image_effect_applied
                    and getattr(request, "first_image_effect", None) == "side_flip_rounded"
                )
                if use_first_static_card_effect:
                    user_img_resized = _apply_side_flip_rounded_card(
                        user_img_resized,
                        angle_degrees=30.0,
                    )
                    target_w, target_h = user_img_resized.size
                    first_static_image_effect_applied = True
                    logger.info(
                        f"GitHub首张静态图特效: 30度侧翻圆角卡片, 处理后尺寸={target_w}x{target_h}"
                    )

                paste_x = (img_width - target_w) // 2
                # 图片在标题和摘要之间居中
                available = summary_start_y - 40 - (title_start_y + title_height + 30)
                final_paste_y = title_start_y + title_height + 30 + (available - target_h) // 2
                final_paste_y = max(title_start_y + title_height + 30, final_paste_y)

                # 使用用户配置的时长，如果没有则使用默认值
                clip_duration = img_duration if img_duration is not None else DEFAULT_CLIP_DURATION
                                
                logger.info(f"片段 {idx}: 生成 {clip_duration:.1f}s 动画，图片 {target_w}x{target_h}")
                
                # ⚠️ 智能动画选择：如果图片高度过大，自动使用向上滚动
                # 使用原始图片高度来判断（未缩放前）
                orig_img_height = user_img.height
                img_height_ratio = orig_img_height / img_height  # 原始图片高度占屏幕比例
                
                # 每张图使用不同的动画（打乱后循环分配）
                anim = anim_queue.pop(0)
                
                if use_first_static_card_effect:
                    anim = 'fade_in'
                    logger.info(f"片段 {idx} 使用 GitHub 首图侧翻圆角卡片特效，动画固定为 fade_in")
                elif img_height_ratio > 0.7:  # 如果原始图片高度超过屏幕 70%
                    anim = 'scroll_up'  # 强制使用向上滚动
                    logger.info(f"片段 {idx} 检测到高图（原始高度 {orig_img_height}px, 占比 {img_height_ratio:.1%}），自动使用 scroll_up 动画")
                else:
                    logger.info(f"片段 {idx} 动画类型：{anim}")
                
                # 检查是否需要放大效果（从 frame_info 中读取）
                has_zoom = img_data.get('has_zoom', False)
                zoom_start = img_data.get('zoom_start_scale', 1.0)
                zoom_end = img_data.get('zoom_end_scale', 1.15)
                
                # ⚠️ 智能调整：如果使用了 scroll_up 动画（高图），禁用放大效果
                if use_first_static_card_effect:
                    has_zoom = True
                    zoom_start = 1.0
                    zoom_end = 1.18
                    logger.info(f"片段 {idx} 首图卡片特效启用渐进放大：{zoom_start} -> {zoom_end}")
                elif anim == 'scroll_up':
                    has_zoom = False  # 高图不使用放大效果，改为向上滚动
                    logger.info(f"片段 {idx} 高图使用 scroll_up 动画，已禁用放大效果")
                else:
                    # 首段多为 GitHub 主页截图；后续片段缩放区间略加大，动效更明显
                    if idx == 1 and has_zoom:
                        zoom_end = min(1.48, float(zoom_end) + 0.5)
                        zoom_start = max(1, float(zoom_start))
                    if idx >= 2 and has_zoom:
                        zoom_end = min(1.48, float(zoom_end) )
                        zoom_start = max(0.88, float(zoom_start) - 0.03)
                    
                    if has_zoom:
                        logger.info(f"片段 {idx} 启用放大效果：{zoom_start} -> {zoom_end}")
                
                # 只有第一个片段启用摘要滚动效果
                enable_summary_scroll = (idx == 1)
                logger.info(f"片段 {idx} 摘要滚动：{'开启' if enable_summary_scroll else '关闭'}")
                if anim == 'scroll_up':
                    _scroll_phase = max(0.0, float(clip_duration) - float(ENTRANCE_DUR))
                    _phase_cap = max(0.05, _scroll_phase)
                    _scroll_dist = _scroll_up_effective_distance(
                        target_h, available, _scroll_phase
                    )
                    if available is not None and available > 0:
                        _overflow_px = max(0, target_h - available)
                    else:
                        _overflow_px = max(1, int(target_h * 0.28))
                    _max_travel_px = SCROLL_UP_PIXELS_PER_SEC * _phase_cap
                    _avg_px_s = (
                        float(_scroll_dist) / _scroll_phase
                        if _scroll_phase > 1e-9
                        else 0.0
                    )
                    logger.info(
                        "[animated_video_static] scroll_up 片段 {}: 成片时长={:.3f}s | 入场={:.3f}s | "
                        "上滑阶段时长={:.3f}s | 缩放后图 {}x{} | 可视槽高={} | overflow≈{}px | "
                        "匀速上限={} px/s | 速度×阶段位移上限={:.1f}px | 实际上移总位移={}px | 平均速度≈{:.1f} px/s",
                        idx,
                        clip_duration,
                        ENTRANCE_DUR,
                        _scroll_phase,
                        target_w,
                        target_h,
                        available,
                        _overflow_px,
                        SCROLL_UP_PIXELS_PER_SEC,
                        _max_travel_px,
                        _scroll_dist,
                        _avg_px_s,
                    )

                # 使用 make_frame 创建动画片段
                def make_frame_func(t, _bg=bg_template, _img=user_img_resized,
                                    _px=paste_x, _py=final_paste_y,
                                    _tw=target_w, _th=target_h,
                                    _ti=title_info, _si=summary_info,
                                    _anim=anim, _zoom=has_zoom,
                                    _zs=zoom_start, _ze=zoom_end,
                                    _scroll=enable_summary_scroll,
                                    _tse=_tse,
                                    _slot=available):
                    return _render_frame_animated(
                        _bg, _img, _px, _py, _tw, _th, img_width, img_height,
                        _ti, _si, t,
                        entrance_duration=ENTRANCE_DUR,
                        hold_with_text_start=HOLD_NO_TEXT,
                        anim_type=_anim,
                        zoom_effect=_zoom,
                        zoom_start_scale=_zs,
                        zoom_end_scale=_ze,
                        clip_duration=clip_duration,
                        summary_scroll=_scroll,
                        summary_scroll_mode=_ssm,
                        summary_segments=None,  # 不再使用分段
                        title_slide_entrance=_tse,
                        scroll_viewport_height=_slot,
                        clip_fps=FPS,
                    )
                
                clip = VideoClip(make_frame_func, duration=clip_duration).with_fps(FPS)
                clips.append(clip)
                first_clip_already_placed = True
                
                # 同时保存一张静态预览帧（用于前端显示）
                preview = _render_frame_animated(
                    bg_template, user_img_resized, paste_x, final_paste_y,
                    target_w, target_h, img_width, img_height,
                    title_info, summary_info, clip_duration,
                    entrance_duration=ENTRANCE_DUR, hold_with_text_start=HOLD_NO_TEXT,
                    anim_type=anim,
                    zoom_effect=has_zoom,
                    zoom_start_scale=zoom_start,
                    zoom_end_scale=zoom_end,
                    clip_duration=clip_duration,
                    summary_scroll=enable_summary_scroll,
                    summary_scroll_mode=_ssm,
                    summary_segments=None,  # 不再使用分段
                    title_slide_entrance=_tse,
                    scroll_viewport_height=available,
                    clip_fps=FPS,
                )
                preview_path = output_dir / f"preview_{idx:02d}.png"
                Image.fromarray(preview).save(preview_path, quality=95)

            except Exception as e:
                logger.error(f"处理图片 {idx} 失败: {e}")
                import traceback
                traceback.print_exc()
                continue

        if not clips:
            return JSONResponse(status_code=500,
                                content={"success": False, "message": "所有图片处理失败"})

        # 拼接
        final_clip = concatenate_videoclips(clips, method="compose")
        video_duration = final_clip.duration
        logger.info(f"动画视频总时长: {video_duration:.2f}s, {len(clips)} 个片段")

        # 音频
        audio = None
        audio_path = request.audio_path.lstrip('/') if request.audio_path else None
        if audio_path:
            audio_file = Path(audio_path)
            if audio_file.exists():
                audio = AudioFileClip(str(audio_file))
                original_duration = audio.duration
                logger.info(f"🎵 加载音频文件: {audio_path}")
                logger.info(f"   原始时长: {original_duration:.2f}秒")
                
                speed = 1.1
                audio = audio.with_speed_scaled(speed)
                new_duration = audio.duration
                logger.info(f"   🚀 应用{speed}倍速")
                logger.info(f"   加速后时长: {new_duration:.2f}秒")
                logger.info(f"   时间压缩: {(original_duration - new_duration) / original_duration * 100:.1f}%")
                if audio.duration < video_duration:
                    audio = concatenate_audioclips([audio] * (int(video_duration / audio.duration) + 1))
                audio = audio.subclipped(0, video_duration)
                final_clip = final_clip.with_audio(audio)
                logger.info("背景音乐已添加")

        # 输出
        video_dir = Path("data/videos")
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = video_dir / f"animated_{timestamp}.mp4"

        final_clip.write_videofile(
            str(video_path), fps=FPS, codec='libx264',
            audio_codec='aac' if audio else None,
            temp_audiofile='temp-audio.m4a' if audio else None,
            remove_temp=True, logger=None
        )

        final_clip.close()
        if audio:
            audio.close()
        
        # 关闭所有视频片段以释放资源
        for clip in clips:
            if hasattr(clip, 'close'):
                try:
                    clip.close()
                    logger.debug(f"已关闭视频片段: {type(clip).__name__}")
                except Exception as e:
                    logger.warning(f"关闭视频片段时出错: {e}")
        
        logger.info("所有资源已清理完成")
        
        rel = str(video_path.relative_to(Path("."))).replace("\\", "/")
        size_mb = video_path.stat().st_size / (1024 * 1024)
        logger.success(f"动画视频生成成功: {video_path} ({size_mb:.2f}MB)")
                
        # 预览帧列表
        previews = []
        for f in sorted(output_dir.glob("preview_*.png")):
            previews.append("/" + str(f.relative_to(Path("."))).replace(chr(92), "/"))
                
        return {
            "success": True,
            "message": f"动画视频生成成功，共 {len(clips)} 个片段",
            "video_path": f"/{rel}",
            "preview_frames": previews,
            "duration": video_duration,
            "file_size_mb": round(size_mb, 2),
            "output_dir": str(output_dir.relative_to(Path("."))).replace("\\", "/")
        }
            
    except Exception as e:
        logger.error(f"动画视频生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"动画视频生成失败: {str(e)}")


@router.post("/create-animated-video")
async def create_animated_video(request: CreateAnimatedVideoRequest):
    """一步生成带小图入场动画效果的视频（跳过静态关键帧步骤）。"""
    return await asyncio.to_thread(_create_animated_video_blocking, request)


@router.post("/create-user-video")
async def create_user_video(
    title: str = Form(default=""),
    subtitle: str = Form(default=""),
    images: str = Form(...),  # JSON array string of image paths
    audio_path: str = Form(default="static/music/background.mp3"),
    clip_duration: float = Form(default=3.0),
    effect: str = Form(default="none"),  # none/gold_sparkle/snowfall/bokeh/firefly/bubble
):
    """用户上传图片生成视频（可选标题，8种入场动画，背景音乐）"""
    try:
        import json as _json
        
        # 参数验证
        if not images or not images.strip():
            return JSONResponse(status_code=400,
                                content={"success": False, "message": "图片列表不能为空"})
        
        try:
            image_list = _json.loads(images)
        except _json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}, 输入内容: {images[:100]}...")
            return JSONResponse(status_code=400,
                                content={"success": False, "message": "图片列表格式错误"})
        
        if not isinstance(image_list, list) or not image_list:
            return JSONResponse(status_code=400,
                                content={"success": False, "message": "请至少上传一张图片"})

        from moviepy import concatenate_videoclips, AudioFileClip, VideoClip, concatenate_audioclips

        FPS = 24
        ENTRANCE_DUR = 0.7       # 入场动画时长

        # ===== 第一轮：扫描所有图片，确定画布尺寸（取最大宽高） =====
        valid_images = []
        max_w, max_h = 0, 0
        for img_path in image_list:
            try:
                p = Path(img_path.lstrip('/'))
                if not p.exists():
                    continue
                im = Image.open(p)
                valid_images.append((img_path, im.width, im.height))
                max_w = max(max_w, im.width)
                max_h = max(max_h, im.height)
                im.close()
            except Exception:
                continue

        if not valid_images:
            return JSONResponse(status_code=400,
                                content={"success": False, "message": "没有可用的图片"})

        # 画布尺寸：最大图片的宽高（确保是偶数，h264要求）
        canvas_w = max_w if max_w % 2 == 0 else max_w + 1
        canvas_h = max_h if max_h % 2 == 0 else max_h + 1
        logger.info(f"用户视频画布尺寸: {canvas_w}x{canvas_h}, 共 {len(valid_images)} 张有效图片")

        # 黑色背景模板
        bg_template = Image.new('RGB', (canvas_w, canvas_h), (0, 0, 0))

        # 如果有标题，预计算
        title_info = None
        summary_info = None
        if title.strip():
            title_font, subtitle_font, summary_font = _load_fonts()
            margin = int(canvas_w * 0.06)
            text_width = canvas_w - 2 * margin
            temp_draw = ImageDraw.Draw(bg_template.copy())
            main_title_lines = _wrap_text(title.strip(), title_font, text_width, temp_draw)
            sub_title_lines = _wrap_text(subtitle.strip(), subtitle_font, text_width, temp_draw) if subtitle.strip() else []

            main_title_height = sum(
                temp_draw.textbbox((0, 0), l, font=title_font)[3] -
                temp_draw.textbbox((0, 0), l, font=title_font)[1] + 18
                for l in main_title_lines
            )
            title_start_y = int(canvas_h * 0.03)  # 标题靠顶部

            title_info = (title_font, subtitle_font, main_title_lines, sub_title_lines,
                          title_start_y, main_title_height, margin, text_width)
            summary_info = (summary_font if title.strip() else None, [], 0)

        clips = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("data/generated") / f"user_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 动画队列
        import random
        all_anim_types = ['zoom_in', 'zoom_out', 'unfold', 'scroll_up',
                          'slide_left', 'slide_right', 'fade_in', 'drop_bounce']
        random.shuffle(all_anim_types)
        anim_queue = [all_anim_types[i % len(all_anim_types)] for i in range(len(valid_images))]

        first_clip_already_placed = False
        for idx, (img_path, orig_w, orig_h) in enumerate(valid_images, 1):
            try:
                _tse = not first_clip_already_placed
                _ap2 = Path(img_path.lstrip('/'))
                is_gif = _ap2.is_file() and gif_processor.is_animation_raster(str(_ap2))
                
                if is_gif:
                    # 处理 GIF / 动画 WebP
                    logger.info(f"🔄 处理 GIF/动画 WebP: {img_path}")
                    logger.info(f"   素材路径: {img_path}")
                    logger.info(f"   目标时长: {clip_duration}秒")
                    
                    # 修复路径问题 - 去掉开头的斜杠
                    actual_gif_path = img_path.lstrip('/')
                    logger.info(f"   实际路径: {actual_gif_path}")
                    
                    # 检查文件是否存在
                    if not Path(actual_gif_path).exists():
                        logger.error(f"   ❌ 文件不存在: {actual_gif_path}")
                        logger.warning(f"   ⚠️ 回退到静态图片处理: {img_path}")
                        # 继续使用静态图片处理逻辑
                    else:
                        logger.info(f"   ✅ 文件存在")

                        gif_frames = gif_processor.extract_gif_frames(actual_gif_path)
                        
                        if gif_frames and len(gif_frames) > 0:
                            logger.info(f"   🎬 提取到 {len(gif_frames)} 帧动画")
                            
                            # 将第一帧作为基础图片进行处理
                            first_frame = Image.fromarray(gif_frames[0])
                            if first_frame.mode != 'RGBA':
                                first_frame = first_frame.convert('RGBA')
                            
                            # 图片原始大小居中放置（不缩放）
                            target_w, target_h = first_frame.width, first_frame.height
                            paste_x = (canvas_w - target_w) // 2
                            paste_y = (canvas_h - target_h) // 2
                            
                            anim = anim_queue.pop(0)
                            logger.info(f"用户视频片段 {idx}: 动画={anim}, GIF帧数={len(gif_frames)}, 尺寸={target_w}x{target_h}")
                            
                            _effect = effect
                            _clip_dur = clip_duration
                            _seed = idx
                            
                            # 创建GIF动画make_frame函数
                            def make_gif_frame_func(t, _bg=bg_template, _frames=gif_frames,
                                                   _px=paste_x, _py=paste_y,
                                                   _tw=target_w, _th=target_h,
                                                   _ti=title_info, _si=summary_info,
                                                   _anim=anim, _eff=_effect, _sd=_seed,
                                                   _cd=_clip_dur, _dur=clip_duration,
                                                   _tse=_tse):
                                # 计算当前应该显示哪一帧
                                total_frames = len(_frames)
                                current_frame_index = int((t / _dur) * total_frames) % total_frames
                                current_frame = Image.fromarray(_frames[current_frame_index])
                                
                                # 保持原始尺寸
                                if current_frame.mode != 'RGBA':
                                    current_frame = current_frame.convert('RGBA')
                                
                                frame = _render_frame_animated(
                                    _bg, current_frame, _px, _py, _tw, _th, canvas_w, canvas_h,
                                    _ti, _si, t,
                                    entrance_duration=ENTRANCE_DUR,
                                    hold_with_text_start=ENTRANCE_DUR,
                                    anim_type=_anim,
                                    title_slide_entrance=_tse,
                                    clip_duration=_cd,
                                    clip_fps=FPS,
                                )
                                return _apply_video_effect(frame, t, _eff, canvas_w, canvas_h, _cd, seed=_sd)
                            
                            clip = VideoClip(make_gif_frame_func, duration=clip_duration).with_fps(FPS)
                            clips.append(clip)
                            first_clip_already_placed = True
                            logger.info(f"   🎬 GIF动画片段 {idx} 添加成功")
                            if anim == 'scroll_up':
                                _uv_slot = None
                                _scroll_phase = max(0.0, float(clip_duration) - float(ENTRANCE_DUR))
                                _phase_cap = max(0.05, _scroll_phase)
                                _scroll_dist = _scroll_up_effective_distance(
                                    target_h, _uv_slot, _scroll_phase
                                )
                                _overflow_px = max(1, int(target_h * 0.28))
                                _max_travel_px = SCROLL_UP_PIXELS_PER_SEC * _phase_cap
                                _avg_px_s = (
                                    float(_scroll_dist) / _scroll_phase
                                    if _scroll_phase > 1e-9
                                    else 0.0
                                )
                                logger.info(
                                    "[user_video_gif] scroll_up 片段 {}: 成片时长={:.3f}s | 入场={:.3f}s | "
                                    "上滑阶段时长={:.3f}s | 缩放后图 {}x{} | 可视槽高={} | overflow≈{}px | "
                                    "匀速上限={} px/s | 速度×阶段位移上限={:.1f}px | 实际上移总位移={}px | 平均速度≈{:.1f} px/s",
                                    idx,
                                    clip_duration,
                                    ENTRANCE_DUR,
                                    _scroll_phase,
                                    target_w,
                                    target_h,
                                    _uv_slot,
                                    _overflow_px,
                                    SCROLL_UP_PIXELS_PER_SEC,
                                    _max_travel_px,
                                    _scroll_dist,
                                    _avg_px_s,
                                )

                            # 保存预览帧（取中间帧）
                            mid_frame_index = len(gif_frames) // 2
                            mid_frame = Image.fromarray(gif_frames[mid_frame_index])
                            if mid_frame.mode != 'RGBA':
                                mid_frame = mid_frame.convert('RGBA')

                            preview_raw = _render_frame_animated(
                                bg_template, mid_frame, paste_x, paste_y,
                                target_w, target_h, canvas_w, canvas_h,
                                title_info, summary_info, clip_duration,
                                entrance_duration=ENTRANCE_DUR, hold_with_text_start=ENTRANCE_DUR,
                                anim_type=anim,
                                title_slide_entrance=_tse,
                                clip_duration=clip_duration,
                                clip_fps=FPS,
                            )
                            preview = _apply_video_effect(preview_raw, clip_duration * 0.5, effect, canvas_w, canvas_h, clip_duration, seed=idx)
                            preview_path = output_dir / f"preview_{idx:02d}.png"
                            Image.fromarray(preview).save(preview_path, quality=95)
                            logger.info(f"   🖼️ 预览帧保存成功: {preview_path}")
                            
                            continue  # 跳过下面的静态图片处理
                        else:
                            logger.warning(f"   ⚠️ GIF帧提取失败，回退到静态图片处理: {img_path}")
                        # 继续使用静态图片处理逻辑
                
                # 原有的静态图片处理逻辑
                user_img = Image.open(Path(img_path.lstrip('/')))
                if user_img.mode != 'RGBA':
                    user_img = user_img.convert('RGBA')

                # 图片原始大小居中放置（不缩放）
                target_w, target_h = user_img.width, user_img.height
                paste_x = (canvas_w - target_w) // 2
                paste_y = (canvas_h - target_h) // 2

                anim = anim_queue.pop(0)
                logger.info(f"用户视频片段 {idx}: 动画={anim}, 图片={target_w}x{target_h}, 偏移=({paste_x},{paste_y})")
                if anim == 'scroll_up':
                    _uv_slot = None
                    _scroll_phase = max(0.0, float(clip_duration) - float(ENTRANCE_DUR))
                    _phase_cap = max(0.05, _scroll_phase)
                    _scroll_dist = _scroll_up_effective_distance(
                        target_h, _uv_slot, _scroll_phase
                    )
                    _overflow_px = max(1, int(target_h * 0.28))
                    _max_travel_px = SCROLL_UP_PIXELS_PER_SEC * _phase_cap
                    _avg_px_s = (
                        float(_scroll_dist) / _scroll_phase
                        if _scroll_phase > 1e-9
                        else 0.0
                    )
                    logger.info(
                        "[user_video_static] scroll_up 片段 {}: 成片时长={:.3f}s | 入场={:.3f}s | "
                        "上滑阶段时长={:.3f}s | 缩放后图 {}x{} | 可视槽高={} | overflow≈{}px | "
                        "匀速上限={} px/s | 速度×阶段位移上限={:.1f}px | 实际上移总位移={}px | 平均速度≈{:.1f} px/s",
                        idx,
                        clip_duration,
                        ENTRANCE_DUR,
                        _scroll_phase,
                        target_w,
                        target_h,
                        _uv_slot,
                        _overflow_px,
                        SCROLL_UP_PIXELS_PER_SEC,
                        _max_travel_px,
                        _scroll_dist,
                        _avg_px_s,
                    )

                _effect = effect
                _clip_dur = clip_duration
                _seed = idx  # 每段粒子不同

                def make_frame_func(t, _bg=bg_template, _img=user_img,
                                    _px=paste_x, _py=paste_y,
                                    _tw=target_w, _th=target_h,
                                    _ti=title_info, _si=summary_info,
                                    _anim=anim, _eff=_effect, _sd=_seed,
                                    _cd=_clip_dur,
                                    _tse=_tse):
                    frame = _render_frame_animated(
                        _bg, _img, _px, _py, _tw, _th, canvas_w, canvas_h,
                        _ti, _si, t,
                        entrance_duration=ENTRANCE_DUR,
                        hold_with_text_start=ENTRANCE_DUR,
                        anim_type=_anim,
                        title_slide_entrance=_tse,
                        clip_duration=_cd,
                        clip_fps=FPS,
                    )
                    return _apply_video_effect(frame, t, _eff, canvas_w, canvas_h, _cd, seed=_sd)

                clip = VideoClip(make_frame_func, duration=clip_duration).with_fps(FPS)
                clips.append(clip)
                first_clip_already_placed = True

                # 保存预览帧（带特效）
                preview_raw = _render_frame_animated(
                    bg_template, user_img, paste_x, paste_y,
                    target_w, target_h, canvas_w, canvas_h,
                    title_info, summary_info, clip_duration,
                    entrance_duration=ENTRANCE_DUR, hold_with_text_start=ENTRANCE_DUR,
                    anim_type=anim,
                    title_slide_entrance=_tse,
                    clip_duration=clip_duration,
                    clip_fps=FPS,
                )
                preview = _apply_video_effect(preview_raw, clip_duration * 0.5, effect, canvas_w, canvas_h, clip_duration, seed=idx)
                preview_path = output_dir / f"preview_{idx:02d}.png"
                Image.fromarray(preview).save(preview_path, quality=95)

            except Exception as e:
                logger.error(f"处理图片 {idx} 失败: {e}")
                import traceback
                traceback.print_exc()
                continue

        if not clips:
            return JSONResponse(status_code=500,
                                content={"success": False, "message": "所有图片处理失败"})

        final_clip = concatenate_videoclips(clips, method="compose")
        video_duration = final_clip.duration
        logger.info(f"用户视频总时长: {video_duration:.2f}s, {len(clips)} 个片段")

        # 音频
        audio = None
        _audio_path = audio_path.lstrip('/') if audio_path else None
        if _audio_path:
            audio_file = Path(_audio_path)
            if audio_file.exists():
                audio = AudioFileClip(str(audio_file))
                original_duration = audio.duration
                logger.info(f"🎵 加载音频文件: {audio_path}")
                logger.info(f"   原始时长: {original_duration:.2f}秒")
                
                speed = 1.1
                audio = audio.with_speed_scaled(speed)
                new_duration = audio.duration
                logger.info(f"   🚀 应用{speed}倍速")
                logger.info(f"   加速后时长: {new_duration:.2f}秒")
                logger.info(f"   时间压缩: {(original_duration - new_duration) / original_duration * 100:.1f}%")
                if audio.duration < video_duration:
                    audio = concatenate_audioclips([audio] * (int(video_duration / audio.duration) + 1))
                audio = audio.subclipped(0, video_duration)
                final_clip = final_clip.with_audio(audio)
                logger.info("用户视频背景音乐已添加")

        video_dir = Path("data/videos")
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = video_dir / f"user_video_{timestamp}.mp4"

        final_clip.write_videofile(
            str(video_path), fps=FPS, codec='libx264',
            audio_codec='aac' if audio else None,
            temp_audiofile='temp-audio.m4a' if audio else None,
            remove_temp=True, logger=None
        )

        final_clip.close()
        if audio:
            audio.close()
        
        # 关闭所有视频片段以释放资源
        for clip in clips:
            if hasattr(clip, 'close'):
                try:
                    clip.close()
                    logger.debug(f"已关闭视频片段: {type(clip).__name__}")
                except Exception as e:
                    logger.warning(f"关闭视频片段时出错: {e}")
        
        logger.info("所有资源已清理完成")

        rel = str(video_path.relative_to(Path("."))).replace("\\", "/")
        size_mb = video_path.stat().st_size / (1024 * 1024)
        logger.success(f"用户视频生成成功: {video_path} ({size_mb:.2f}MB)")

        previews = []
        for f in sorted(output_dir.glob("preview_*.png")):
            previews.append(f"/{str(f.relative_to(Path('.'))).replace(chr(92), '/')}")

        return {
            "success": True,
            "message": f"视频生成成功，共 {len(clips)} 个片段",
            "video_path": f"/{rel}",
            "preview_frames": previews,
            "duration": video_duration,
            "file_size_mb": round(size_mb, 2)
        }

    except Exception as e:
        logger.error(f"用户视频生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")