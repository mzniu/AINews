"""36氪AI频道爬虫 - 作为机器之心的备用方案"""
from typing import List, Optional
from datetime import datetime
import re
import time

from src.crawlers.base import BaseCrawler
from src.models.article import Article
from src.utils.logger import logger


class Kr36AICrawler(BaseCrawler):
    """36氪AI频道爬虫"""
    
    def __init__(self):
        super().__init__("36kr_ai")
        self.base_url = "https://www.36kr.com"
        self.list_url = "https://www.36kr.com/information/AI/"
        self.use_playwright = True  # 使用Playwright
    
    def parse_list(self, html: str) -> List[str]:
        """解析列表页，提取文章链接"""
        soup = self.parse_html(html)
        article_urls = []
        
        # 36氪的文章链接格式：/p/数字 或 /newsflashes/数字
        # 支持多种链接格式
        patterns = [
            re.compile(r'/p/\d+'),
            re.compile(r'/newsflashes/\d+'),
            re.compile(r'/information/\w+/\d+'),
        ]
        
        for pattern in patterns:
            article_links = soup.find_all('a', href=pattern)
            for link in article_links:
                href = link.get('href')
                if href:
                    # 构建完整URL
                    if href.startswith('/'):
                        full_url = self.base_url + href
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        continue
                    
                    if full_url not in article_urls:
                        article_urls.append(full_url)
        
        # 如果没找到，尝试查找所有包含特定class的链接
        if not article_urls:
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                # 36氪文章通常包含这些路径
                if any(x in href for x in ['/p/', '/newsflashes/', '/information/']):
                    if href.startswith('/'):
                        full_url = self.base_url + href
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        continue
                    
                    if full_url not in article_urls:
                        article_urls.append(full_url)
        
        return article_urls
    
    def parse_detail(self, url: str, html: str) -> Optional[Article]:
        """解析详情页，提取文章信息"""
        try:
            soup = self.parse_html(html)
            
            # 提取标题
            title = None
            title_selectors = [
                soup.find('h1', class_='article-title'),
                soup.find('h1'),
                soup.find('meta', property='og:title'),
            ]
            
            for elem in title_selectors:
                if elem:
                    if elem.name == 'meta':
                        title = elem.get('content')
                    else:
                        title = elem.get_text(strip=True)
                    if title:
                        break
            
            if not title:
                logger.warning(f"未找到标题: {url}")
                return None
            
            # 提取作者
            author = None
            author_elem = soup.find('a', class_='author') or soup.find('span', class_='author')
            if author_elem:
                author = author_elem.get_text(strip=True)
            
            # 提取发布时间
            publish_time = None
            time_elem = soup.find('time') or soup.find('span', class_='time')
            if time_elem:
                time_str = time_elem.get('datetime') or time_elem.get_text(strip=True)
                try:
                    # 尝试解析时间
                    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y年%m月%d日"]:
                        try:
                            publish_time = datetime.strptime(time_str.split()[0], fmt)
                            break
                        except:
                            continue
                except:
                    logger.warning(f"解析时间失败: {time_str}")
            
            # 提取正文内容
            content_elem = soup.find('div', class_='article-content') or soup.find('article')
            if not content_elem:
                logger.warning(f"未找到正文: {url}")
                return None
            
            # 清理内容
            for tag in content_elem.find_all(['script', 'style', 'iframe']):
                tag.decompose()
            
            content = content_elem.get_text(separator='\n', strip=True)
            
            # 提取图片
            images = []
            for img in content_elem.find_all('img'):
                img_url = img.get('src') or img.get('data-src')
                if img_url:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = self.base_url + img_url
                    images.append(img_url)
            
            # 提取标签
            tags = ["AI", "人工智能"]  # 默认标签
            tag_elems = soup.find_all('a', class_='tag')
            for tag_elem in tag_elems:
                tag_text = tag_elem.get_text(strip=True)
                if tag_text:
                    tags.append(tag_text)
            
            # 提取摘要
            summary = None
            summary_elem = soup.find('meta', {'name': 'description'})
            if summary_elem:
                summary = summary_elem.get('content')
            
            # 创建Article对象
            article = Article(
                id=self.get_url_hash(url),
                title=title,
                url=url,
                source=self.source_name,
                author=author,
                publish_time=publish_time,
                content=content,
                summary=summary,
                tags=tags,
                images=images[:5]
            )
            
            return article
            
        except Exception as e:
            logger.error(f"解析文章失败 {url}: {str(e)}")
            return None
    
    def crawl_latest(self, max_articles: int = 10) -> List[Article]:
        """爬取最新文章"""
        return self.crawl_list(self.list_url, max_articles)
