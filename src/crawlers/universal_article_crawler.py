"""
通用文章爬虫框架
支持多种网站的文章内容抓取
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import os
from urllib.parse import urljoin, urlparse
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ArticleData:
    """文章数据结构"""
    url: str
    title: str = ""
    author: str = ""
    publish_date: str = ""
    content: str = ""
    images: List[Dict[str, str]] = None
    tags: List[str] = None
    summary: str = ""
    downloaded_images: List[str] = None

class BaseArticleCrawler(ABC):
    """基础文章爬虫抽象类"""
    
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
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """判断是否能处理该URL"""
        pass
    
    @abstractmethod
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取标题"""
        pass
    
    @abstractmethod
    def _extract_author(self, soup: BeautifulSoup) -> str:
        """提取作者"""
        pass
    
    @abstractmethod
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """提取内容"""
        pass
    
    def get_article(self, url: str) -> Optional[ArticleData]:
        """获取文章数据"""
        try:
            if not self.can_handle(url):
                print(f"不支持的网站: {url}")
                return None
            
            print(f"正在抓取: {url}")
            time.sleep(self.delay)
            
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                article_data = ArticleData(
                    url=url,
                    title=self._extract_title(soup),
                    author=self._extract_author(soup),
                    publish_date=self._extract_publish_date(soup),
                    content=self._extract_content(soup),
                    images=self._extract_images(soup, url),
                    tags=self._extract_tags(soup),
                    summary=self._extract_summary(soup)
                )
                
                return article_data
            else:
                print(f"HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"抓取失败: {e}")
            return None
    
    def _extract_publish_date(self, soup: BeautifulSoup) -> str:
        """提取发布日期（通用实现）"""
        time_elem = soup.find('time')
        if time_elem and time_elem.has_attr('datetime'):
            return time_elem['datetime']
        return "未知日期"
    
    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """提取图片信息（通用实现）"""
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
    
    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """提取标签（通用实现）"""
        tags = []
        tag_selectors = ['.tags a', '.post-tags a', '[rel="tag"]']
        
        for selector in tag_selectors:
            tag_elements = soup.select(selector)
            for tag in tag_elements:
                tag_text = tag.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)
        return tags
    
    def _extract_summary(self, soup: BeautifulSoup) -> str:
        """提取摘要（通用实现）"""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            return meta_desc.get('content', '')
        return ""

class VentureBeatCrawler(BaseArticleCrawler):
    """VentureBeat专用爬虫"""
    
    def can_handle(self, url: str) -> bool:
        return 'venturebeat.com' in url
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        title_elem = soup.find('h1')
        return title_elem.get_text(strip=True) if title_elem else "未找到标题"
    
    def _extract_author(self, soup: BeautifulSoup) -> str:
        author_selectors = ['[class*="author"] a', '[rel="author"]', '.byline-author']
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                return author_elem.get_text(strip=True)
        return "未知作者"
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_selectors = ['[class*="content"]', 'article', '.post-content']
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 清理不需要的元素
                for unwanted in content_elem.select('script, style, .ad, .advertisement, .related-posts, nav'):
                    unwanted.decompose()
                content_text = content_elem.get_text(separator='\n', strip=True)
                return content_text[:2000] + "..." if len(content_text) > 2000 else content_text
        return "未找到文章内容"

class GenericCrawler(BaseArticleCrawler):
    """通用爬虫，适用于大多数网站"""
    
    def can_handle(self, url: str) -> bool:
        return True  # 通用爬虫可以处理任何URL
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        # 尝试多种标题选择器
        title_selectors = ['h1', 'h1[class*="title"]', 'title']
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                return title_elem.get_text(strip=True)
        return "未找到标题"
    
    def _extract_author(self, soup: BeautifulSoup) -> str:
        author_selectors = [
            '[rel="author"]', 
            '.author-name',
            '.byline-author a',
            '[class*="author"]'
        ]
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                return author_elem.get_text(strip=True)
        return "未知作者"
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_selectors = [
            'article',
            '[class*="content"]',
            '.post-content',
            '.entry-content',
            'main'
        ]
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 清理不需要的元素
                for unwanted in content_elem.select('script, style, .ad, .advertisement, .related-posts, nav, header, footer'):
                    unwanted.decompose()
                content_text = content_elem.get_text(separator='\n', strip=True)
                return content_text[:3000] + "..." if len(content_text) > 3000 else content_text
        return "未找到文章内容"

