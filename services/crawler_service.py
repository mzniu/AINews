"""爬虫服务 - 处理网页抓取相关业务逻辑"""
from typing import Tuple, Dict, List
from pathlib import Path
from urllib.parse import urljoin, urlparse
import hashlib
import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime
import json
from loguru import logger
from services.video_thumbnail_service import video_thumbnail_service


class CrawlerService:
    """网页爬虫服务类"""
    
    @staticmethod
    async def get_page_content(url: str) -> Tuple[str, str]:
        """使用Playwright获取页面内容"""
        try:
            from playwright.async_api import async_playwright
            
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
            raise Exception(f"获取页面失败: {str(e)}")
    
    @staticmethod
    def extract_content(html: str, base_url: str) -> Dict:
        """提取页面内容和图片"""
        soup = BeautifulSoup(html, 'lxml')
        
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        content_selectors = [
            'article', 
            '.article-content',      # 36kr专用选择器
            '[class*="article"]',   # 更精确的文章选择器
            '[class*="content"]',   # 通用内容选择器
            '[class*="post"]', 
            '[id*="content"]', 
            'main', 
            '.main-content',
            'body'
        ]
        
        content_text = ""
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                content_text = elements[0].get_text(separator='\n', strip=True)
                if len(content_text) > 200:
                    break
        
        images = []
        videos = []  # 新增视频列表
        
        # 检查网站类型
        parsed_url = urlparse(base_url)
        is_qbitai = 'qbitai.com' in parsed_url.netloc
        is_36kr = '36kr.com' in parsed_url.netloc
        is_wechat = 'mp.weixin.qq.com' in parsed_url.netloc
        is_toutiao = 'toutiao.com' in parsed_url.netloc
        
        if is_qbitai:
            # qbitai网站：提取syl-page-img和pgc-img类的图片
            logger.info("检测到qbitai网站，提取syl-page-img和pgc-img类的图片")
            
            # 提取syl-page-img类图片
            syl_img_elements = soup.find_all('img', class_='syl-page-img')
            for img in syl_img_elements:
                src = img.get('src') or img.get('data-src') or img.get('data-original')
                if src and not src.startswith('data:'):
                    images.append({
                        'url': urljoin(base_url, src),
                        'alt': img.get('alt', ''),
                        'class': 'syl-page-img'
                    })
            
            # 提取pgc-img类图片（在pgc-img div容器内）
            pgc_containers = soup.find_all('div', class_='pgc-img')
            for container in pgc_containers:
                img = container.find('img')
                if img:
                    src = img.get('src') or img.get('data-src') or img.get('data-original')
                    if src and not src.startswith('data:'):
                        images.append({
                            'url': urljoin(base_url, src),
                            'alt': img.get('alt', ''),
                            'class': 'pgc-img'
                        })
            
            logger.info(f"qbitai网站提取完成: syl-page-img {len(syl_img_elements)}张, pgc-img {len(pgc_containers)}张")
            
        elif is_36kr:
            # 36kr网站：只提取image-wrapper类容器中的图片
            logger.info("检测到36kr网站，只提取image-wrapper类容器中的图片")
            
            # 查找所有image-wrapper容器（包括p标签和div标签）
            wrapper_containers = soup.find_all(['p', 'div'], class_='image-wrapper')
            logger.info(f"找到 {len(wrapper_containers)} 个image-wrapper容器")
            
            for container in wrapper_containers:
                # 在每个容器中查找图片
                imgs = container.find_all('img')
                for img in imgs:
                    src = img.get('src') or img.get('data-src') or img.get('data-original')
                    if src and not src.startswith('data:'):
                        images.append({
                            'url': urljoin(base_url, src),
                            'alt': img.get('alt', ''),
                            'class': 'image-wrapper',
                            'container': 'image-wrapper',
                            'data_img_size': img.get('data-img-size-val', '')
                        })
            
            logger.info(f"36kr网站提取完成: 共 {len(images)} 张图片")
            
        elif is_wechat:
            # 微信公众号：提取多种类型的图片
            logger.info("检测到微信公众号网站，提取文章内容中的图片")
            
            # 方案1: 标准的 rich_pages wxw-img 类图片
            wechat_img_elements = soup.find_all('img', class_='rich_pages wxw-img')
            logger.info(f"找到 {len(wechat_img_elements)} 个标准rich_pages wxw-img图片")
            
            for img in wechat_img_elements:
                src = img.get('data-src') or img.get('src')
                if src and not src.startswith('data:'):
                    # 处理微信图片URL
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(base_url, src)
                    
                    images.append({
                        'url': src,
                        'alt': img.get('alt', ''),
                        'class': 'rich_pages wxw-img',
                        'data_type': img.get('data-type', ''),
                        'data_ratio': img.get('data-ratio', ''),
                        'extraction_method': 'standard_class'
                    })
            
            # 方案2: 基于微信域名特征的图片识别
            all_images = soup.find_all('img')
            wechat_domain_count = 0
            
            for img in all_images:
                # 跳过已经处理过的图片
                if img in wechat_img_elements:
                    continue
                
                data_src = img.get('data-src', '')
                src = img.get('src', '')
                img_alt = img.get('alt', '')
                img_classes = img.get('class', [])
                
                # 识别微信图片的多种特征
                is_wechat_image = (
                    # 微信图片域名特征
                    'mmbiz.qpic.cn' in data_src or 'mmbiz.qpic.cn' in src or
                    'sz_mmbiz' in data_src or 'sz_mmbiz' in src or
                    # 微信特有的data属性
                    img.get('data-type') or img.get('data-ratio') or img.get('data-w') or
                    # 微信图片通常有alt描述
                    (img_alt and len(img_alt.strip()) > 0 and 'data:' not in src)
                )
                
                if is_wechat_image:
                    final_src = data_src or src
                    if final_src and not final_src.startswith('data:'):
                        # 处理URL
                        if final_src.startswith('//'):
                            final_src = 'https:' + final_src
                        elif final_src.startswith('/'):
                            final_src = urljoin(base_url, final_src)
                        
                        images.append({
                            'url': final_src,
                            'alt': img_alt,
                            'class': ' '.join(img_classes) if img_classes else 'no-class',
                            'data_type': img.get('data-type', ''),
                            'data_ratio': img.get('data-ratio', ''),
                            'data_w': img.get('data-w', ''),
                            'extraction_method': 'domain_feature'
                        })
                        wechat_domain_count += 1
            
            logger.info(f"通过域名特征识别: {wechat_domain_count} 张图片")
            logger.info(f"微信公众号提取完成: 共 {len(images)} 张图片")
            
        elif is_toutiao:
            # 今日头条：提取pgc-img容器中的图片
            logger.info("检测到今日头条网站，提取pgc-img容器中的图片")
            
            # 提取pgc-img容器中的图片
            toutiao_containers = soup.find_all('div', class_='pgc-img')
            logger.info(f"找到 {len(toutiao_containers)} 个pgc-img容器")
            
            for container in toutiao_containers:
                img = container.find('img')
                if img:
                    # 今日头条可能使用src或data-src属性
                    src = img.get('data-src') or img.get('src')
                    if src and not src.startswith('data:'):
                        # 处理相对URL
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = urljoin(base_url, src)
                        
                        images.append({
                            'url': src,
                            'alt': img.get('alt', ''),
                            'class': 'pgc-img',
                            'img_width': img.get('img_width'),
                            'img_height': img.get('img_height'),
                            'image_type': img.get('image_type'),
                            'mime_type': img.get('mime_type')
                        })
            
            logger.info(f"今日头条提取完成: 共 {len(images)} 张图片")
            
        # 新增：提取视频元素（适用于所有网站）
        video_elements = soup.find_all('video')
        logger.info(f"检测到 {len(video_elements)} 个视频元素")
        
        for video_elem in video_elements:
            video_src = video_elem.get('src')
            if not video_src:
                # 检查source子元素
                source_elem = video_elem.find('source')
                if source_elem:
                    video_src = source_elem.get('src')
            
            if video_src:
                # 处理相对URL
                if video_src.startswith('//'):
                    video_src = 'https:' + video_src
                elif video_src.startswith('/'):
                    video_src = urljoin(base_url, video_src)
                
                videos.append({
                    'url': video_src,
                    'poster': video_elem.get('poster', ''),
                    'width': video_elem.get('width'),
                    'height': video_elem.get('height'),
                    'controls': video_elem.get('controls'),
                    'source_page': base_url
                })
                
                logger.info(f"提取视频: {video_src[:100]}...")
            
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
        
        # 新增：提取视频元素（适用于所有网站）
        video_elements = soup.find_all('video')
        logger.info(f"检测到 {len(video_elements)} 个视频元素")
        
        for video_elem in video_elements:
            video_src = video_elem.get('src')
            if not video_src:
                # 检查source子元素
                source_elem = video_elem.find('source')
                if source_elem:
                    video_src = source_elem.get('src')
            
            if video_src:
                # 处理相对URL
                if video_src.startswith('//'):
                    video_src = 'https:' + video_src
                elif video_src.startswith('/'):
                    video_src = urljoin(base_url, video_src)
                
                videos.append({
                    'url': video_src,
                    'poster': video_elem.get('poster', ''),
                    'width': video_elem.get('width'),
                    'height': video_elem.get('height'),
                    'controls': video_elem.get('controls'),
                    'source_page': base_url
                })
                
                logger.info(f"提取视频: {video_src[:100]}...")
        
        logger.info(f"提取到 {len(images)} 张图片, {len(videos)} 个视频 (qbitai模式: {is_qbitai}, 36kr模式: {is_36kr}, 微信公众号模式: {is_wechat}, 今日头条模式: {is_toutiao})")
        return {'content': content_text, 'images': images, 'videos': videos}
    
    @staticmethod
    def download_video(video_url: str, save_dir: Path, index: int, page_url: str = '', max_size_mb: int = 50) -> Dict:
        """下载视频文件（带大小限制和重试机制）"""
        max_retries = 3
        retry_delay = 3  # 3秒间隔
        
        for attempt in range(max_retries):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': page_url or video_url,
                    'Accept': '*/*',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                }
                
                # 先检查文件大小
                head_response = requests.head(video_url, headers=headers, timeout=10)
                if head_response.status_code == 200:
                    content_length = head_response.headers.get('content-length')
                    if content_length:
                        size_mb = int(content_length) / (1024 * 1024)
                        if size_mb > max_size_mb:
                            logger.warning(f"视频文件过大 ({size_mb:.1f}MB > {max_size_mb}MB): {video_url}")
                            return {
                                'url': video_url,
                                'success': False,
                                'error': f'文件过大: {size_mb:.1f}MB',
                                'size_mb': size_mb
                            }
                
                # 下载视频文件
                response = requests.get(video_url, headers=headers, timeout=30, stream=True)
                response.raise_for_status()
                
                # 生成文件名
                parsed_url = urlparse(video_url)
                ext = Path(parsed_url.path).suffix.lower()
                if not ext or ext not in ['.mp4', '.webm', '.mov', '.avi', '.mkv']:
                    content_type = response.headers.get('content-type', '')
                    if 'video/mp4' in content_type:
                        ext = '.mp4'
                    elif 'video/webm' in content_type:
                        ext = '.webm'
                    else:
                        ext = '.mp4'  # 默认mp4
                
                filename = f"video_{index:03d}{ext}"
                filepath = save_dir / filename
                
                # 保存文件
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # 验证文件
                if filepath.exists() and filepath.stat().st_size > 0:
                    file_size = filepath.stat().st_size / (1024 * 1024)
                    logger.success(f"✅ 视频下载成功: {filename} ({file_size:.1f}MB)")
                    
                    # 生成视频缩略图
                    try:
                        thumbnail_dir = save_dir.parent / "thumbnails"
                        thumbnail_path = str(thumbnail_dir / f"{filename}_thumb.jpg")
                        
                        if video_thumbnail_service.generate_video_thumbnail(
                            str(filepath), thumbnail_path, (320, 180)
                        ):
                            logger.info(f"✅ 视频缩略图生成成功: {thumbnail_path}")
                            thumbnail_relative = str(Path(thumbnail_path).relative_to(Path("."))).replace("\\", "/")
                        else:
                            thumbnail_relative = None
                            logger.warning(f"❌ 视频缩略图生成失败: {filename}")
                    except Exception as thumb_error:
                        logger.error(f"生成缩略图时出错: {thumb_error}")
                        thumbnail_relative = None
                    
                    relative_path = str(filepath.relative_to(Path("."))).replace("\\", "/")
                    return {
                        'url': video_url,
                        'local_path': f"/{relative_path}",
                        'thumbnail_path': f"/{thumbnail_relative}" if thumbnail_relative else None,
                        'filename': filename,
                        'size_mb': file_size,
                        'success': True
                    }
                else:
                    raise Exception("文件下载不完整")
                    
            except Exception as e:
                logger.warning(f"视频下载失败 (尝试 {attempt + 1}/{max_retries}): {video_url} - {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    return {
                        'url': video_url,
                        'success': False,
                        'error': str(e)
                    }
        
        return {'url': video_url, 'success': False, 'error': '下载失败'}
    
    @staticmethod
    def download_image(image_url: str, save_dir: Path, index: int, page_url: str = '') -> Dict:
        """下载图片（增强GIF支持，带重试机制）"""
        max_retries = 3
        retry_delay = 3  # 3秒间隔
        
        for attempt in range(max_retries):
            try:
                # 跳过 data URI
                if image_url.startswith('data:'):
                    # 特殊处理GIF data URI
                    if image_url.startswith('data:image/gif'):
                        return CrawlerService._handle_gif_data_uri(image_url, save_dir, index)
                    return {'url': image_url[:50], 'success': False, 'error': 'data URI, skipped'}
                
                # 发送HEAD请求获取真实内容类型
                try:
                    head_response = requests.head(image_url, timeout=10, allow_redirects=True)
                    content_type = head_response.headers.get('content-type', '').lower()
                    
                    # 根据Content-Type确定扩展名
                    if 'gif' in content_type:
                        ext = '.gif'
                    elif 'png' in content_type:
                        ext = '.png'
                    elif 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    else:
                        # 回退到URL路径提取
                        ext = Path(urlparse(image_url).path).suffix or '.jpg'
                except:
                    # HEAD请求失败时回退到默认逻辑
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
                
                # 验证文件是否为有效的图片
                try:
                    from PIL import Image
                    with Image.open(filepath) as img:
                        img.verify()
                except Exception:
                    filepath.unlink()  # 删除无效文件
                    return {'url': image_url, 'success': False, 'error': 'Invalid image file'}
                
                relative_path = str(filepath.relative_to(Path("."))).replace("\\", "/")
                return {'url': image_url, 'local_path': f"/{relative_path}", 'success': True, 'format': ext[1:].upper()}
                
            except Exception as e:
                # 检查是否为网络连接相关的错误
                error_msg = str(e).lower()
                is_connection_error = (
                    'connectionreseterror' in error_msg or
                    'connection aborted' in error_msg or
                    'connection broken' in error_msg or
                    'timeout' in error_msg or
                    'connect timeout' in error_msg or
                    'read timeout' in error_msg
                )
                
                if is_connection_error and attempt < max_retries - 1:
                    logger.warning(f"图片下载失败 {index}: {e}, 第{attempt + 1}次重试中...")
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    # 最后一次尝试失败或其他错误
                    if attempt == max_retries - 1:
                        logger.warning(f"图片下载失败 {index}: {e}, 已重试{max_retries}次，跳过该图片")
                    return {'url': image_url, 'success': False, 'error': str(e)}
        
        # 理论上不会到达这里
        return {'url': image_url, 'success': False, 'error': 'Unknown error'}
    
    @staticmethod
    def _handle_gif_data_uri(data_uri: str, save_dir: Path, index: int) -> Dict:
        """处理GIF格式的data URI"""
        try:
            # 解码base64数据
            import base64
            import re
            
            # 提取base64数据部分
            match = re.search(r'data:image/gif;base64,(.*)', data_uri)
            if not match:
                return {'url': data_uri[:50], 'success': False, 'error': 'Invalid GIF data URI format'}
            
            base64_data = match.group(1)
            gif_data = base64.b64decode(base64_data)
            
            # 保存GIF文件
            filename = f"image_{index:03d}.gif"
            filepath = save_dir / filename
            filepath.write_bytes(gif_data)
            
            relative_path = str(filepath.relative_to(Path("."))).replace("\\", "/")
            return {'url': data_uri[:50] + '...', 'local_path': f"/{relative_path}", 'success': True, 'format': 'GIF'}
            
        except Exception as e:
            return {'url': data_uri[:50], 'success': False, 'error': f'Failed to decode GIF data URI: {str(e)}'}
    
    @staticmethod
    def save_results(url: str, title: str, content: str, images: List, videos: List = None) -> Dict:
        """保存抓取结果（支持图片和视频下载）"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        save_dir = Path("data/fetched") / f"{url_hash}_{timestamp}"
        images_dir = save_dir / "images"
        videos_dir = save_dir / "videos"  # 新增视频目录
        images_dir.mkdir(parents=True, exist_ok=True)
        if videos:
            videos_dir.mkdir(parents=True, exist_ok=True)
        
        # 下载图片（只有当图片数组不为空时才下载）
        downloaded_images = []
        if images:  # 只有当有图片需要下载时才执行
            logger.info(f"开始下载 {len(images)} 张图片...")
            for i, img in enumerate(images, 1):
                logger.info(f"正在下载图片 {i}/{len(images)}: {img['url'][:50]}...")
                result = CrawlerService.download_image(img['url'], images_dir, i, page_url=url)
                downloaded_images.append(result)
                if not result['success']:
                    logger.warning(f"图片下载失败 {i}: {result.get('error', 'Unknown error')}")
            logger.info(f"图片下载完成: 成功 {len([img for img in downloaded_images if img['success']])}/{len(images)} 张")
        else:
            logger.info("没有图片需要下载")
            # 如果没有图片需要下载，但仍需要构建正确的元数据结构
            downloaded_images = []
        
        # 下载视频（如果有的话）
        downloaded_videos = []
        if videos:
            logger.info(f"开始下载 {len(videos)} 个视频...")
            for i, video in enumerate(videos, 1):
                logger.info(f"正在下载视频 {i}/{len(videos)}: {video['url'][:50]}...")
                result = CrawlerService.download_video(video['url'], videos_dir, i, page_url=url)
                downloaded_videos.append(result)
                if not result['success']:
                    logger.warning(f"视频下载失败 {i}: {result.get('error', 'Unknown error')}")
            logger.info(f"视频下载完成: 成功 {len([video for video in downloaded_videos if video['success']])}/{len(videos)} 个")
        
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
        
        # 添加视频信息到元数据
        if videos:
            metadata['videos_count'] = len([video for video in downloaded_videos if video['success']])
            metadata['videos'] = downloaded_videos
            metadata['content_preview'] += f"\n\n视频数量: {len(videos)} 个"
        
        with open(save_dir / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        relative_dir = str(save_dir.relative_to(Path("."))).replace("\\", "/")
        metadata['content_file'] = f"/{relative_dir}/content.txt"
        metadata['metadata_file'] = f"/{relative_dir}/metadata.json"
        
        logger.success(f"保存完成! 目录: {save_dir}")
        logger.info(f"- 内容文件: {content_file}")
        logger.info(f"- 元数据: {save_dir / 'metadata.json'}")
        logger.info(f"- 图片数量: {len(downloaded_images)}")
        if videos:
            logger.info(f"- 视频数量: {len(downloaded_videos)}")
        
        return metadata