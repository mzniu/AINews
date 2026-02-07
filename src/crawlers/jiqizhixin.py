"""机器之心爬虫"""
from typing import List, Optional
from datetime import datetime
import re

from src.crawlers.base import BaseCrawler
from src.models.article import Article
from src.utils.logger import logger


class JiqizhixinCrawler(BaseCrawler):
    """机器之心爬虫"""
    
    def __init__(self):
        super().__init__("jiqizhixin")
        self.base_url = "https://www.jiqizhixin.com"
        self.list_url = "https://www.jiqizhixin.com/articles"
        self.use_playwright = True  # 使用Playwright处理JS渲染
    
    def parse_list(self, html: str) -> List[str]:
        """解析列表页，提取文章链接"""
        soup = self.parse_html(html)
        article_urls = []
        
        # 查找所有文章链接
        # 机器之心的文章链接格式：/articles/2026-02-05-2
        article_links = soup.find_all('a', href=re.compile(r'/articles/\d{4}-\d{2}-\d{2}-\d+'))
        
        for link in article_links:
            href = link.get('href')
            if href:
                # 构建完整URL
                if href.startswith('/'):
                    full_url = self.base_url + href
                else:
                    full_url = href
                
                if full_url not in article_urls:
                    article_urls.append(full_url)
        
        return article_urls
    
    def parse_detail(self, url: str, html: str) -> Optional[Article]:
        """解析详情页，提取文章信息"""
        try:
            soup = self.parse_html(html)
            
            # 提取标题 - 尝试多种选择器
            title = None
            title_selectors = [
                soup.find('h1', class_='article-title'),
                soup.find('h1', class_='title'),
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
            author_elem = soup.find('span', class_='author') or soup.find('a', class_='author')
            if author_elem:
                author = author_elem.get_text(strip=True)
            
            # 提取发布时间
            publish_time = None
            time_elem = soup.find('time') or soup.find('span', class_='publish-time')
            if time_elem:
                time_str = time_elem.get('datetime') or time_elem.get_text(strip=True)
                try:
                    # 尝试多种时间格式
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
            
            # 清理内容，移除脚本和样式
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
            tags = []
            tag_elems = soup.find_all('a', class_='tag') or soup.find_all('span', class_='tag')
            for tag_elem in tag_elems:
                tag_text = tag_elem.get_text(strip=True)
                if tag_text:
                    tags.append(tag_text)
            
            # 提取摘要（如果有）
            summary = None
            summary_elem = soup.find('div', class_='article-summary') or soup.find('meta', {'name': 'description'})
            if summary_elem:
                if summary_elem.name == 'meta':
                    summary = summary_elem.get('content')
                else:
                    summary = summary_elem.get_text(strip=True)
            
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
                images=images[:5]  # 最多保存5张图片
            )
            
            return article
            
        except Exception as e:
            logger.error(f"解析文章失败 {url}: {str(e)}")
            return None
    
    def crawl_latest(self, max_articles: int = 10) -> List[Article]:
        """
        爬取最新文章
        
        Args:
            max_articles: 最大爬取数量
            
        Returns:
            Article对象列表
        """
        return self.crawl_list(self.list_url, max_articles)
