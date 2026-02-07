"""爬虫基类"""
from abc import ABC, abstractmethod
from typing import List, Optional
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime

from src.utils.logger import logger
from src.utils.config import Config
from src.models.article import Article


class BaseCrawler(ABC):
    """爬虫基类"""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': Config.USER_AGENT
        })
        self.crawled_urls = set()
        self.use_playwright = False  # 默认不使用playwright
        
    def get_url_hash(self, url: str) -> str:
        """生成URL哈希"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def is_duplicate(self, url: str) -> bool:
        """检查URL是否已爬取"""
        url_hash = self.get_url_hash(url)
        if url_hash in self.crawled_urls:
            return True
        self.crawled_urls.add(url_hash)
        return False
    
    def fetch_page(self, url: str, use_selenium: bool = False, use_playwright: bool = None) -> Optional[str]:
        """获取页面内容"""
        # 优先使用实例设置的playwright选项
        if use_playwright is None:
            use_playwright = getattr(self, 'use_playwright', False)
        
        try:
            logger.info(f"正在获取页面: {url}")
            
            if use_playwright:
                # 使用Playwright处理JavaScript渲染的页面
                return self._fetch_with_playwright(url)
            elif use_selenium:
                # 使用Selenium处理JavaScript渲染的页面
                return self._fetch_with_selenium(url)
            
            response = self.session.get(
                url,
                timeout=Config.CRAWLER_TIMEOUT,
                allow_redirects=True
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            
            # 延迟以避免过于频繁的请求
            time.sleep(Config.CRAWLER_DELAY)
            
            return response.text
        except requests.Timeout:
            logger.error(f"获取页面超时: {url}")
        except requests.ConnectionError:
            logger.error(f"连接错误: {url}")
        except Exception as e:
            logger.error(f"获取页面失败 {url}: {str(e)}")
        return None
    
    def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """使用Playwright获取页面"""
        try:
            from playwright.sync_api import sync_playwright
            
            logger.info(f"使用Playwright获取页面: {url}")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=Config.USER_AGENT
                )
                page = context.new_page()
                
                # 访问页面
                page.goto(url, wait_until='networkidle', timeout=30000)
                
                # 等待内容加载
                time.sleep(2)
                
                # 获取页面内容
                html = page.content()
                
                browser.close()
                
                logger.success(f"Playwright成功获取页面: {url}")
                return html
                
        except Exception as e:
            logger.error(f"Playwright获取页面失败 {url}: {str(e)}")
            return None
    
    def _fetch_with_selenium(self, url: str) -> Optional[str]:
        """使用Selenium获取页面"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument(f'user-agent={Config.USER_AGENT}')
            
            driver = webdriver.Chrome(options=options)
            driver.get(url)
            
            # 等待页面加载
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)  # 额外等待JavaScript执行
            
            html = driver.page_source
            driver.quit()
            
            return html
        except Exception as e:
            logger.error(f"Selenium获取页面失败 {url}: {str(e)}")
            return None
    
    def parse_html(self, html: str) -> BeautifulSoup:
        """解析HTML"""
        return BeautifulSoup(html, 'lxml')
    
    @abstractmethod
    def parse_list(self, html: str) -> List[str]:
        """
        解析列表页，提取文章链接
        
        Args:
            html: 列表页HTML内容
            
        Returns:
            文章链接列表
        """
        pass
    
    @abstractmethod
    def parse_detail(self, url: str, html: str) -> Optional[Article]:
        """
        解析详情页，提取文章信息
        
        Args:
            url: 文章URL
            html: 详情页HTML内容
            
        Returns:
            Article对象
        """
        pass
    
    def crawl_article(self, url: str) -> Optional[Article]:
        """
        爬取单篇文章
        
        Args:
            url: 文章URL
            
        Returns:
            Article对象
        """
        if self.is_duplicate(url):
            logger.info(f"文章已爬取，跳过: {url}")
            return None
        
        html = self.fetch_page(url)
        if not html:
            return None
        
        article = self.parse_detail(url, html)
        if article:
            logger.success(f"成功爬取文章: {article.title}")
        
        return article
    
    def crawl_list(self, list_url: str, max_articles: int = 10) -> List[Article]:
        """
        爬取列表页的文章
        
        Args:
            list_url: 列表页URL
            max_articles: 最大爬取数量
            
        Returns:
            Article对象列表
        """
        logger.info(f"开始爬取列表: {list_url}")
        
        html = self.fetch_page(list_url)
        if not html:
            return []
        
        article_urls = self.parse_list(html)
        logger.info(f"发现 {len(article_urls)} 篇文章")
        
        articles = []
        for url in article_urls[:max_articles]:
            article = self.crawl_article(url)
            if article:
                articles.append(article)
        
        logger.success(f"成功爬取 {len(articles)} 篇文章")
        return articles
    
    def save_articles(self, articles: List[Article], output_dir: Optional[str] = None):
        """
        保存文章到JSON文件
        
        Args:
            articles: Article对象列表
            output_dir: 输出目录
        """
        import json
        from pathlib import Path
        
        if output_dir is None:
            output_dir = Config.RAW_DATA_DIR / self.source_name
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"articles_{timestamp}.json"
        
        data = [article.to_dict() for article in articles]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.success(f"文章已保存到: {output_file}")
