"""
异步文章爬虫服务
专为FastAPI设计，支持VentureBeat等网站的文章抓取
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import time
import os
from urllib.parse import urljoin, urlparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

@dataclass
class AsyncArticleData:
    """异步文章数据结构"""
    url: str
    title: str = ""
    author: str = ""
    publish_date: str = ""
    content: str = ""
    images: List[Dict[str, str]] = None
    tags: List[str] = None
    summary: str = ""
    downloaded_images: List[str] = None

class AsyncVentureBeatCrawler:
    """异步VentureBeat文章爬虫"""
    
    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    async def can_handle(self, url: str) -> bool:
        """判断是否能处理该URL"""
        return 'venturebeat.com' in url
    
    async def crawl_article(self, url: str) -> Optional[AsyncArticleData]:
        """异步抓取文章"""
        try:
            if not await self.can_handle(url):
                logger.warning(f"不支持的URL: {url}")
                return None
            
            logger.info(f"开始抓取VentureBeat文章: {url}")
            
            # 添加延迟避免请求过于频繁
            await asyncio.sleep(self.delay)
            
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        html_content = await response.text()
                        soup = BeautifulSoup(html_content, 'html.parser')
                        
                        article_data = AsyncArticleData(
                            url=url,
                            title=await self._extract_title(soup),
                            author=await self._extract_author(soup),
                            publish_date=await self._extract_publish_date(soup),
                            content=await self._extract_content(soup),
                            images=await self._extract_images(soup, url),
                            tags=await self._extract_tags(soup),
                            summary=await self._extract_summary(soup)
                        )
                        
                        logger.success(f"文章抓取成功: {article_data.title}")
                        return article_data
                    else:
                        logger.error(f"HTTP错误: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"抓取文章失败: {e}")
            return None
    
    async def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取标题"""
        title_elem = soup.find('h1')
        return title_elem.get_text(strip=True) if title_elem else "未找到标题"
    
    async def _extract_author(self, soup: BeautifulSoup) -> str:
        """提取作者"""
        author_selectors = ['[class*="author"] a', '[rel="author"]', '.byline-author']
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                return author_elem.get_text(strip=True)
        return "未知作者"
    
    async def _extract_publish_date(self, soup: BeautifulSoup) -> str:
        """提取发布日期"""
        time_elem = soup.find('time')
        if time_elem and time_elem.has_attr('datetime'):
            return time_elem['datetime']
        return datetime.now().isoformat()
    
    async def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取文章内容"""
        content_selectors = ['[class*="content"]', 'article', '.post-content']
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 清理不需要的元素
                for unwanted in content_elem.select('script, style, .ad, .advertisement, .related-posts, nav'):
                    unwanted.decompose()
                content_text = content_elem.get_text(separator='\n', strip=True)
                return content_text[:3000] + "..." if len(content_text) > 3000 else content_text
        return "未找到文章内容"
    
    async def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """提取图片信息"""
        images = []
        img_elements = soup.find_all('img')
        
        for img in img_elements:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                full_url = urljoin(base_url, src)
                alt_text = img.get('alt', '')
                images.append({
                    'url': full_url,
                    'alt': alt_text,
                    'title': img.get('title', '')
                })
        return images
    
    async def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """提取标签"""
        tags = []
        tag_selectors = ['.tags a', '.post-tags a', '[rel="tag"]']
        
        for selector in tag_selectors:
            tag_elements = soup.select(selector)
            for tag in tag_elements:
                tag_text = tag.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)
        return tags
    
    async def _extract_summary(self, soup: BeautifulSoup) -> str:
        """提取摘要"""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            return meta_desc.get('content', '')
        return ""
    
    async def download_images(self, article_data: AsyncArticleData, output_dir: str = "downloaded_images") -> List[str]:
        """异步下载图片"""
        if not article_data or not article_data.images:
            return []
        
        # 创建输出目录
        domain = urlparse(article_data.url).netloc
        images_dir = Path(output_dir) / domain.replace('.', '_')
        images_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded_images = []
        
        logger.info(f"开始下载 {len(article_data.images)} 张图片...")
        
        async with aiohttp.ClientSession() as session:
            for i, img_info in enumerate(article_data.images):
                try:
                    img_url = img_info['url']
                    logger.info(f"下载图片 {i+1}/{len(article_data.images)}: {img_info['alt'][:30]}...")
                    
                    # 添加请求头避免429错误
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Referer': article_data.url,
                        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
                    }
                    
                    async with session.get(img_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            # 检查内容类型
                            content_type = response.headers.get('content-type', '').lower()
                            if not content_type.startswith('image/'):
                                logger.warning(f"非图片内容类型: {content_type}, 尝试继续处理")
                            
                            # 生成文件名
                            parsed_url = urlparse(img_url)
                            filename = f"article_image_{i+1:03d}_{os.path.basename(parsed_url.path)}"
                            
                            # 如果没有扩展名，根据内容类型添加
                            if not any(filename.endswith(ext) for ext in ['.jpg', '.png', '.gif', '.webp', '.jpeg']):
                                if 'png' in content_type:
                                    filename += '.png'
                                elif 'webp' in content_type:
                                    filename += '.webp'
                                else:
                                    filename += '.jpg'
                            
                            filepath = images_dir / filename
                            
                            # 保存图片
                            content = await response.read()
                            with open(filepath, 'wb') as f:
                                f.write(content)
                            
                            # 验证是否为有效图片文件
                            if self._is_valid_image(filepath):
                                downloaded_images.append(str(filepath))
                                file_size = filepath.stat().st_size / 1024  # KB
                                logger.success(f"已保存 ({file_size:.1f} KB): {filepath.name}")
                            else:
                                logger.warning(f"下载的文件不是有效图片，删除: {filepath.name}")
                                filepath.unlink()  # 删除无效文件
                        else:
                            logger.warning(f"下载失败，状态码: {response.status}")
                            
                    # 增加延迟避免429错误
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"下载图片异常: {e}")
                    continue
        
        return downloaded_images
    
    def _is_valid_image(self, filepath: Path) -> bool:
        """检查文件是否为有效的图片文件"""
        try:
            # 检查文件大小
            if filepath.stat().st_size < 100:  # 小于100字节的文件不太可能是图片
                return False
            
            # 检查文件扩展名
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
            if filepath.suffix.lower() not in valid_extensions:
                return False
            
            # 简单的文件头检查
            with open(filepath, 'rb') as f:
                header = f.read(10)
                
            # JPEG文件头
            if header.startswith(b'\xff\xd8\xff'):
                return True
            # PNG文件头
            if header.startswith(b'\x89PNG\r\n\x1a\n'):
                return True
            # GIF文件头
            if header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
                return True
            
            return True  # 如果无法确定，暂时认为有效
            
        except Exception:
            return False

# 兼容性函数，用于现有代码
async def crawl_venturebeat_article_async(url: str) -> Optional[AsyncArticleData]:
    """异步抓取VentureBeat文章的便捷函数"""
    crawler = AsyncVentureBeatCrawler()
    return await crawler.crawl_article(url)

# 用于测试
if __name__ == "__main__":
    async def test_crawler():
        url = "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
        article_data = await crawl_venturebeat_article_async(url)
        if article_data:
            print(f"标题: {article_data.title}")
            print(f"作者: {article_data.author}")
            print(f"图片数量: {len(article_data.images)}")
    
    asyncio.run(test_crawler())