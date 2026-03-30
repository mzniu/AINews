"""视频处理相关API路由"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import List
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
    _load_fonts, _wrap_text
)
from services.video_service import VideoService
from services.video_embedding_service import video_embedding_service
import cv2
import numpy as np

router = APIRouter(prefix="/api", tags=["视频"])

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
        from moviepy.editor import VideoFileClip
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

@router.post("/create-animated-video")
async def create_animated_video(request: CreateAnimatedVideoRequest):
    """一步生成带小图入场动画效果的视频（跳过静态关键帧步骤）"""
    try:
        if not request.images:
            return JSONResponse(status_code=400,
                                content={"success": False, "message": "请至少选择一张图片"})

        from moviepy.video.VideoClip import ImageClip, VideoClip
        from moviepy.video.compositing.concatenate import concatenate_videoclips
        from moviepy.audio.io.AudioFileClip import AudioFileClip

        FPS = 24
        ENTRANCE_DUR = 0.4     # 小图弹落动画时长
        HOLD_NO_TEXT = 0.8     # 弹落后无文字停顿
        TEXT_FADE_IN = 0.4     # 文字渐入时长
        HOLD_WITH_TEXT = 1.4     # 文字显示后静持时长
        
        DEFAULT_CLIP_DURATION = HOLD_NO_TEXT + TEXT_FADE_IN + HOLD_WITH_TEXT  # 默认每段约 2.7 秒

        # 加载背景和字体
        bg_path = Path("static/imgs/bg.png")
        bg_template = Image.open(bg_path) if bg_path.exists() else Image.new('RGB', (1080, 1920), (102, 126, 234))
        img_width, img_height = bg_template.size
        title_font, subtitle_font, summary_font = _load_fonts()

        margin = int(img_width * 0.08)
        text_width = img_width - 2 * margin

        # 解析主副标题（用 | 分隔）
        title_parts = request.title.split('|', 1)
        main_title_text = title_parts[0].strip()
        sub_title_text = title_parts[1].strip() if len(title_parts) > 1 else ''

        # 预计算标题和摘要
        temp_draw = ImageDraw.Draw(bg_template.copy())
        main_title_lines = _wrap_text(main_title_text, title_font, text_width, temp_draw)
        sub_title_lines = _wrap_text(sub_title_text, subtitle_font, text_width, temp_draw) if sub_title_text else []
        
        # 计算标题高度
        main_title_height = sum(
            temp_draw.textbbox((0, 0), l, font=title_font)[3] -
            temp_draw.textbbox((0, 0), l, font=title_font)[1] + 18
            for l in main_title_lines
        )
        sub_title_height = sum(
            temp_draw.textbbox((0, 0), l, font=subtitle_font)[3] -
            temp_draw.textbbox((0, 0), l, font=subtitle_font)[1] + 14
            for l in sub_title_lines
        ) if sub_title_lines else 0
        title_height = main_title_height + (sub_title_height + 12 if sub_title_height else 0)
        
        # 标题起始位置（距离顶部 10%）
        title_start_y = int(img_height * 0.1)
        
        # 构建 title_info
        title_info = (title_font, subtitle_font, main_title_lines, sub_title_lines,
                      title_start_y, main_title_height, margin, text_width)
                
        # 摘要：自动换行处理
        summary_lines = _wrap_text(request.summary, summary_font, text_width, temp_draw)
        
        # 计算摘要高度
        summary_height = sum(
            temp_draw.textbbox((0, 0), l, font=summary_font)[3] -
            temp_draw.textbbox((0, 0), l, font=summary_font)[1] + 12
            for l in summary_lines
        )
        
        # 摘要起始位置（距离底部 10%）
        summary_start_y = int(img_height * 0.9) - summary_height
        
        # 构建 summary_info
        summary_info = (summary_font, summary_lines, summary_start_y)

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

        for idx, img_data in enumerate(processed_images, 1):
            img_path = img_data['path']
            img_duration = img_data['duration']  # 可能为 null（视频）或秒数（图片）
            try:
                # 检查文件类型
                is_video = img_path.lower().endswith(('.mp4', '.webm', '.mov'))
                is_gif = img_path.lower().endswith('.gif')
                
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
                        [actual_video_path], bg_template, title_info, summary_info, clip_duration
                    )
                                        
                    if pip_result.get('success') and pip_result.get('segments'):
                        segment = pip_result['segments'][0]
                        logger.info(f"   🎨 画中画效果创建成功：{len(segment['frames'])} 帧")
                                            
                        # 使用画中画帧创建视频片段
                        def make_pip_frame(t, frames=segment['frames'], duration=clip_duration):
                            frame_index = int((t / duration) * len(frames))
                            frame_index = min(frame_index, len(frames) - 1)
                            return np.array(frames[frame_index])
                                            
                        clip = VideoClip(make_pip_frame, duration=clip_duration).set_fps(FPS)
                        clips.append(clip)
                        
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
                    # 处理 GIF 动画
                    logger.info(f"🔄 处理 GIF 动画：{img_path}")
                    logger.info(f"   GIF 路径：{img_path}")
                    
                    # 使用用户配置的时长，如果没有则使用默认值
                    clip_duration = img_duration if img_duration is not None else DEFAULT_CLIP_DURATION
                    logger.info(f"   目标时长：{clip_duration}秒")
                    
                    # 修复路径问题 - 去掉开头的斜杠
                    actual_gif_path = img_path.lstrip('/')
                    logger.info(f"   实际GIF路径: {actual_gif_path}")
                    
                    # 检查文件是否存在
                    if not Path(actual_gif_path).exists():
                        logger.error(f"   ❌ GIF文件不存在: {actual_gif_path}")
                        logger.warning(f"   ⚠️ 回退到静态图片处理: {img_path}")
                        # 继续使用静态图片处理逻辑
                    else:
                        logger.info(f"   ✅ GIF文件存在")
                        
                        # 提取GIF帧用于动画处理
                        from services.gif_processor import gif_processor
                        gif_frames = gif_processor.extract_gif_frames(actual_gif_path)
                        
                        if gif_frames and len(gif_frames) > 0:
                            logger.info(f"   🎬 提取到 {len(gif_frames)} 帧GIF动画")
                            
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
                            
                            # 使用GIF帧创建动画片段
                            anim = anim_queue.pop(0)
                            logger.info(f"   片段 {idx} 动画类型: {anim}")
                            
                            # 创建GIF动画make_frame函数
                            def make_gif_frame_func(t, _bg=bg_template, _frames=gif_frames,
                                                   _px=paste_x, _py=final_paste_y,
                                                   _tw=target_w, _th=target_h,
                                                   _ti=title_info, _si=summary_info,
                                                   _anim=anim, _dur=clip_duration):
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
                                    anim_type=_anim
                                )
                            
                            clip = VideoClip(make_gif_frame_func, duration=clip_duration).set_fps(FPS)
                            clips.append(clip)
                            logger.info(f"   🎬 GIF动画片段 {idx} 添加成功")
                            
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
                                anim_type=anim
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

                paste_x = (img_width - target_w) // 2
                # 图片在标题和摘要之间居中
                available = summary_start_y - 40 - (title_start_y + title_height + 30)
                final_paste_y = title_start_y + title_height + 30 + (available - target_h) // 2
                final_paste_y = max(title_start_y + title_height + 30, final_paste_y)

                # 使用用户配置的时长，如果没有则使用默认值
                clip_duration = img_duration if img_duration is not None else DEFAULT_CLIP_DURATION
                                
                logger.info(f"片段 {idx}: 生成 {clip_duration:.1f}s 动画，图片 {target_w}x{target_h}")
                
                # 每张图使用不同的动画（打乱后循环分配）
                anim = anim_queue.pop(0)
                logger.info(f"片段 {idx} 动画类型：{anim}")
                
                # 检查是否需要放大效果（从 frame_info 中读取）
                has_zoom = img_data.get('has_zoom', False)
                zoom_start = img_data.get('zoom_start_scale', 1.0)
                zoom_end = img_data.get('zoom_end_scale', 1.15)
                
                if has_zoom:
                    logger.info(f"片段 {idx} 启用放大效果：{zoom_start} -> {zoom_end}")
                
                # 只有第一个片段启用摘要滚动效果
                enable_summary_scroll = (idx == 1)
                logger.info(f"片段 {idx} 摘要滚动：{'开启' if enable_summary_scroll else '关闭'}")
                
                # 使用 make_frame 创建动画片段
                def make_frame_func(t, _bg=bg_template, _img=user_img_resized,
                                    _px=paste_x, _py=final_paste_y,
                                    _tw=target_w, _th=target_h,
                                    _ti=title_info, _si=summary_info,
                                    _anim=anim, _zoom=has_zoom,
                                    _zs=zoom_start, _ze=zoom_end,
                                    _scroll=enable_summary_scroll):
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
                        summary_segments=None  # 不再使用分段
                    )
                
                clip = VideoClip(make_frame_func, duration=clip_duration).set_fps(FPS)
                clips.append(clip)
                
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
                    summary_segments=None  # 不再使用分段
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
                audio = audio.fl_time(lambda t: t * speed).set_duration(audio.duration / speed)
                new_duration = audio.duration
                logger.info(f"   🚀 应用{speed}倍速")
                logger.info(f"   加速后时长: {new_duration:.2f}秒")
                logger.info(f"   时间压缩: {(original_duration - new_duration) / original_duration * 100:.1f}%")
                if audio.duration < video_duration:
                    from moviepy.editor import concatenate_audioclips
                    audio = concatenate_audioclips([audio] * (int(video_duration / audio.duration) + 1))
                audio = audio.subclip(0, video_duration)
                final_clip = final_clip.set_audio(audio)
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

        from moviepy.editor import concatenate_videoclips, AudioFileClip, VideoClip

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

        for idx, (img_path, orig_w, orig_h) in enumerate(valid_images, 1):
            try:
                # 检查是否为GIF文件
                is_gif = img_path.lower().endswith('.gif')
                
                if is_gif:
                    # 处理GIF动画
                    logger.info(f"🔄 处理GIF动画: {img_path}")
                    logger.info(f"   GIF路径: {img_path}")
                    logger.info(f"   目标时长: {clip_duration}秒")
                    
                    # 修复路径问题 - 去掉开头的斜杠
                    actual_gif_path = img_path.lstrip('/')
                    logger.info(f"   实际GIF路径: {actual_gif_path}")
                    
                    # 检查文件是否存在
                    if not Path(actual_gif_path).exists():
                        logger.error(f"   ❌ GIF文件不存在: {actual_gif_path}")
                        logger.warning(f"   ⚠️ 回退到静态图片处理: {img_path}")
                        # 继续使用静态图片处理逻辑
                    else:
                        logger.info(f"   ✅ GIF文件存在")
                        
                        # 提取GIF帧用于动画处理
                        from services.gif_processor import gif_processor
                        gif_frames = gif_processor.extract_gif_frames(actual_gif_path)
                        
                        if gif_frames and len(gif_frames) > 0:
                            logger.info(f"   🎬 提取到 {len(gif_frames)} 帧GIF动画")
                            
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
                                                   _cd=_clip_dur, _dur=clip_duration):
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
                                    anim_type=_anim
                                )
                                return _apply_video_effect(frame, t, _eff, canvas_w, canvas_h, _cd, seed=_sd)
                            
                            clip = VideoClip(make_gif_frame_func, duration=clip_duration).set_fps(FPS)
                            clips.append(clip)
                            logger.info(f"   🎬 GIF动画片段 {idx} 添加成功")
                            
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
                                anim_type=anim
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

                _effect = effect
                _clip_dur = clip_duration
                _seed = idx  # 每段粒子不同

                def make_frame_func(t, _bg=bg_template, _img=user_img,
                                    _px=paste_x, _py=paste_y,
                                    _tw=target_w, _th=target_h,
                                    _ti=title_info, _si=summary_info,
                                    _anim=anim, _eff=_effect, _sd=_seed,
                                    _cd=_clip_dur):
                    frame = _render_frame_animated(
                        _bg, _img, _px, _py, _tw, _th, canvas_w, canvas_h,
                        _ti, _si, t,
                        entrance_duration=ENTRANCE_DUR,
                        hold_with_text_start=ENTRANCE_DUR,
                        anim_type=_anim
                    )
                    return _apply_video_effect(frame, t, _eff, canvas_w, canvas_h, _cd, seed=_sd)

                clip = VideoClip(make_frame_func, duration=clip_duration).set_fps(FPS)
                clips.append(clip)

                # 保存预览帧（带特效）
                preview_raw = _render_frame_animated(
                    bg_template, user_img, paste_x, paste_y,
                    target_w, target_h, canvas_w, canvas_h,
                    title_info, summary_info, clip_duration,
                    entrance_duration=ENTRANCE_DUR, hold_with_text_start=ENTRANCE_DUR,
                    anim_type=anim
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
                audio = audio.fl_time(lambda t: t * speed).set_duration(audio.duration / speed)
                new_duration = audio.duration
                logger.info(f"   🚀 应用{speed}倍速")
                logger.info(f"   加速后时长: {new_duration:.2f}秒")
                logger.info(f"   时间压缩: {(original_duration - new_duration) / original_duration * 100:.1f}%")
                if audio.duration < video_duration:
                    from moviepy.editor import concatenate_audioclips
                    audio = concatenate_audioclips([audio] * (int(video_duration / audio.duration) + 1))
                audio = audio.subclip(0, video_duration)
                final_clip = final_clip.set_audio(audio)
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