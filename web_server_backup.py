"""
AINews Web Server - 模块化架构版本
"""
import sys
import os

# 修复Windows控制台GBK编码无法输出emoji/中文的问题
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from dotenv import load_dotenv

# 导入路由模块
from api.routes.main_routes import router as main_router
from api.routes.crawler_routes import router as crawler_router
from api.routes.video_routes import router as video_router
from api.routes.watermark_routes import router as watermark_router

# 加载环境变量
load_dotenv()

# 配置日志
logger.add("logs/web_server_{time}.log", rotation="10 MB")

app = FastAPI(title="网页抓取API", version="2.0.0")

# CORS
# 配置日志
logger.add("logs/web_server_{time}.log", rotation="10 MB")

# 创建FastAPI应用
app = FastAPI(
    title="AINews API",
    version="2.0.0",
    description="AI资讯视频生成平台",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data", StaticFiles(directory="data"), name="data")

# 注册路由
app.include_router(main_router)
app.include_router(crawler_router)
app.include_router(video_router)
app.include_router(watermark_router)


# 数据模型
class FetchRequest(BaseModel):
    url: HttpUrl


class FetchResponse(BaseModel):
    success: bool
    message: str
    data: dict = None


class GenerateSummaryRequest(BaseModel):
    content: str
    images: List[str] = []
    title: str = ""


class GenerateImageRequest(BaseModel):
    title: str
    summary: str
    images: List[str] = []


class ProcessImageRequest(BaseModel):
    image_path: str
    effect: str = "enhance"


class CreateVideoRequest(BaseModel):
    frames_dir: str
    duration_per_frame: float = 2.5
    audio_path: str = ""


class RemoveWatermarkRequest(BaseModel):
    image_path: str
    regions: List[dict] = []  # [{x, y, width, height}, ...]

class DetectWatermarkRequest(BaseModel):
    image_path: str


# 核心功能
async def get_page_content(url: str) -> tuple[str, str]:
    """使用Playwright获取页面（自动降级等待策略）"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # 先尝试 networkidle（最完整），超时则降级到 domcontentloaded
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
            except Exception:
                logger.warning(f"networkidle 超时，降级为 domcontentloaded: {url}")
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    # 额外等待一段时间让JS渲染完成
                    await page.wait_for_timeout(5000)
                except Exception:
                    logger.warning(f"domcontentloaded 也超时，使用 commit 策略: {url}")
                    await page.goto(url, wait_until='commit', timeout=60000)
                    await page.wait_for_timeout(8000)
            
            title = await page.title()
            html = await page.content()
            
            await browser.close()
            logger.success(f"成功获取页面: {title}")
            return html, title
    except Exception as e:
        logger.error(f"获取页面失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取页面失败: {str(e)}")


def extract_content(html: str, base_url: str) -> dict:
    """提取页面内容和图片"""
    soup = BeautifulSoup(html, 'lxml')
    
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    
    content_selectors = [
        'article', '[class*="content"]', '[class*="article"]',
        '[class*="post"]', '[id*="content"]', 'main', 'body'
    ]
    
    content_text = ""
    for selector in content_selectors:
        elements = soup.select(selector)
        if elements:
            content_text = elements[0].get_text(separator='\n', strip=True)
            if len(content_text) > 200:
                break
    
    images = []
    
    # 检查是否为qbitai网站，如果是则只提取syl-page-img类的图片
    parsed_url = urlparse(base_url)
    is_qbitai = 'qbitai.com' in parsed_url.netloc
    
    if is_qbitai:
        # 只提取具有syl-page-img类的图片
        logger.info("检测到qbitai网站，只提取syl-page-img类的图片")
        img_elements = soup.find_all('img', class_='syl-page-img')
        for img in img_elements:
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if src and not src.startswith('data:'):
                images.append({
                    'url': urljoin(base_url, src),
                    'alt': img.get('alt', ''),
                    'class': 'syl-page-img'  # 标记来源
                })
    else:
        # 其他网站提取所有图片
        logger.info("提取页面所有图片")
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if src and not src.startswith('data:'):
                images.append({
                    'url': urljoin(base_url, src),
                    'alt': img.get('alt', '')
                })
    
    logger.info(f"提取到 {len(images)} 张图片 (qbitai模式: {is_qbitai})")
    return {'content': content_text, 'images': images}


def download_image(image_url: str, save_dir: Path, index: int, page_url: str = '') -> dict:
    """下载图片（带Referer防盗链绕过）"""
    try:
        # 跳过 data URI
        if image_url.startswith('data:'):
            return {'url': image_url[:50], 'success': False, 'error': 'data URI, skipped'}
        
        ext = Path(urlparse(image_url).path).suffix or '.jpg'
        filename = f"image_{index:03d}{ext}"
        filepath = save_dir / filename
        
        # 构造完整请求头，带 Referer 绕过防盗链
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        if page_url:
            headers['Referer'] = page_url
            # 设置 Origin 为源站域名
            parsed = urlparse(page_url)
            headers['Origin'] = f"{parsed.scheme}://{parsed.netloc}"
        
        response = requests.get(image_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        relative_path = str(filepath.relative_to(Path("."))).replace("\\", "/")
        return {'url': image_url, 'local_path': f"/{relative_path}", 'success': True}
    except Exception as e:
        return {'url': image_url, 'success': False, 'error': str(e)}


def save_results(url: str, title: str, content: str, images: list) -> dict:
    """保存结果"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    save_dir = Path("data/fetched") / f"{url_hash}_{timestamp}"
    images_dir = save_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_images = [download_image(img['url'], images_dir, i, page_url=url) for i, img in enumerate(images, 1)]
    
    content_file = save_dir / "content.txt"
    with open(content_file, 'w', encoding='utf-8') as f:
        f.write(f"标题: {title}\nURL: {url}\n抓取时间: {datetime.now().isoformat()}\n\n{'='*80}\n\n{content}")
    
    metadata = {
        'url': url,
        'title': title,
        'crawl_time': datetime.now().isoformat(),
        'content_length': len(content),
        'images_count': len([img for img in downloaded_images if img['success']]),
        'images': downloaded_images,
        'content_preview': content[:500] + '...' if len(content) > 500 else content
    }
    
    with open(save_dir / "metadata.json", 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    relative_dir = str(save_dir.relative_to(Path("."))).replace("\\", "/")
    metadata['content_file'] = f"/{relative_dir}/content.txt"
    metadata['metadata_file'] = f"/{relative_dir}/metadata.json"
    
    return metadata


# API路由
@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/video-maker")
async def video_maker_page():
    """用户上传图片生成视频的独立页面"""
    return FileResponse("static/video_maker.html")


@app.post("/api/upload-images")
async def upload_images(files: list[UploadFile] = File(...)):
    """上传一张或多张图片，返回保存路径列表"""
    try:
        upload_dir = Path("data/uploads") / datetime.now().strftime("%Y%m%d_%H%M%S")
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for i, file in enumerate(files):
            ext = Path(file.filename or "img.png").suffix.lower()
            if ext not in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'):
                ext = '.png'
            save_name = f"img_{i+1:03d}{ext}"
            save_path = upload_dir / save_name
            content = await file.read()
            save_path.write_bytes(content)
            rel = str(save_path).replace("\\", "/")
            saved_paths.append(f"/{rel}")
            logger.info(f"已保存上传图片: {save_path} ({len(content)} bytes)")

        return {"success": True, "images": saved_paths, "count": len(saved_paths)}
    except Exception as e:
        logger.error(f"上传图片失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/create-user-video")
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
        image_list = _json.loads(images)
        if not image_list:
            return JSONResponse(status_code=400,
                                content={"success": False, "message": "请至少上传一张图片"})

        from moviepy import concatenate_videoclips, AudioFileClip, VideoClip

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
                    from moviepy import concatenate_audioclips
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


@app.post("/api/fetch", response_model=FetchResponse)
async def fetch_url(request: FetchRequest):
    """抓取URL"""
    try:
        logger.info(f"开始抓取: {request.url}")
        html, title = await get_page_content(str(request.url))
        result = extract_content(html, str(request.url))
        metadata = save_results(str(request.url), title, result['content'], result['images'])
        return FetchResponse(success=True, message="抓取成功", data=metadata)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"抓取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-summary")
async def generate_summary(request: GenerateSummaryRequest):
    """生成AI摘要"""
    try:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key or api_key == "your_deepseek_api_key_here":
            return {"success": False, "message": "请在.env文件中配置DEEPSEEK_API_KEY"}
        
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
        prompt = f"""请为以下文章生成适合短视频的主标题、副标题、摘要和标签，要求：
1. 主标题：8-15字，一句话点明核心看点，简短有力，不使用任何emoji表情
   - 用数字或对比制造冲击感（如"暴涨300%"、"碾压GPT-4"）
   - 用疑问/反问/感叹激发好奇心
   - 直击痛点或利益点
   - 要有观点和态度，不要平淡叙述
2. 副标题：10-20字，补充主标题的信息，提供更多细节或悬念，不使用任何emoji表情
3. 摘要：50-70字，简洁有力，适合短视频口播解说，节奏感强
4. 标签：10个相关标签，每个标签以#开头，用空格分隔

原标题：{request.title}

正文：
{request.content[:3000]}

请按以下JSON格式返回：
{{
  "main_title": "主标题（8-15字，不含emoji）",
  "sub_title": "副标题（10-20字，不含emoji）",
  "summary": "生成的摘要（50-70字）",
  "tags": "#AI #人工智能 #科技 ... (10个标签)"
}}"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是顶级自媒体爆款标题大师，精通短视频内容运营。你的标题总能引发强烈的点击冲动，既有信息量又有情绪张力。你擅长用最凝练的文字传递最大的信息密度和情绪冲击。绝对不使用任何emoji表情符号。请严格按照JSON格式返回结果。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        
        tags = result.get('tags', '')
        main_title = result.get('main_title', result.get('title', ''))
        sub_title = result.get('sub_title', '')
        # 组合标题供前端显示，用 | 分隔主副标题
        combined_title = f"{main_title}|{sub_title}" if sub_title else main_title
        logger.success(f"标题生成成功 - 主标题: {main_title}, 副标题: {sub_title}, 摘要: {len(result['summary'])}字")
        
        return {
            "success": True,
            "title": combined_title,
            "main_title": main_title,
            "sub_title": sub_title,
            "summary": result['summary'],
            "tags": tags,
            "tokens_used": response.usage.total_tokens,
            "model": response.model
        }
    except Exception as e:
        logger.error(f"生成摘要失败: {e}")
        return {"success": False, "message": str(e)}


@app.post("/api/generate-image")
async def generate_image(request: GenerateImageRequest):
    """生成视频关键帧（每张选中图片生成一帧）"""
    try:
        if not request.images:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "请至少选择一张图片"}
            )
        
        # 加载背景图
        bg_path = Path("static/imgs/bg.png")
        if not bg_path.exists():
            bg_template = Image.new('RGB', (1080, 1920), color=(102, 126, 234))
        else:
            bg_template = Image.open(bg_path)
        
        img_width, img_height = bg_template.size
        
        # 加载字体（标题用粗体大号，摘要用常规）
        try:
            title_font = ImageFont.truetype("msyhbd.ttc", 66)       # 微软雅黑粗体，更大
            summary_font = ImageFont.truetype("msyh.ttc", 48)       # 微软雅黑常规
        except:
            try:
                title_font = ImageFont.truetype("simhei.ttf", 66)   # 备选：黑体
                summary_font = ImageFont.truetype("simhei.ttf", 48)
            except:
                title_font = ImageFont.load_default()
                summary_font = ImageFont.load_default()
        
        # 文字自动换行函数（词感知：不截断英文单词）
        def wrap_text(text, font, max_width, draw_obj):
            import re
            # 将文本拆分为"token"：连续的ASCII单词/数字为一个token，每个中文字符单独为一个token，
            # 空格和标点也单独为token，这样换行时不会把英文单词从中间截断
            tokens = re.findall(r"[A-Za-z0-9]+(?:['\u2019\-][A-Za-z0-9]+)*|[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]|[^\S\n]|[^\w\s]|\n", text)
            
            lines = []
            current_line = ""
            
            for token in tokens:
                if token == '\n':
                    lines.append(current_line)
                    current_line = ""
                    continue
                    
                test_line = current_line + token
                bbox = draw_obj.textbbox((0, 0), test_line, font=font)
                line_width = bbox[2] - bbox[0]
                
                if line_width <= max_width:
                    current_line = test_line
                else:
                    # 当前行放不下这个token
                    if current_line.strip():
                        lines.append(current_line)
                        # 新行开头去掉前导空格
                        current_line = token.lstrip() if token.isspace() else token
                    else:
                        # 当前行为空但单个token就超宽了（超长单词），强制按字符拆分
                        for char in token:
                            test_char = current_line + char
                            bbox = draw_obj.textbbox((0, 0), test_char, font=font)
                            if bbox[2] - bbox[0] <= max_width:
                                current_line = test_char
                            else:
                                if current_line:
                                    lines.append(current_line)
                                current_line = char
                    
                    # 检查新行是否也超宽（token本身超宽时的后续处理）
                    bbox = draw_obj.textbbox((0, 0), current_line, font=font)
                    if bbox[2] - bbox[0] > max_width and len(current_line) > 1:
                        # 对超长的current_line进行字符级拆分
                        temp = ""
                        for char in current_line:
                            test_char = temp + char
                            bbox = draw_obj.textbbox((0, 0), test_char, font=font)
                            if bbox[2] - bbox[0] <= max_width:
                                temp = test_char
                            else:
                                if temp:
                                    lines.append(temp)
                                temp = char
                        current_line = temp
            
            if current_line:
                lines.append(current_line)
            return lines
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("data/generated") / f"frames_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        generated_frames = []
        
        # 为每张选中的图片生成一帧
        for idx, img_path in enumerate(request.images, 1):
            try:
                # 复制背景图
                bg = bg_template.copy()
                
                # 创建绘制对象
                draw = ImageDraw.Draw(bg)
                
                # 设置文字区域
                margin = int(img_width * 0.08)
                text_width = img_width - 2 * margin
                
                # 先计算所有元素的高度，以便垂直居中
                # 计算标题高度
                title_lines = wrap_text(request.title, title_font, text_width, draw)
                title_height = sum([draw.textbbox((0, 0), line, font=title_font)[3] - 
                                   draw.textbbox((0, 0), line, font=title_font)[1] + 18 
                                   for line in title_lines])
                
                # 计算摘要高度
                summary_lines = wrap_text(request.summary, summary_font, text_width, draw)
                summary_height = sum([draw.textbbox((0, 0), line, font=summary_font)[3] - 
                                     draw.textbbox((0, 0), line, font=summary_font)[1] + 12 
                                     for line in summary_lines])
                
                # 加载用户图片以获取实际高度
                user_img_path = Path(img_path.lstrip('/'))
                target_height = 0
                target_width = img_width
                user_img_resized = None
                
                if user_img_path.exists():
                    user_img = Image.open(user_img_path)
                    
                    # 缩放用户图片（宽度占背景100%，保持宽高比）
                    ratio = target_width / user_img.width
                    target_height = int(user_img.height * ratio)
                    
                    # 限制最大高度
                    max_height = int(img_height * 0.6)
                    if target_height > max_height:
                        target_height = max_height
                        ratio = target_height / user_img.height
                        target_width = int(user_img.width * ratio)
                    
                    user_img_resized = user_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # 计算总高度（标题 + 间距 + 图片 + 间距 + 摘要）
                total_content_height = title_height + 30 + target_height + 40 + summary_height
                
                # 标题固定在背景上部15%位置
                title_start_y = int(img_height * 0.15)
                current_y = title_start_y
                
                # 绘制标题背景（渐变毛玻璃效果）
                title_bg_y = current_y - 25
                title_bg_height = title_height + 40
                overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                # 多层渐变：上下边缘更透明，中间稍实
                for i in range(title_bg_height):
                    progress = i / title_bg_height
                    if progress < 0.1:
                        alpha = int(220 * (progress / 0.1))
                    elif progress > 0.9:
                        alpha = int(220 * ((1 - progress) / 0.1))
                    else:
                        alpha = 220
                    overlay_draw.rectangle(
                        [(0, title_bg_y + i), (img_width, title_bg_y + i + 1)],
                        fill=(20, 20, 40, alpha)
                    )
                bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
                draw = ImageDraw.Draw(bg)  # 重新创建draw对象
                
                # 绘制标题（多层光影效果）
                for line in title_lines:
                    bbox = draw.textbbox((0, 0), line, font=title_font)
                    line_width = bbox[2] - bbox[0]
                    x = margin + (text_width - line_width) // 2
                    
                    # 第1层：柔和外发光（模拟光晕）
                    for dx in range(-3, 4):
                        for dy in range(-3, 4):
                            if dx*dx + dy*dy <= 9:
                                draw.text((x + dx, current_y + dy), line, font=title_font, 
                                         fill=(102, 126, 234, 60))  # 品牌蓝色光晕
                    
                    # 第2层：深色阴影（增加立体感）
                    draw.text((x + 3, current_y + 3), line, font=title_font, fill=(0, 0, 0))
                    draw.text((x + 2, current_y + 2), line, font=title_font, fill=(10, 10, 30))
                    
                    # 第3层：主文字（纯白）
                    draw.text((x, current_y), line, font=title_font, fill=(255, 255, 0))
                    
                    current_y += bbox[3] - bbox[1] + 18
                
                # 标题和图片之间的间距
                current_y += 30
                
                # 计算摘要的起始位置（距离底部15%）
                summary_start_y = int(img_height * 0.85) - summary_height
                
                # 计算图片的位置（在标题下方和摘要上方之间居中）
                available_space = summary_start_y - 40 - current_y  # 减去间距
                image_y = current_y + (available_space - target_height) // 2
                
                # 粘贴用户图片
                if user_img_resized:
                    # 居中粘贴图片
                    paste_x = (img_width - target_width) // 2
                    paste_y = max(current_y, image_y)  # 确保图片在标题下方
                    
                    # 如果用户图片有透明通道，使用它作为mask
                    if user_img_resized.mode == 'RGBA':
                        bg.paste(user_img_resized, (paste_x, paste_y), user_img_resized)
                    else:
                        bg.paste(user_img_resized, (paste_x, paste_y))
                
                # 绘制摘要背景（柔和渐变半透明）
                current_y = summary_start_y
                summary_bg_y = current_y - 35
                summary_bg_height = summary_height + 50
                overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                for i in range(summary_bg_height):
                    progress = i / summary_bg_height
                    if progress < 0.1:
                        alpha = int(220 * (progress / 0.1))
                    elif progress > 0.9:
                        alpha = int(220 * ((1 - progress) / 0.1))
                    else:
                        alpha = 220
                    overlay_draw.rectangle(
                        [(0, summary_bg_y + i), (img_width, summary_bg_y + i + 1)],
                        fill=(20, 20, 40, alpha)
                    )
                bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
                draw = ImageDraw.Draw(bg)  # 重新创建draw对象
                
                # 绘制摘要文字
                for line in summary_lines:
                    bbox = draw.textbbox((0, 0), line, font=summary_font)
                    line_width = bbox[2] - bbox[0]
                    x = margin + (text_width - line_width) // 2
                    
                    # 阴影
                    draw.text((x + 2, current_y + 2), line, font=summary_font, fill=(0, 0, 0))
                    # 文字（亮白色）
                    draw.text((x, current_y), line, font=summary_font, fill=(255, 255, 255))
                    current_y += bbox[3] - bbox[1] + 12
                
                # 保存关键帧
                output_path = output_dir / f"frame_{idx:02d}.png"
                bg.save(output_path, quality=95)
                
                relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
                generated_frames.append({
                    "frame_index": idx,
                    "image_path": f"/{relative_path}",
                    "source_image": img_path
                })
                
                logger.success(f"关键帧 {idx} 生成成功: {output_path}")
                
            except Exception as frame_error:
                logger.error(f"生成关键帧 {idx} 失败: {frame_error}")
                continue
        
        if not generated_frames:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "所有关键帧生成失败"}
            )
        
        return {
            "success": True,
            "message": f"成功生成 {len(generated_frames)} 个关键帧",
            "frames": generated_frames,
            "total": len(generated_frames),
            "title": request.title,
            "summary": request.summary,
            "output_dir": str(output_dir.relative_to(Path("."))).replace("\\", "/")
        }
        
    except Exception as e:
        logger.error(f"图片生成失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"图片生成失败: {str(e)}"}
        )


@app.post("/api/create-video")
async def create_video(request: CreateVideoRequest):
    """将关键帧合成视频"""
    try:
        # MoviePy 2.x 使用新的导入方式
        from moviepy import ImageClip, concatenate_videoclips, AudioFileClip
        
        frames_dir = Path(request.frames_dir.lstrip('/'))
        if not frames_dir.exists():
            raise HTTPException(status_code=404, detail="关键帧目录不存在")
        
        # 获取所有关键帧图片
        frame_files = sorted(frames_dir.glob("frame_*.png"))
        if not frame_files:
            raise HTTPException(status_code=404, detail="未找到关键帧图片")
        
        logger.info(f"找到 {len(frame_files)} 个关键帧，开始合成视频...")
        
        # 加载背景音乐
        audio = None
        audio_path = request.audio_path.lstrip('/') if request.audio_path else None
        logger.info(f"音频路径参数: {request.audio_path}")
        logger.info(f"处理后路径: {audio_path}")
        if audio_path:
            audio_file = Path(audio_path)
            logger.info(f"音频文件存在: {audio_file.exists()}, 绝对路径: {audio_file.absolute()}")
            if audio_file.exists():
                audio = AudioFileClip(str(audio_file))
                original_duration = audio.duration
                # 加速到1.1倍速 (通过时间变换实现)
                speed_factor = 1.1
                audio = audio.time_transform(lambda t: t * speed_factor).with_duration(audio.duration / speed_factor)
                logger.info(f"加载背景音乐: {audio_path}, 原时长: {original_duration:.2f}秒, 1.1倍速后: {audio.duration:.2f}秒")
            else:
                logger.warning(f"背景音乐文件不存在: {audio_file.absolute()}")
        
        # 创建视频片段列表
        clips = []
        num_frames = len(frame_files)
        
        for idx, frame_file in enumerate(frame_files):
            # 计算每帧时长：
            # - 1张关键帧：6秒
            # - 2张关键帧：每张3秒，共6秒
            # - 3张及以上：第一张2.5秒，其余每张3秒
            if num_frames == 1:
                frame_duration = 6.0
            elif num_frames == 2:
                frame_duration = 3.0
            elif idx == 0:
                frame_duration = 2.5
            else:
                frame_duration = 2
            
            clip = ImageClip(str(frame_file), duration=frame_duration)
            clips.append(clip)
            logger.info(f"关键帧 {idx + 1}: {frame_file.name}, 时长 {frame_duration}秒")
        
        # 拼接所有片段
        final_clip = concatenate_videoclips(clips, method="compose")
        
        # 记录视频总时长
        video_duration = final_clip.duration
        logger.info(f"视频总时长: {video_duration:.2f}秒")
        
        # 添加背景音乐
        if audio:
            # 如果音频比视频短，循环音乐
            if audio.duration < video_duration:
                from moviepy import concatenate_audioclips
                n_loops = int(video_duration / audio.duration) + 1
                audio = concatenate_audioclips([audio] * n_loops)
                logger.info(f"音乐循环 {n_loops} 次")
            # 截取与视频等长的音频 (MoviePy 2.x 使用 subclipped)
            audio = audio.subclipped(0, video_duration)
            final_clip = final_clip.with_audio(audio)
            logger.info("背景音乐已添加")
        
        # 保存视频
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("data/videos")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"video_{timestamp}.mp4"
        
        # 写入视频文件
        final_clip.write_videofile(
            str(output_path),
            fps=24,
            codec='libx264',
            audio_codec='aac' if audio else None,
            temp_audiofile='temp-audio.m4a' if audio else None,
            remove_temp=True,
            logger=None  # 禁用moviepy的详细日志
        )
        
        # 关闭资源
        final_clip.close()
        if audio:
            audio.close()
        
        relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
        file_size = output_path.stat().st_size / (1024 * 1024)  # MB
        
        logger.success(f"视频生成成功: {output_path} ({file_size:.2f}MB)")
        
        return {
            "success": True,
            "message": "视频生成成功",
            "video_path": f"/{relative_path}",
            "frames_count": len(frame_files),
            "duration": video_duration,
            "file_size_mb": round(file_size, 2)
        }
        
    except Exception as e:
        logger.error(f"视频生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"视频生成失败: {str(e)}")


# ==================== 带入场动画的视频生成 ====================

class CreateAnimatedVideoRequest(BaseModel):
    title: str
    summary: str
    images: List[str] = []
    audio_path: str = ""


def _load_fonts():
    """加载字体，返回 (title_font, subtitle_font, summary_font)"""
    try:
        return (ImageFont.truetype("msyhbd.ttc", 66),
                ImageFont.truetype("msyhbd.ttc", 58),
                ImageFont.truetype("msyh.ttc", 48))
    except:
        try:
            return (ImageFont.truetype("simhei.ttf", 66),
                    ImageFont.truetype("simhei.ttf", 58),
                    ImageFont.truetype("simhei.ttf", 48))
        except:
            df = ImageFont.load_default()
            return df, df, df


def _wrap_text(text, font, max_width, draw_obj):
    """词感知自动换行（不截断英文单词）"""
    import re
    tokens = re.findall(
        r"[A-Za-z0-9]+(?:['\u2019\-][A-Za-z0-9]+)*|[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]|[^\S\n]|[^\w\s]|\n",
        text
    )
    lines, current_line = [], ""
    for token in tokens:
        if token == '\n':
            lines.append(current_line)
            current_line = ""
            continue
        test_line = current_line + token
        bbox = draw_obj.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line.strip():
                lines.append(current_line)
                current_line = token.lstrip() if token.isspace() else token
            else:
                for char in token:
                    test_char = current_line + char
                    bbox = draw_obj.textbbox((0, 0), test_char, font=font)
                    if bbox[2] - bbox[0] <= max_width:
                        current_line = test_char
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = char
    if current_line:
        lines.append(current_line)
    return lines


def _draw_text_overlay(bg, lines, font, start_y, img_width, margin, text_width,
                       text_color=(255, 255, 255), glow_color=None, line_spacing=12):
    """在图片上绘制带半透明背景的文字块，返回 (result_image, block_height)"""
    draw = ImageDraw.Draw(bg)
    total_h = sum(
        draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] + line_spacing
        for line in lines
    )
    # 半透明背景
    bg_y = start_y - 25
    bg_h = total_h + 40
    overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(bg_h):
        p = i / bg_h
        alpha = int(220 * (min(p, 1 - p) / 0.1 if min(p, 1 - p) < 0.1 else 1))
        od.rectangle([(0, bg_y + i), (img_width, bg_y + i + 1)], fill=(20, 20, 40, alpha))
    result = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(result)

    cy = start_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = margin + (text_width - lw) // 2
        if glow_color:
            # 外层柔光（r=3）
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    d2 = dx * dx + dy * dy
                    if d2 <= 9:
                        a = int(50 * (1 - d2 / 9))
                        draw.text((x + dx, cy + dy), line, font=font,
                                  fill=(glow_color[0], glow_color[1], glow_color[2], a))
        # 深色阴影
        draw.text((x + 3, cy + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x + 1, cy + 1), line, font=font, fill=(10, 10, 30))
        # 主文字
        draw.text((x, cy), line, font=font, fill=text_color)
        cy += bbox[3] - bbox[1] + line_spacing

    # 标题装饰：底部渐变高亮线
    if glow_color:
        accent_y = bg_y + bg_h - 4
        for i in range(3):
            alpha = 180 - i * 50
            for px in range(margin, img_width - margin):
                progress = (px - margin) / max(1, (img_width - 2 * margin))
                r = int(255 * (1 - progress) + glow_color[0] * progress)
                g = int(200 * (1 - progress) + glow_color[1] * progress)
                b = int(60 * (1 - progress) + glow_color[2] * progress)
                draw.point((px, accent_y + i), fill=(r, g, b, alpha))

    return result, total_h


def _render_frame_animated(bg_template, user_img_resized, paste_x, final_paste_y,
                           target_width, target_height, img_width, img_height,
                           title_info, summary_info, t, entrance_duration=0.6,
                           hold_with_text_start=0.8, anim_type='zoom_in'):
    """
    渲染动画的某一帧（时间 t 秒）。
    anim_type: 'zoom_in'(动感放大), 'zoom_out'(动感缩小), 'unfold'(展开),
              'scroll_up'(向上滚动), 'slide_left'(左滑入), 'slide_right'(右滑入),
              'fade_in'(淡入), 'drop_bounce'(垂落弹跳)
    返回 numpy array (H, W, 3) uint8
    """
    import math

    bg = bg_template.copy().convert('RGB')

    # --- 阶段1: 小图入场动画 ---
    if t < entrance_duration:
        progress = t / entrance_duration
        # 缓出曲线
        ease = 1 - (1 - progress) ** 3

        if anim_type == 'zoom_in':
            # 动感放大：从小到大 + 轻微弹跳
            scale = 0.3 + 0.7 * ease
            bounce = 1 + 0.08 * math.sin(math.pi * progress) * (1 - progress)
            scale *= bounce
            sw = int(target_width * scale)
            sh = int(target_height * scale)
            if sw > 0 and sh > 0:
                scaled = user_img_resized.resize((sw, sh), Image.Resampling.LANCZOS)
                sx = paste_x + (target_width - sw) // 2
                sy = final_paste_y + (target_height - sh) // 2
                _safe_paste(bg, scaled, sx, sy)

        elif anim_type == 'zoom_out':
            # 动感缩小：从大到正常 + 轻微弹跳
            scale = 1.6 - 0.6 * ease
            bounce = 1 + 0.06 * math.sin(math.pi * progress) * (1 - progress)
            scale *= bounce
            sw = int(target_width * scale)
            sh = int(target_height * scale)
            if sw > 0 and sh > 0:
                scaled = user_img_resized.resize((sw, sh), Image.Resampling.LANCZOS)
                sx = paste_x + (target_width - sw) // 2
                sy = final_paste_y + (target_height - sh) // 2
                _safe_paste(bg, scaled, sx, sy)

        elif anim_type == 'unfold':
            # 展开：从中间横向展开
            reveal_w = max(1, int(target_width * ease))
            reveal_h = max(1, int(target_height * (0.4 + 0.6 * ease)))
            # 从中心裁剪出可见区域
            cx = target_width // 2
            cy_img = target_height // 2
            left = cx - reveal_w // 2
            top = cy_img - reveal_h // 2
            right = left + reveal_w
            bottom = top + reveal_h
            cropped = user_img_resized.crop((max(0, left), max(0, top),
                                             min(target_width, right), min(target_height, bottom)))
            px = paste_x + (target_width - cropped.width) // 2
            py = final_paste_y + (target_height - cropped.height) // 2
            _safe_paste(bg, cropped, px, py)

        elif anim_type == 'scroll_up':
            # 向上滚动：从下方滑入
            start_y = img_height + 50
            cur_y = int(start_y + (final_paste_y - start_y) * ease)
            _safe_paste(bg, user_img_resized, paste_x, cur_y)

        elif anim_type == 'slide_left':
            # 左滑入：从右侧滑入
            start_x = img_width + 50
            cur_x = int(start_x + (paste_x - start_x) * ease)
            _safe_paste(bg, user_img_resized, cur_x, final_paste_y)

        elif anim_type == 'slide_right':
            # 右滑入：从左侧滑入
            start_x = -target_width - 50
            cur_x = int(start_x + (paste_x - start_x) * ease)
            _safe_paste(bg, user_img_resized, cur_x, final_paste_y)

        elif anim_type == 'fade_in':
            # 淡入：透明度从0到1
            alpha = ease
            temp = bg.copy()
            _safe_paste(temp, user_img_resized, paste_x, final_paste_y)
            bg = Image.blend(bg, temp, alpha)

        elif anim_type == 'drop_bounce':
            # 垂落弹跳：从上方落下 + 阻尼弹跳
            bounce_val = 1 - math.exp(-5 * progress) * math.cos(3 * math.pi * progress)
            bounce_val = max(0.0, min(bounce_val, 1.3))
            start_y = -target_height - 50
            cur_y = int(start_y + (final_paste_y - start_y) * bounce_val)
            _safe_paste(bg, user_img_resized, paste_x, cur_y)

    else:
        # 小图已落定
        if user_img_resized.mode == 'RGBA':
            bg.paste(user_img_resized, (paste_x, final_paste_y), user_img_resized)
        else:
            bg.paste(user_img_resized, (paste_x, final_paste_y))

    # --- 标题和摘要始终显示 ---
    if title_info and summary_info:
        t_font, st_font, main_lines, sub_lines, title_y, main_h, margin, text_width = title_info
        summary_font, summary_lines, summary_y = summary_info

        # 主标题：白色 + 蓝色光晕
        bg, _ = _draw_text_overlay(
            bg, main_lines, t_font, title_y, img_width, margin, text_width,
            text_color=(255, 255, 255), glow_color=(102, 126, 234), line_spacing=18
        )
        # 副标题：黄色，紧跟主标题下方
        if sub_lines:
            sub_y = title_y + main_h + 12
            bg, _ = _draw_text_overlay(
                bg, sub_lines, st_font, sub_y, img_width, margin, text_width,
                text_color=(255, 255, 0), glow_color=(180, 140, 30), line_spacing=14
            )
        # 摘要
        bg, _ = _draw_text_overlay(
            bg, summary_lines, summary_font, summary_y, img_width, margin, text_width,
            text_color=(255, 255, 255), line_spacing=12
        )

    return np.array(bg)


def _apply_video_effect(frame_array, t, effect, width, height, clip_duration, seed=0):
    """
    在帧上叠加视觉特效。
    effect: 'none', 'gold_sparkle'(金粉闪闪), 'snowfall'(雪花飘落),
            'bokeh'(光斑), 'firefly'(萤火虫), 'bubble'(气泡)
    frame_array: numpy (H, W, 3) uint8
    返回 numpy (H, W, 3) uint8
    """
    if effect == 'none' or not effect:
        return frame_array

    import random
    import math

    img = Image.fromarray(frame_array).convert('RGBA')
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    rng = random.Random(seed)
    # 预生成粒子位置（基于seed固定）
    num_particles = 60
    particles = []
    for _ in range(num_particles):
        particles.append({
            'x': rng.uniform(0, width),
            'y': rng.uniform(0, height),
            'speed': rng.uniform(0.3, 1.0),
            'size': rng.uniform(2, 8),
            'phase': rng.uniform(0, math.pi * 2),
            'drift': rng.uniform(-30, 30),
        })

    if effect == 'gold_sparkle':
        # 金粉闪闪：金色小光点随机闪烁
        for p in particles:
            # 闪烁：alpha随时间正弦变化
            flicker = 0.5 + 0.5 * math.sin(t * 8 + p['phase'])
            alpha = int(200 * flicker)
            if alpha < 30:
                continue
            # 缓慢下落 + 横向飘
            px = int((p['x'] + p['drift'] * math.sin(t * 1.5 + p['phase'])) % width)
            py = int((p['y'] + t * p['speed'] * 80) % height)
            sz = max(1, int(p['size'] * (0.6 + 0.4 * flicker)))
            # 金色系
            r = rng.randint(220, 255)
            g = rng.randint(180, 220)
            b = rng.randint(50, 100)
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(r, g, b, alpha))
            # 十字星芒
            if sz > 3 and flicker > 0.7:
                arm = sz * 2
                for dx, dy in [(arm, 0), (-arm, 0), (0, arm), (0, -arm)]:
                    draw.line([px, py, px + dx, py + dy], fill=(255, 230, 120, int(alpha * 0.6)), width=1)

    elif effect == 'snowfall':
        # 雪花飘落
        for p in particles:
            py = int((p['y'] + t * p['speed'] * 60) % height)
            px = int((p['x'] + 20 * math.sin(t * 2 + p['phase'])) % width)
            sz = max(1, int(p['size']))
            alpha = int(180 + 60 * math.sin(t * 3 + p['phase']))
            alpha = max(0, min(255, alpha))
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(255, 255, 255, alpha))

    elif effect == 'bokeh':
        # 柔和光斑
        num_bokeh = 20
        for i, p in enumerate(particles[:num_bokeh]):
            px = int((p['x'] + 15 * math.sin(t * 0.8 + p['phase'])) % width)
            py = int((p['y'] + 10 * math.cos(t * 0.6 + p['phase'])) % height)
            sz = int(p['size'] * 4 + 8)
            flicker = 0.4 + 0.6 * math.sin(t * 2 + p['phase'])
            alpha = int(50 * flicker)
            colors = [(255, 200, 100), (200, 150, 255), (150, 220, 255), (255, 180, 200)]
            c = colors[i % len(colors)]
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(c[0], c[1], c[2], alpha))

    elif effect == 'firefly':
        # 萤火虫：暖黄色小光点缓慢游动
        num_ff = 25
        for p in particles[:num_ff]:
            px = int((p['x'] + 40 * math.sin(t * 0.7 + p['phase'])) % width)
            py = int((p['y'] + 30 * math.cos(t * 0.5 + p['phase'])) % height)
            glow = 0.5 + 0.5 * math.sin(t * 4 + p['phase'])
            alpha = int(180 * glow)
            sz = max(1, int(p['size'] * 0.8))
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(255, 240, 80, alpha))
            # 光晕
            hsz = sz * 3
            draw.ellipse([px - hsz, py - hsz, px + hsz, py + hsz], fill=(255, 240, 80, int(alpha * 0.15)))

    elif effect == 'bubble':
        # 气泡：半透明圆，缓慢上升
        num_bub = 20
        for p in particles[:num_bub]:
            py = int((p['y'] - t * p['speed'] * 50) % height)
            px = int((p['x'] + 15 * math.sin(t * 1.2 + p['phase'])) % width)
            sz = int(p['size'] * 3 + 6)
            alpha = int(60 + 30 * math.sin(t * 2 + p['phase']))
            draw.ellipse([px - sz, py - sz, px + sz, py + sz], fill=(200, 230, 255, alpha))
            # 高光
            hx = px - sz // 3
            hy = py - sz // 3
            hsz = max(1, sz // 4)
            draw.ellipse([hx - hsz, hy - hsz, hx + hsz, hy + hsz], fill=(255, 255, 255, int(alpha * 1.5)))

    # 合成
    img = Image.alpha_composite(img, overlay)
    return np.array(img.convert('RGB'))


def _safe_paste(bg, img, x, y):
    """安全粘贴：处理图片部分在画面外的情况"""
    bg_w, bg_h = bg.size
    iw, ih = img.size

    # 计算源图和目标的裁剪区域
    src_x1 = max(0, -x)
    src_y1 = max(0, -y)
    src_x2 = min(iw, bg_w - x)
    src_y2 = min(ih, bg_h - y)

    if src_x2 <= src_x1 or src_y2 <= src_y1:
        return  # 完全在画面外

    dst_x = max(0, x)
    dst_y = max(0, y)

    cropped = img.crop((src_x1, src_y1, src_x2, src_y2))
    if cropped.mode == 'RGBA':
        bg.paste(cropped, (dst_x, dst_y), cropped)
    else:
        bg.paste(cropped, (dst_x, dst_y))


@app.post("/api/create-animated-video")
async def create_animated_video(request: CreateAnimatedVideoRequest):
    """一步生成带小图入场动画效果的视频（跳过静态关键帧步骤）"""
    try:
        if not request.images:
            return JSONResponse(status_code=400,
                                content={"success": False, "message": "请至少选择一张图片"})

        from moviepy import ImageClip, concatenate_videoclips, AudioFileClip, VideoClip

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
                    from moviepy import concatenate_audioclips
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


@app.post("/api/process-image")
async def process_image(request: ProcessImageRequest):
    """处理图片"""
    try:
        image_path = Path(request.image_path.lstrip('/'))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")
        
        img = Image.open(image_path)
        
        if request.effect == "enhance":
            img = ImageEnhance.Contrast(img).enhance(1.3)
            img = ImageEnhance.Sharpness(img).enhance(1.2)
        elif request.effect == "blur":
            img = img.filter(ImageFilter.GaussianBlur(radius=5))
        elif request.effect == "sharpen":
            img = img.filter(ImageFilter.SHARPEN)
        elif request.effect == "grayscale":
            img = img.convert('L').convert('RGB')
        
        output_dir = image_path.parent / "processed"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{image_path.stem}_{request.effect}{image_path.suffix}"
        img.save(output_path, quality=95)
        
        relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
        logger.success(f"图片处理成功: {output_path}")
        
        return {
            "success": True,
            "message": "图片处理成功",
            "processed_path": f"/{relative_path}"
        }
    except Exception as e:
        logger.error(f"图片处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/api/detect-watermark")
async def detect_watermark(request: DetectWatermarkRequest):
    """自动检测图片中可能的水印区域"""
    try:
        image_path = Path(request.image_path.lstrip('/'))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")
        
        img = cv2.imread(str(image_path))
        if img is None:
            return {"success": False, "message": "无法读取图片"}
        
        h, w = img.shape[:2]
        regions = []
        
        # 策略1: 扫描四个角落区域（水印最常出现的位置）
        corner_regions = [
            (int(w * 0.65), int(h * 0.90), int(w * 0.35), int(h * 0.10)),  # 右下角
            (0, int(h * 0.90), int(w * 0.35), int(h * 0.10)),              # 左下角
            (int(w * 0.65), 0, int(w * 0.35), int(h * 0.08)),              # 右上角
            (0, 0, int(w * 0.35), int(h * 0.08)),                          # 左上角
        ]
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        for rx, ry, rw, rh in corner_regions:
            roi = gray[ry:ry+rh, rx:rx+rw]
            if roi.size == 0:
                continue
            
            # 使用Canny边缘检测 + 形态学操作找文字/Logo区域
            edges = cv2.Canny(roi, 50, 150)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
            dilated = cv2.dilate(edges, kernel, iterations=2)
            
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                cx, cy, cw, ch = cv2.boundingRect(cnt)
                area = cw * ch
                roi_area = rw * rh
                # 过滤: 面积合理（不能太小也不能占满整个角落）
                if area < roi_area * 0.01 or area > roi_area * 0.9:
                    continue
                if cw < 20 or ch < 8:
                    continue
                
                # 转换为全图坐标，并适当扩展边界
                pad = 8
                abs_x = max(0, rx + cx - pad)
                abs_y = max(0, ry + cy - pad)
                abs_w = min(w - abs_x, cw + pad * 2)
                abs_h = min(h - abs_y, ch + pad * 2)
                regions.append({'x': abs_x, 'y': abs_y, 'width': abs_w, 'height': abs_h})
        
        # 合并重叠区域
        regions = merge_regions(regions)
        
        # 策略2: 如果角落没检测到，尝试查找半透明文字水印（全图高亮区域）
        if len(regions) == 0:
            # 查找接近白色的大面积文字（常见半透明水印）
            _, bright = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
            kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 10))
            bright_dilated = cv2.dilate(bright, kernel2, iterations=2)
            contours2, _ = cv2.findContours(bright_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours2:
                cx, cy, cw, ch = cv2.boundingRect(cnt)
                # 水印通常不会太小也不会太大
                if cw * ch < w * h * 0.001 or cw * ch > w * h * 0.3:
                    continue
                if cw < 30 or ch < 15:
                    continue
                pad = 10
                regions.append({
                    'x': max(0, cx - pad),
                    'y': max(0, cy - pad),
                    'width': min(w - max(0, cx - pad), cw + pad * 2),
                    'height': min(h - max(0, cy - pad), ch + pad * 2)
                })
            regions = merge_regions(regions)
        
        logger.info(f"水印检测完成: 找到 {len(regions)} 个可疑区域")
        return {
            "success": True,
            "regions": regions[:10],  # 最多返回10个
            "count": len(regions)
        }
    except Exception as e:
        logger.error(f"水印检测失败: {e}")
        return {"success": False, "message": str(e), "regions": []}


def merge_regions(regions):
    """合并重叠的区域"""
    if len(regions) <= 1:
        return regions
    
    merged = True
    while merged:
        merged = False
        new_regions = []
        used = set()
        for i in range(len(regions)):
            if i in used:
                continue
            r1 = regions[i]
            for j in range(i + 1, len(regions)):
                if j in used:
                    continue
                r2 = regions[j]
                # 检查是否重叠或相邻
                if (r1['x'] <= r2['x'] + r2['width'] + 10 and
                    r2['x'] <= r1['x'] + r1['width'] + 10 and
                    r1['y'] <= r2['y'] + r2['height'] + 10 and
                    r2['y'] <= r1['y'] + r1['height'] + 10):
                    # 合并
                    nx = min(r1['x'], r2['x'])
                    ny = min(r1['y'], r2['y'])
                    nx2 = max(r1['x'] + r1['width'], r2['x'] + r2['width'])
                    ny2 = max(r1['y'] + r1['height'], r2['y'] + r2['height'])
                    r1 = {'x': nx, 'y': ny, 'width': nx2 - nx, 'height': ny2 - ny}
                    used.add(j)
                    merged = True
            new_regions.append(r1)
            used.add(i)
        regions = new_regions
    return regions


# LaMa模型全局实例（延迟加载）
_simple_lama = None

def get_lama_model():
    """延迟加载LaMa模型，首次使用时初始化"""
    global _simple_lama
    if _simple_lama is None:
        logger.info("首次加载LaMa模型，请稍候...")
        from simple_lama_inpainting import SimpleLama
        _simple_lama = SimpleLama()
        logger.success("LaMa模型加载完成")
    return _simple_lama


@app.post("/api/remove-watermark")
async def remove_watermark(request: RemoveWatermarkRequest):
    """使用LaMa模型去除图片水印"""
    try:
        image_path = Path(request.image_path.lstrip('/'))
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")
        
        if not request.regions or len(request.regions) == 0:
            return {"success": False, "message": "请至少框选一个水印区域"}
        
        # 加载原图
        img = Image.open(image_path).convert("RGB")
        img_width, img_height = img.size
        
        # 根据regions创建mask（白色=需要修复的区域）
        mask = Image.new("L", (img_width, img_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        
        for region in request.regions:
            x = int(region.get('x', 0))
            y = int(region.get('y', 0))
            w = int(region.get('width', 0))
            h = int(region.get('height', 0))
            if w > 0 and h > 0:
                # 稍微扩大区域以获得更好的效果
                expand = 5
                x1 = max(0, x - expand)
                y1 = max(0, y - expand)
                x2 = min(img_width, x + w + expand)
                y2 = min(img_height, y + h + expand)
                mask_draw.rectangle([(x1, y1), (x2, y2)], fill=255)
        
        # 使用LaMa模型进行修复
        simple_lama = get_lama_model()
        result = simple_lama(img, mask)
        
        # 保存结果
        output_dir = image_path.parent / "watermark_removed"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        output_path = output_dir / f"{image_path.stem}_clean_{timestamp}{image_path.suffix}"
        result.save(output_path, quality=95)
        
        relative_path = str(output_path.relative_to(Path("."))).replace("\\", "/")
        logger.success(f"水印去除成功: {output_path}")
        
        return {
            "success": True,
            "message": "水印去除成功",
            "original_path": request.image_path,
            "cleaned_path": f"/{relative_path}",
            "regions_count": len(request.regions)
        }
    except Exception as e:
        logger.error(f"水印去除失败: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"水印去除失败: {str(e)}"}


if __name__ == "__main__":
    import uvicorn
    
    for p in ["data/fetched", "data/uploads", "logs", "static"]:
        Path(p).mkdir(parents=True, exist_ok=True)
    
    print("🚀 网页抓取服务已启动")
    print("🌐 访问: http://localhost:8080")
    print("📖 API文档: http://localhost:8080/docs")
    print("\n⚙️  配置DeepSeek API Key:")
    print("   编辑 .env 文件，设置 DEEPSEEK_API_KEY=你的密钥\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
