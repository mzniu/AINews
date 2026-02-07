"""运行爬虫的主脚本"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from src.utils.logger import logger
from src.crawlers.jiqizhixin import JiqizhixinCrawler


@click.command()
@click.option('--source', default='jiqizhixin', help='爬虫源名称')
@click.option('--max-articles', default=10, help='最大爬取文章数')
@click.option('--test-url', default=None, help='测试单个URL')
def main(source: str, max_articles: int, test_url: str):
    """运行爬虫"""
    logger.info(f"开始运行爬虫: {source}")
    
    if source == 'jiqizhixin':
        crawler = JiqizhixinCrawler()
        
        if test_url:
            # 测试单个URL
            logger.info(f"测试单个URL: {test_url}")
            article = crawler.crawl_article(test_url)
            if article:
                logger.success(f"成功: {article.title}")
                crawler.save_articles([article])
            else:
                logger.error("爬取失败")
        else:
            # 批量爬取
            articles = crawler.crawl_latest(max_articles=max_articles)
            logger.success(f"共爬取 {len(articles)} 篇文章")
            
            if articles:
                crawler.save_articles(articles)
    else:
        logger.error(f"不支持的爬虫源: {source}")


if __name__ == "__main__":
    main()
