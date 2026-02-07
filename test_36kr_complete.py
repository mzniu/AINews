"""完整测试36kr爬虫"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.crawlers.kr36_ai import Kr36AICrawler
from src.utils.logger import logger
import requests

def test_url_access():
    """测试URL可访问性"""
    test_urls = [
        "https://www.36kr.com",
        "https://www.36kr.com/information/AI/",
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    for url in test_urls:
        logger.info(f"测试: {url}")
        try:
            r = requests.get(url, headers=headers, timeout=5)
            logger.success(f"✅ 可访问! 状态码: {r.status_code}, 长度: {len(r.text)}")
            return True
        except requests.Timeout:
            logger.warning(f"❌ 超时: {url}")
        except Exception as e:
            logger.error(f"❌ 错误: {url} - {type(e).__name__}: {str(e)[:50]}")
    
    return False

def test_crawl():
    """测试爬取功能"""
    logger.info("\n" + "="*60)
    logger.info("开始测试36kr AI频道爬虫")
    logger.info("="*60 + "\n")
    
    crawler = Kr36AICrawler()
    
    try:
        # 爬取文章
        logger.info("正在爬取最新文章...")
        articles = crawler.crawl_latest(max_articles=5)
        
        if articles:
            logger.success(f"\n✅ 成功爬取 {len(articles)} 篇文章\n")
            
            for i, article in enumerate(articles, 1):
                logger.info(f"[{i}] {article.title}")
                logger.info(f"    URL: {article.url}")
                logger.info(f"    来源: {article.source}")
                logger.info(f"    作者: {article.author or '未知'}")
                logger.info(f"    时间: {article.publish_time or '未知'}")
                logger.info(f"    内容长度: {len(article.content)} 字符")
                logger.info(f"    标签: {', '.join(article.tags)}")
                logger.info(f"    图片: {len(article.images)} 张")
                if article.content:
                    logger.info(f"    内容预览: {article.content[:100]}...\n")
            
            # 保存文章
            crawler.save_articles(articles)
            logger.success("✅ 文章已保存到data/raw/36kr_ai/")
            
        else:
            logger.warning("⚠️ 未爬取到文章")
            logger.info("可能原因:")
            logger.info("1. 网站结构已变化")
            logger.info("2. 需要JavaScript渲染")
            logger.info("3. 网络连接问题")
            
    except Exception as e:
        logger.error(f"❌ 爬取失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    """主函数"""
    # 先测试连接
    logger.info("第一步: 测试网站连接")
    if test_url_access():
        logger.success("✅ 网站可访问，继续爬取\n")
        test_crawl()
    else:
        logger.error("❌ 无法访问36kr网站")
        logger.info("\n解决方案:")
        logger.info("1. 检查网络连接")
        logger.info("2. 配置代理（如需要）")
        logger.info("3. 使用其他数据源")

if __name__ == "__main__":
    main()
