"""使用RSS订阅源获取AI资讯"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import feedparser
import requests
from datetime import datetime
from src.models.article import Article
from src.utils.logger import logger
import json

# 常见的AI资讯RSS源
RSS_SOURCES = {
    "机器之心RSS": "https://www.jiqizhixin.com/rss",
    "量子位RSS": "https://www.qbitai.com/feed",
    "AI科技评论RSS": "https://www.leiphone.com/category/ai/feed",
    "36氪AI": "https://36kr.com/feed/ai",
}

def fetch_rss(name, url, max_articles=10):
    """获取RSS订阅"""
    logger.info(f"正在获取 {name}: {url}")
    
    try:
        # 使用requests获取，避免feedparser的网络问题
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"{name} 返回状态码: {response.status_code}")
            return []
        
        # 解析RSS
        feed = feedparser.parse(response.content)
        logger.success(f"✅ {name} - 找到 {len(feed.entries)} 条资讯")
        
        articles = []
        for entry in feed.entries[:max_articles]:
            try:
                article = Article(
                    id=entry.get('id', entry.link),
                    title=entry.get('title', ''),
                    url=entry.get('link', ''),
                    source=name,
                    author=entry.get('author', ''),
                    publish_time=datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') else None,
                    content=entry.get('summary', entry.get('description', '')),
                    summary=entry.get('summary', '')[:200],
                    tags=[tag.term for tag in entry.get('tags', [])],
                    images=[]
                )
                articles.append(article)
                logger.info(f"  - {article.title}")
            except Exception as e:
                logger.error(f"解析条目失败: {e}")
                continue
        
        return articles
        
    except requests.Timeout:
        logger.warning(f"❌ {name} 超时")
    except Exception as e:
        logger.error(f"❌ {name} 错误: {e}")
    
    return []

def main():
    """主函数"""
    all_articles = []
    
    for name, url in RSS_SOURCES.items():
        articles = fetch_rss(name, url, max_articles=5)
        all_articles.extend(articles)
    
    if all_articles:
        logger.success(f"\n📊 总共获取 {len(all_articles)} 篇文章")
        
        # 保存到JSON
        output_dir = Path("data/raw/rss")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"articles_{timestamp}.json"
        
        data = [article.to_dict() for article in all_articles]
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.success(f"💾 已保存到: {output_file}")
    else:
        logger.warning("未获取到任何文章")

if __name__ == "__main__":
    main()