class ArticleCrawlerManager:
    """文章爬虫管理器"""
    
    def __init__(self):
        self.crawlers = [
            VentureBeatCrawler(),
            GenericCrawler()
        ]
    
    def crawl_article(self, url: str) -> Optional[ArticleData]:
        """根据URL选择合适的爬虫"""
        for crawler in self.crawlers:
            if crawler.can_handle(url):
                print(f"使用爬虫: {crawler.__class__.__name__}")
                return crawler.get_article(url)
        
        print("没有找到合适的爬虫")
        return None
    
    def download_images(self, article_data: ArticleData, output_dir: str = "downloaded_images") -> List[str]:
        """下载文章图片"""
        if not article_data or not article_data.images:
            return []
        
        # 创建输出目录
        domain = urlparse(article_data.url).netloc
        images_dir = Path(output_dir) / domain.replace('.', '_')
        images_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded_images = []
        
        print(f"开始下载 {len(article_data.images)} 张图片...")
        
        for i, img_info in enumerate(article_data.images):
            try:
                img_url = img_info['url']
                print(f"下载图片 {i+1}/{len(article_data.images)}: {img_url}")
                
                response = requests.get(img_url, headers=self.crawlers[0].headers, timeout=30)
                
                if response.status_code == 200:
                    # 生成文件名
                    parsed_url = urlparse(img_url)
                    filename = f"image_{i+1:03d}_{os.path.basename(parsed_url.path)}"
                    if not any(filename.endswith(ext) for ext in ['.jpg', '.png', '.gif', '.webp', '.jpeg']):
                        filename += '.jpg'
                    
                    filepath = images_dir / filename
                    
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    downloaded_images.append(str(filepath))
                    print(f"  ✓ 已保存: {filepath}")
                else:
                    print(f"  ✗ 下载失败，状态码: {response.status_code}")
                    
                time.sleep(1)
                
            except Exception as e:
                print(f"  ✗ 下载异常: {e}")
                continue
        
        return downloaded_images

def main():
    """测试函数"""
    urls = [
        "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero",
        # 可以添加其他网站的URL进行测试
    ]
    
    manager = ArticleCrawlerManager()
    
    for url in urls:
        print(f"\n{'='*60}")
        print(f"开始处理: {url}")
        print('='*60)
        
        # 抓取文章
        article_data = manager.crawl_article(url)
        
        if article_data:
            print("✅ 文章抓取成功!")
            print(f"标题: {article_data.title}")
            print(f"作者: {article_data.author}")
            print(f"发布日期: {article_data.publish_date}")
            print(f"内容长度: {len(article_data.content)} 字符")
            print(f"图片数量: {len(article_data.images)}")
            print(f"标签: {', '.join(article_data.tags)}")
            print(f"摘要: {article_data.summary[:100]}...")
            
            # 下载图片
            downloaded_images = manager.download_images(article_data)
            article_data.downloaded_images = downloaded_images
            print(f"🖼️  成功下载 {len(downloaded_images)} 张图片")
            
            # 保存数据
            filename = f"article_{urlparse(url).netloc.replace('.', '_')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(article_data.__dict__, f, ensure_ascii=False, indent=2, default=str)
            print(f"💾 数据已保存到 {filename}")
        else:
            print("❌ 文章抓取失败")

if __name__ == "__main__":
    main()