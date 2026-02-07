"""
网页抓取API服务 - 支持内容编辑和AI摘要生成
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from loguru import logger
from openai import OpenAI
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont
import cv2
import numpy as np
import os
from typing import List
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logger.add("logs/web_server_{time}.log", rotation="10 MB")

app = FastAPI(title="网页抓取API", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data", StaticFiles(directory="data"), name="data")


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


# 核心功能
async def get_page_content(url: str) -> tuple[str, str]:
    """使用Playwright获取页面"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
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
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        if src:
            images.append({
                'url': urljoin(base_url, src),
                'alt': img.get('alt', '')
            })
    
    return {'content': content_text, 'images': images}


def download_image(image_url: str, save_dir: Path, index: int) -> dict:
    """下载图片"""
    try:
        ext = Path(urlparse(image_url).path).suffix or '.jpg'
        filename = f"image_{index:03d}{ext}"
        filepath = save_dir / filename
        
        response = requests.get(image_url, headers={
            'User-Agent': 'Mozilla/5.0'
        }, timeout=10)
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
    
    downloaded_images = [download_image(img['url'], images_dir, i) for i, img in enumerate(images, 1)]
    
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
        
        prompt = f"""请为以下文章生成适合短视频的标题、摘要和标签，要求：
1. 标题：25字以内，吸引眼球，突出核心亮点
2. 摘要：100字以内，简洁明了，适合短视频解说
3. 标签：10个相关标签，每个标签以#开头，用空格分隔

原标题：{request.title}

正文：
{request.content[:3000]}

请按以下JSON格式返回：
{{
  "title": "生成的标题（25字以内）",
  "summary": "生成的摘要（100字以内）",
  "tags": "#AI #人工智能 #科技 ... (10个标签)"
}}"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是专业的AI资讯编辑，擅长提炼文章核心要点，生成适合短视频的标题、摘要和热门标签。请严格按照JSON格式返回结果。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        
        tags = result.get('tags', '')
        logger.success(f"标题和摘要生成成功 - 标题: {len(result['title'])}字, 摘要: {len(result['summary'])}字, 标签: {tags}")
        
        return {
            "success": True,
            "title": result['title'],
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
        
        # 加载字体
        try:
            title_font = ImageFont.truetype("msyh.ttc", 60)
            summary_font = ImageFont.truetype("msyh.ttc", 40)
        except:
            title_font = ImageFont.load_default()
            summary_font = ImageFont.load_default()
        
        # 文字自动换行函数
        def wrap_text(text, font, max_width, draw_obj):
            lines = []
            current_line = ""
            for char in text:
                test_line = current_line + char
                bbox = draw_obj.textbbox((0, 0), test_line, font=font)
                if bbox[2] - bbox[0] <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = char
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
                                   draw.textbbox((0, 0), line, font=title_font)[1] + 15 
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
                
                # 绘制标题背景（半透明灰色矩形）
                title_bg_y = current_y - 15
                title_bg_height = title_height + 20
                # 创建半透明层
                overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle(
                    [(0, title_bg_y), (img_width, title_bg_y + title_bg_height)],
                    fill=(50, 50, 50, 180)  # 深灰色，透明度180/255
                )
                bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
                draw = ImageDraw.Draw(bg)  # 重新创建draw对象
                
                # 绘制标题
                for line in title_lines:
                    bbox = draw.textbbox((0, 0), line, font=title_font)
                    line_width = bbox[2] - bbox[0]
                    x = margin + (text_width - line_width) // 2
                    
                    # 阴影
                    draw.text((x + 2, current_y + 2), line, font=title_font, fill=(0, 0, 0))
                    # 文字
                    draw.text((x, current_y), line, font=title_font, fill=(255, 255, 255))
                    current_y += bbox[3] - bbox[1] + 15
                
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
                
                # 绘制摘要背景（半透明灰色矩形，固定在底部15%）
                current_y = summary_start_y
                summary_bg_y = current_y - 15
                summary_bg_height = summary_height + 20
                overlay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle(
                    [(0, summary_bg_y), (img_width, summary_bg_y + summary_bg_height)],
                    fill=(50, 50, 50, 180)  # 深灰色，透明度180/255
                )
                bg = Image.alpha_composite(bg.convert('RGBA'), overlay).convert('RGB')
                draw = ImageDraw.Draw(bg)  # 重新创建draw对象
                
                # 绘制摘要（图片下方）
                for line in summary_lines:
                    bbox = draw.textbbox((0, 0), line, font=summary_font)
                    line_width = bbox[2] - bbox[0]
                    x = margin + (text_width - line_width) // 2
                    
                    # 阴影
                    draw.text((x + 2, current_y + 2), line, font=summary_font, fill=(0, 0, 0))
                    # 文字
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
                frame_duration = 3.0
            
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
    
    for p in ["data/fetched", "logs", "static"]:
        Path(p).mkdir(parents=True, exist_ok=True)
    
    print("🚀 网页抓取服务已启动")
    print("🌐 访问: http://localhost:8000")
    print("📖 API文档: http://localhost:8000/docs")
    print("\n⚙️  配置DeepSeek API Key:")
    print("   编辑 .env 文件，设置 DEEPSEEK_API_KEY=你的密钥\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
