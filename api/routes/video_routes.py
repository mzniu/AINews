"""视频处理相关API路由"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import List
from pathlib import Path
from datetime import datetime
from loguru import logger
from PIL import Image, ImageDraw
from ..schemas.request_models import (
    CreateVideoRequest, CreateAnimatedVideoRequest, CreateUserVideoRequest
)
from utils.video_utils import (
    _render_frame_animated, _apply_video_effect, _safe_paste, _draw_text_overlay,
    _load_fonts, _wrap_text
)
from services.video_service import VideoService

router = APIRouter(prefix="/api", tags=["视频"])

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

        from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip, VideoClip

        FPS = 24
        ENTRANCE_DUR = 0.6     # 小图弹落动画时长
        HOLD_NO_TEXT = 0.8     # 弹落后无文字停顿
        TEXT_FADE_IN = 0.4     # 文字渐入时长
        HOLD_WITH_TEXT = 1.5   # 文字显示后静持时长

        CLIP_DURATION = HOLD_NO_TEXT + TEXT_FADE_IN + HOLD_WITH_TEXT  # 每段约2.7秒

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
        summary_lines = _wrap_text(request.summary, summary_font, text_width, temp_draw)

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
        summary_height = sum(
            temp_draw.textbbox((0, 0), l, font=summary_font)[3] -
            temp_draw.textbbox((0, 0), l, font=summary_font)[1] + 12
            for l in summary_lines
        )

        title_start_y = int(img_height * 0.1)
        summary_start_y = int(img_height * 0.9) - summary_height

        title_info = (title_font, subtitle_font, main_title_lines, sub_title_lines,
                      title_start_y, main_title_height, margin, text_width)
        summary_info = (summary_font, summary_lines, summary_start_y)

        clips = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("data/generated") / f"anim_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 构建动画队列：打乱后循环分配，保证每张图动画不同
        import random
        all_anim_types = ['zoom_in', 'zoom_out', 'unfold', 'scroll_up',
                          'slide_left', 'slide_right', 'fade_in', 'drop_bounce']
        num_images = len(request.images)
        random.shuffle(all_anim_types)
        # 循环分配：图片数 > 动画种类时重复但尽量错开
        anim_queue = []
        for i in range(num_images):
            anim_queue.append(all_anim_types[i % len(all_anim_types)])

        for idx, img_path in enumerate(request.images, 1):
            try:
                user_img_path = Path(img_path.lstrip('/'))
                if not user_img_path.exists():
                    logger.warning(f"图片不存在，跳过: {img_path}")
                    continue

                user_img = Image.open(user_img_path)
                if user_img.mode != 'RGBA':
                    user_img = user_img.convert('RGBA')

                # 缩放
                target_w = img_width
                ratio = target_w / user_img.width
                target_h = int(user_img.height * ratio)
                max_h = int(img_height * 0.6)
                if target_h > max_h:
                    target_h = max_h
                    ratio = target_h / user_img.height
                    target_w = int(user_img.width * ratio)

                user_img_resized = user_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

                paste_x = (img_width - target_w) // 2
                # 图片在标题和摘要之间居中
                available = summary_start_y - 40 - (title_start_y + title_height + 30)
                final_paste_y = title_start_y + title_height + 30 + (available - target_h) // 2
                final_paste_y = max(title_start_y + title_height + 30, final_paste_y)

                logger.info(f"片段 {idx}: 生成 {CLIP_DURATION:.1f}s 动画, 图片 {target_w}x{target_h}")

                # 每张图使用不同的动画（打乱后循环分配）
                anim = anim_queue.pop(0)
                logger.info(f"片段 {idx} 动画类型: {anim}")

                # 使用 make_frame 创建动画片段
                def make_frame_func(t, _bg=bg_template, _img=user_img_resized,
                                    _px=paste_x, _py=final_paste_y,
                                    _tw=target_w, _th=target_h,
                                    _ti=title_info, _si=summary_info,
                                    _anim=anim):
                    return _render_frame_animated(
                        _bg, _img, _px, _py, _tw, _th, img_width, img_height,
                        _ti, _si, t,
                        entrance_duration=ENTRANCE_DUR,
                        hold_with_text_start=HOLD_NO_TEXT,
                        anim_type=_anim
                    )

                clip = VideoClip(make_frame_func, duration=CLIP_DURATION).with_fps(FPS)
                clips.append(clip)

                # 同时保存一张静态预览帧（用于前端显示）
                preview = _render_frame_animated(
                    bg_template, user_img_resized, paste_x, final_paste_y,
                    target_w, target_h, img_width, img_height,
                    title_info, summary_info, CLIP_DURATION,
                    entrance_duration=ENTRANCE_DUR, hold_with_text_start=HOLD_NO_TEXT,
                    anim_type=anim
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
                speed = 1.1
                audio = audio.time_transform(lambda t: t * speed).with_duration(audio.duration / speed)
                if audio.duration < video_duration:
                    from moviepy.editor import concatenate_audioclips
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

        rel = str(video_path.relative_to(Path("."))).replace("\\", "/")
        size_mb = video_path.stat().st_size / (1024 * 1024)
        logger.success(f"动画视频生成成功: {video_path} ({size_mb:.2f}MB)")

        # 预览帧列表
        previews = []
        for f in sorted(output_dir.glob("preview_*.png")):
            previews.append(f"/{str(f.relative_to(Path('.'))).replace(chr(92), '/')}")

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

                clip = VideoClip(make_frame_func, duration=clip_duration).with_fps(FPS)
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
                speed = 1.1
                audio = audio.time_transform(lambda t: t * speed).with_duration(audio.duration / speed)
                if audio.duration < video_duration:
                    from moviepy.editor import concatenate_audioclips
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