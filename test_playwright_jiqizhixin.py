"""测试机器之心 - 使用Playwright"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.crawlers.jiqizhixin import JiqizhixinCrawler
from src.utils.logger import logger

def main():
    logger.info("="*60)
    logger.info("使用Playwright测试机器之心爬虫")
    logger.info("="*60)
    
    crawler = JiqizhixinCrawler()
    
    try:
        logger.info("\n开始爬取文章...")
        articles = crawler.crawl_latest(max_articles=3)
        
        if articles:
            logger.success(f"\n✅ 成功爬取 {len(articles)} 篇文章\n")
            
            for i, article in enumerate(articles, 1):
                logger.info(f"{'='*60}")
                logger.info(f"文章 [{i}]")
                logger.info(f"{'='*60}")
                logger.info(f"标题: {article.title}")
                logger.info(f"URL: {article.url}")
                logger.info(f"作者: {article.author or '未知'}")
                logger.info(f"时间: {article.publish_time or '未知'}")
                logger.info(f"内容长度: {len(article.content)} 字符")
                logger.info(f"标签: {', '.join(article.tags)}")
                
                if article.content:
                    preview = article.content[:200].replace('\n', ' ')
                    logger.info(f"内容预览: {preview}...")
                logger.info("")
            
            # 保存文章
            crawler.save_articles(articles)
            logger.success(f"✅ 文章已保存")
            
        else:
            logger.warning("⚠️ 未爬取到文章")
            
    except KeyboardInterrupt:
        logger.warning("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 爬取失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()
