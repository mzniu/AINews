"""测试真实爬取 - 使用可访问的网站"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.crawlers.kr36_ai import Kr36AICrawler
from src.utils.logger import logger
import requests

def test_connection():
    """测试网站连接"""
    url = "https://www.36kr.com"
    logger.info(f"测试连接: {url}")
    
    try:
        response = requests.get(url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logger.success(f"✅ 连接成功! 状态码: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"❌ 连接失败: {e}")
        return False

def test_crawl():
    """测试爬取"""
    if not test_connection():
        logger.error("无法连接到网站，终止测试")
        return
    
    logger.info("\n" + "=" * 60)
    logger.info("开始爬取36氪AI频道")
    logger.info("=" * 60)
    
    crawler = Kr36AICrawler()
    
    try:
        articles = crawler.crawl_latest(max_articles=3)
        
        logger.success(f"\n✅ 成功爬取 {len(articles)} 篇文章")
        
        for i, article in enumerate(articles, 1):
            logger.info(f"\n[{i}] {article.title}")
            logger.info(f"    URL: {article.url}")
            logger.info(f"    作者: {article.author}")
            logger.info(f"    时间: {article.publish_time}")
            logger.info(f"    内容长度: {len(article.content)} 字符")
            logger.info(f"    标签: {', '.join(article.tags)}")
        
        if articles:
            crawler.save_articles(articles)
            logger.success(f"\n💾 文章已保存")
        
    except Exception as e:
        logger.error(f"❌ 爬取失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_crawl()
