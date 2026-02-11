"""爬虫服务 - 处理网页抓取相关业务逻辑"""
from typing import Tuple, Dict, List
from pathlib import Path
from urllib.parse import urljoin, urlparse
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
from loguru import logger


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
        
        # 检查网站类型
        parsed_url = urlparse(base_url)
        is_qbitai = 'qbitai.com' in parsed_url.netloc
        is_36kr = '36kr.com' in parsed_url.netloc
        
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
    
    @staticmethod
    def download_image(image_url: str, save_dir: Path, index: int, page_url: str = '') -> Dict:
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
    
    @staticmethod
    def save_results(url: str, title: str, content: str, images: List) -> Dict:
        """保存抓取结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        save_dir = Path("data/fetched") / f"{url_hash}_{timestamp}"
        images_dir = save_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded_images = [CrawlerService.download_image(img['url'], images_dir, i, page_url=url) for i, img in enumerate(images, 1)]
        
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