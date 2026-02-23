"""
VentureBeat文章页面爬虫
用于抓取文章内容和图片
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
import time
from loguru import logger

class VentureBeatCrawler:
    """VentureBeat网站爬虫"""
    
    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.headers
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def fetch_page(self, url: str) -> str:
        """获取页面内容"""
        try:
            await asyncio.sleep(self.delay)  # 请求间隔
            
            logger.info(f"正在抓取: {url}")
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    logger.info(f"成功获取页面，大小: {len(content)} 字符")
                    return content
                else:
                    logger.error(f"HTTP错误: {response.status}")
                    return ""
        except Exception as e:
            logger.error(f"抓取页面失败: {e}")
            return ""
    
    def parse_article_content(self, html_content: str, base_url: str) -> dict:
        """解析文章内容"""
        soup = BeautifulSoup(html_content, 'html.parser')
        result = {
            'title': '',
            'author': '',
            'publish_date': '',
            'content': '',
            'images': [],
            'tags': []
        }
        
        # 提取标题
        title_selectors = [
            'h1.article-title',
            'h1.entry-title',
            'h1.post-title',
            'h1[class*="title"]',
            'title'
        ]
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                result['title'] = title_elem.get_text(strip=True)
                break
        
        # 提取作者
        author_selectors = [
            '.author-name',
            '.byline-author',
            '[rel="author"]',
            '.post-author a',
            '.entry-author'
        ]
        
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                result['author'] = author_elem.get_text(strip=True)
                break
        
        # 提取发布日期
        date_selectors = [
            'time[datetime]',
            '.published',
            '.post-date',
            '.entry-date',
            '[class*="date"]'
        ]
        
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                if date_elem.has_attr('datetime'):
                    result['publish_date'] = date_elem['datetime']
                else:
                    result['publish_date'] = date_elem.get_text(strip=True)
                break
        
        # 提取主要内容
        content_selectors = [
            '.article-content',
            '.post-content',
            '.entry-content',
            '.content',
            '[class*="content"] article',
            'main article'
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 移除不需要的元素
                for unwanted in content_elem.select('script, style, .ad, .advertisement, .related-posts'):
                    unwanted.decompose()
                
                result['content'] = content_elem.get_text(strip=True, separator='\n')
                break
        
        # 提取图片
        img_selectors = [
            '.article-content img',
            '.post-content img',
            '.entry-content img',
            'article img',
            'main img'
        ]
        
        for selector in img_selectors:
            img_elements = soup.select(selector)
            for img in img_elements:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    full_url = urljoin(base_url, src)
                    alt_text = img.get('alt', '')
                    result['images'].append({
                        'url': full_url,
                        'alt': alt_text,
                        'title': img.get('title', '')
                    })
        
        # 提取标签
        tag_selectors = [
            '.tags a',
            '.post-tags a',
            '.entry-tags a',
            '[rel="tag"]'
        ]
        
        for selector in tag_selectors:
            tag_elements = soup.select(selector)
            for tag in tag_elements:
                tag_text = tag.get_text(strip=True)
                if tag_text and tag_text not in result['tags']:
                    result['tags'].append(tag_text)
        
        return result
    
    async def download_image(self, image_url: str, save_path: Path) -> bool:
        """下载图片"""
        try:
            async with self.session.get(image_url) as response:
                if response.status == 200:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                    logger.info(f"图片下载成功: {save_path}")
                    return True
                else:
                    logger.error(f"图片下载失败 {response.status}: {image_url}")
                    return False
        except Exception as e:
            logger.error(f"下载图片异常: {e}")
            return False
    
    async def crawl_article(self, url: str, download_images: bool = True) -> dict:
        """爬取完整文章"""
        try:
            # 获取页面内容
            html_content = await self.fetch_page(url)
            if not html_content:
                return {}
            
            # 解析文章内容
            article_data = self.parse_article_content(html_content, url)
            
            # 下载图片
            if download_images and article_data.get('images'):
                logger.info(f"开始下载 {len(article_data['images'])} 张图片")
                images_dir = Path("downloaded_images") / urlparse(url).netloc
                downloaded_images = []
                
                for i, img_info in enumerate(article_data['images']):
                    try:
                        img_filename = f"image_{i+1:03d}_{Path(urlparse(img_info['url']).path).name}"
                        img_path = images_dir / img_filename
                        
                        if await self.download_image(img_info['url'], img_path):
                            downloaded_images.append(str(img_path))
                            
                    except Exception as e:
                        logger.error(f"处理图片失败: {e}")
                        continue
                
                article_data['downloaded_images'] = downloaded_images
            
            return article_data
            
        except Exception as e:
            logger.error(f"爬取文章失败: {e}")
            return {}

# 测试函数
async def test_venturebeat_crawler():
    """测试VentureBeat爬虫"""
    url = "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    
    print("🚀 开始测试VentureBeat爬虫")
    print("=" * 50)
    
    async with VentureBeatCrawler(delay=3.0) as crawler:
        article_data = await crawler.crawl_article(url, download_images=True)
        
        if article_data:
            print("✅ 文章抓取成功!")
            print(f"标题: {article_data.get('title', 'N/A')}")
            print(f"作者: {article_data.get('author', 'N/A')}")
            print(f"发布时间: {article_data.get('publish_date', 'N/A')}")
            print(f"内容长度: {len(article_data.get('content', ''))} 字符")
            print(f"图片数量: {len(article_data.get('images', []))}")
            print(f"下载图片: {len(article_data.get('downloaded_images', []))}")
            print(f"标签: {', '.join(article_data.get('tags', []))}")
            
            # 保存结果
            output_file = Path("venturebeat_article.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2)
            print(f"结果已保存到: {output_file}")
            
        else:
            print("❌ 文章抓取失败")

if __name__ == "__main__":
    asyncio.run(test_venturebeat_crawler())