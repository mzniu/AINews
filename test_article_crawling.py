"""
简单测试脚本 - 验证文章爬虫功能
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入必要的模块
try:
    from src.crawlers.universal_article_crawler import ArticleCrawlerManager
    print("✅ 成功导入爬虫模块")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    # 使用本地版本
    exec(open('crawl_venturebeat_article.py').read())
    exit()

def test_article_crawling():
    """测试文章爬取功能"""
    print("🚀 开始测试文章爬虫")
    print("=" * 50)
    
    # 测试URL
    test_url = "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    
    # 创建爬虫管理器
    manager = ArticleCrawlerManager()
    
    # 抓取文章
    print(f"正在抓取: {test_url}")
    article_data = manager.crawl_article(test_url)
    
    if article_data:
        print("✅ 文章抓取成功!")
        print(f"标题: {article_data.title}")
        print(f"作者: {article_data.author}")
        print(f"发布日期: {article_data.publish_date}")
        print(f"内容长度: {len(article_data.content)} 字符")
        print(f"图片数量: {len(article_data.images)}")
        print(f"标签: {', '.join(article_data.tags) if article_data.tags else '无标签'}")
        print(f"摘要: {article_data.summary[:100]}...")
        
        # 显示前几张图片信息
        if article_data.images:
            print("\n🖼️  图片信息:")
            for i, img in enumerate(article_data.images[:3]):
                print(f"  图片{i+1}: {img['alt']} -> {img['url'][:80]}...")
        
        # 下载图片
        print("\n📥 开始下载图片...")
        downloaded_images = manager.download_images(article_data)
        print(f"成功下载 {len(downloaded_images)} 张图片")
        
        # 保存结果
        import json
        result_data = {
            'title': article_data.title,
            'author': article_data.author,
            'content_preview': article_data.content[:500] + "...",
            'image_count': len(article_data.images),
            'downloaded_images': downloaded_images,
            'tags': article_data.tags
        }
        
        with open('article_crawling_test_result.json', 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        print("💾 测试结果已保存到 article_crawling_test_result.json")
        
    else:
        print("❌ 文章抓取失败")

def test_multiple_sources():
    """测试多个来源"""
    print("\n🌐 测试多源爬取")
    print("=" * 50)
    
    test_urls = [
        "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero",
        # 可以添加其他测试URL
    ]
    
    manager = ArticleCrawlerManager()
    successful_crawls = 0
    
    for url in test_urls:
        print(f"\n处理: {url}")
        article_data = manager.crawl_article(url)
        if article_data:
            successful_crawls += 1
            print(f"✅ 成功抓取: {article_data.title}")
        else:
            print("❌ 抓取失败")
    
    print(f"\n📊 测试总结: {successful_crawls}/{len(test_urls)} 成功")

if __name__ == "__main__":
    test_article_crawling()
    test_multiple_sources()