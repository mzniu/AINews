"""测试机器之心爬虫 - 真实爬取版本"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.crawlers.jiqizhixin import JiqizhixinCrawler
from src.utils.logger import logger
import requests

def test_connection_first():
    """先测试网站连接"""
    test_urls = [
        ("机器之心", "https://www.jiqizhixin.com"),
        ("机器之心(无www)", "https://jiqizhixin.com"),
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    for name, url in test_urls:
        try:
            logger.info(f"测试 {name}: {url}")
            r = requests.get(url, headers=headers, timeout=5)
            logger.success(f"✅ {name} 可访问！状态码: {r.status_code}")
            return True
        except Exception as e:
            logger.warning(f"❌ {name} 不可访问: {e}")
    
    logger.error("所有URL都无法访问，请检查网络或使用代理")
    return False

def test_single_article():
    """测试爬取单篇文章"""
    crawler = JiqizhixinCrawler()
    
    # 测试URL
    test_url = "https://www.jiqizhixin.com/articles/2026-02-05-2"
    
    logger.info("=" * 50)
    logger.info("测试爬取单篇文章")
    logger.info("=" * 50)
    
    article = crawler.crawl_article(test_url)
    
    if article:
        logger.success("爬取成功！")
        logger.info(f"\n标题: {article.title}")
        logger.info(f"作者: {article.author}")
        logger.info(f"发布时间: {article.publish_time}")
        logger.info(f"标签: {', '.join(article.tags)}")
        logger.info(f"图片数量: {len(article.images)}")
        logger.info(f"正文长度: {len(article.content)} 字符")
        logger.info(f"\n正文预览:\n{article.content[:200]}...")
        
        # 保存到文件
        crawler.save_articles([article])
    else:
        logger.error("爬取失败 - 可能需要配置代理或使用Selenium")

def test_list_page():
    """测试爬取列表页"""
    crawler = JiqizhixinCrawler()
    
    logger.info("=" * 50)
    logger.info("测试爬取列表页")
    logger.info("=" * 50)
    
    articles = crawler.crawl_latest(max_articles=5)
    
    logger.success(f"\n总共爬取了 {len(articles)} 篇文章")
    
    for i, article in enumerate(articles, 1):
        logger.info(f"\n[{i}] {article.title}")
        logger.info(f"    URL: {article.url}")
        logger.info(f"    时间: {article.publish_time}")
    
    if articles:
        crawler.save_articles(articles)
    else:
        logger.warning("未爬取到文章 - 可能需要:")
        logger.warning("1. 配置HTTP代理")
        logger.warning("2. 使用Selenium处理JavaScript渲染")
        logger.warning("3. 使用RSS源作为替代方案")

if __name__ == "__main__":
    # 先测试连接
    if test_connection_first():
        print("\n" + "=" * 80 + "\n")
        
        # 测试单篇文章
        test_single_article()
        
        print("\n" + "=" * 80 + "\n")
        
        # 测试列表页
        test_list_page()
    else:
        logger.error("网络连接失败，无法继续测试")
        logger.info("\n解决方案:")
        logger.info("1. 检查网络连接")
        logger.info("2. 配置HTTP/HTTPS代理")
        logger.info("3. 使用VPN")
        logger.info("4. 使用本地代理工具（如Clash、V2Ray等）")
        logger.info("5. 或使用备用爬虫源（见 src/crawlers/baidu_news.py）")

