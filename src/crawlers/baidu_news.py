"""百度新闻搜索爬虫 - 搜索AI相关新闻"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from typing import List, Optional
from datetime import datetime
import re
from urllib.parse import quote, unquote

from src.crawlers.base import BaseCrawler
from src.models.article import Article
from src.utils.logger import logger


class BaiduNewsAICrawler(BaseCrawler):
    """百度新闻AI搜索爬虫"""
    
    def __init__(self):
        super().__init__("baidu_news_ai")
        self.base_url = "https://www.baidu.com"
        # 搜索关键词：人工智能、AI、深度学习等
        keywords = ["人工智能", "AI大模型", "ChatGPT", "深度学习"]
        self.search_urls = [
            f"https://www.baidu.com/s?tn=news&word={quote(kw)}"
            for kw in keywords
        ]
    
    def parse_list(self, html: str) -> List[str]:
        """解析搜索结果页，提取新闻链接"""
        soup = self.parse_html(html)
        article_urls = []
        
        # 百度新闻搜索结果
        results = soup.find_all('div', class_='result')
        
        for result in results:
            link = result.find('a')
            if link and link.get('href'):
                url = link['href']
                # 跳过百度内部链接
                if url and not url.startswith('/'):
                    article_urls.append(url)
        
        return article_urls
    
    def parse_detail(self, url: str, html: str) -> Optional[Article]:
        """解析新闻详情"""
        try:
            soup = self.parse_html(html)
            
            # 通用新闻页面解析
            title = None
            title_candidates = [
                soup.find('h1'),
                soup.find('meta', property='og:title'),
                soup.find('title'),
            ]
            
            for elem in title_candidates:
                if elem:
                    if elem.name == 'meta':
                        title = elem.get('content')
                    else:
                        title = elem.get_text(strip=True)
                    if title and len(title) > 5:
                        break
            
            if not title:
                return None
            
            # 提取正文
            content = ""
            content_candidates = [
                soup.find('article'),
                soup.find('div', class_=re.compile(r'content|article|post')),
                soup.find('div', id=re.compile(r'content|article|post')),
            ]
            
            for elem in content_candidates:
                if elem:
                    # 清理
                    for tag in elem.find_all(['script', 'style', 'iframe']):
                        tag.decompose()
                    content = elem.get_text(separator='\n', strip=True)
                    if len(content) > 100:
                        break
            
            if len(content) < 100:
                logger.warning(f"内容过短: {url}")
                return None
            
            # 创建文章对象
            article = Article(
                id=self.get_url_hash(url),
                title=title,
                url=url,
                source=self.source_name,
                content=content,
                tags=["AI", "人工智能"],
                publish_time=datetime.now()  # 默认当前时间
            )
            
            return article
            
        except Exception as e:
            logger.error(f"解析失败 {url}: {e}")
            return None
    
    def crawl_latest(self, max_articles: int = 10) -> List[Article]:
        """爬取最新AI新闻"""
        all_articles = []
        
        for search_url in self.search_urls[:2]:  # 只搜索前2个关键词
            logger.info(f"搜索: {search_url}")
            articles = self.crawl_list(search_url, max_articles=5)
            all_articles.extend(articles)
            
            if len(all_articles) >= max_articles:
                break
        
        return all_articles[:max_articles]


if __name__ == "__main__":
    logger.info("开始爬取百度AI新闻")
    
    crawler = BaiduNewsAICrawler()
    articles = crawler.crawl_latest(max_articles=5)
    
    logger.success(f"成功爬取 {len(articles)} 篇文章")
    
    for i, article in enumerate(articles, 1):
        logger.info(f"\n[{i}] {article.title}")
        logger.info(f"    URL: {article.url}")
        logger.info(f"    内容: {article.content[:100]}...")
    
    if articles:
        crawler.save_articles(articles)
