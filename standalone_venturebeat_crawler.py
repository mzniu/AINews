"""
独立的VentureBeat文章爬虫测试
无需依赖项目其他模块
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import os
from urllib.parse import urljoin, urlparse
from pathlib import Path

def crawl_venturebeat_article(url):
    """抓取VentureBeat文章"""
    
    print(f"🚀 开始抓取VentureBeat文章: {url}")
    print("=" * 60)
    
    # 请求头设置
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        # 发送请求
        print("正在发送请求...")
        time.sleep(2)
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print("✅ 请求成功!")
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 提取文章信息
            article_data = {
                'url': url,
                'title': extract_title(soup),
                'author': extract_author(soup),
                'publish_date': extract_publish_date(soup),
                'content': extract_content(soup),
                'images': extract_images(soup, url),
                'tags': extract_tags(soup),
                'summary': extract_summary(soup)
            }
            
            # 显示结果
            print("\n📋 文章信息:")
            print(f"标题: {article_data['title']}")
            print(f"作者: {article_data['author']}")
            print(f"发布日期: {article_data['publish_date']}")
            print(f"内容长度: {len(article_data['content'])} 字符")
            print(f"图片数量: {len(article_data['images'])}")
            print(f"标签: {', '.join(article_data['tags']) if article_data['tags'] else '无标签'}")
            print(f"摘要: {article_data['summary'][:150]}...")
            
            # 显示图片信息
            if article_data['images']:
                print("\n🖼️  图片列表:")
                for i, img in enumerate(article_data['images'][:5]):
                    print(f"  {i+1}. {img['alt'][:50]} -> {img['url'][:80]}...")
            
            # 保存原始数据
            with open('venturebeat_article_raw.json', 'w', encoding='utf-8') as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n💾 原始数据已保存到 venturebeat_article_raw.json")
            
            # 下载图片
            downloaded_images = download_article_images(article_data)
            article_data['downloaded_images'] = downloaded_images
            
            # 保存完整数据
            with open('venturebeat_article_complete.json', 'w', encoding='utf-8') as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2, default=str)
            print(f"💾 完整数据已保存到 venturebeat_article_complete.json")
            
            return article_data
            
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ 抓取失败: {e}")
        return None

def extract_title(soup):
    """提取标题"""
    title_elem = soup.find('h1')
    return title_elem.get_text(strip=True) if title_elem else "未找到标题"

def extract_author(soup):
    """提取作者"""
    author_selectors = ['[class*="author"] a', '[rel="author"]', '.byline-author']
    for selector in author_selectors:
        author_elem = soup.select_one(selector)
        if author_elem:
            return author_elem.get_text(strip=True)
    return "未知作者"

def extract_publish_date(soup):
    """提取发布日期"""
    time_elem = soup.find('time')
    if time_elem and time_elem.has_attr('datetime'):
        return time_elem['datetime']
    return "未知日期"

def extract_content(soup):
    """提取文章内容"""
    content_selectors = ['[class*="content"]', 'article', '.post-content']
    for selector in content_selectors:
        content_elem = soup.select_one(selector)
        if content_elem:
            # 清理不需要的元素
            for unwanted in content_elem.select('script, style, .ad, .advertisement, .related-posts, nav'):
                unwanted.decompose()
            content_text = content_elem.get_text(separator='\n', strip=True)
            return content_text[:3000] + "..." if len(content_text) > 3000 else content_text
    return "未找到文章内容"

def extract_images(soup, base_url):
    """提取图片信息"""
    images = []
    img_elements = soup.find_all('img')
    
    for img in img_elements:
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if src:
            full_url = urljoin(base_url, src)
            alt_text = img.get('alt', '')
            images.append({
                'url': full_url,
                'alt': alt_text,
                'title': img.get('title', '')
            })
    return images

def extract_tags(soup):
    """提取标签"""
    tags = []
    tag_selectors = ['.tags a', '.post-tags a', '[rel="tag"]']
    
    for selector in tag_selectors:
        tag_elements = soup.select(selector)
        for tag in tag_elements:
            tag_text = tag.get_text(strip=True)
            if tag_text and tag_text not in tags:
                tags.append(tag_text)
    return tags

def extract_summary(soup):
    """提取摘要"""
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        return meta_desc.get('content', '')
    return ""

def download_article_images(article_data, output_dir="downloaded_images"):
    """下载文章图片"""
    if not article_data or not article_data.get('images'):
        print("没有图片需要下载")
        return []
    
    # 创建输出目录
    images_dir = Path(output_dir) / "venturebeat_final"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_images = []
    
    print(f"\n📥 开始下载图片 ({len(article_data['images'])} 张)...")
    
    for i, img_info in enumerate(article_data['images']):
        try:
            img_url = img_info['url']
            print(f"下载图片 {i+1}/{len(article_data['images'])}: {img_info['alt'][:30]}...")
            
            # 发送请求下载图片
            response = requests.get(img_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=30)
            
            if response.status_code == 200:
                # 生成文件名
                parsed_url = urlparse(img_url)
                filename = f"article_image_{i+1:03d}_{os.path.basename(parsed_url.path)}"
                if not any(filename.endswith(ext) for ext in ['.jpg', '.png', '.gif', '.webp', '.jpeg']):
                    filename += '.jpg'
                
                filepath = images_dir / filename
                
                # 保存图片
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                downloaded_images.append(str(filepath))
                file_size = filepath.stat().st_size / 1024  # KB
                print(f"  ✓ 已保存 ({file_size:.1f} KB): {filepath.name}")
            else:
                print(f"  ✗ 下载失败，状态码: {response.status_code}")
                
            time.sleep(1)  # 避免请求过于频繁
            
        except Exception as e:
            print(f"  ✗ 下载异常: {e}")
            continue
    
    return downloaded_images

def main():
    """主函数"""
    # VentureBeat文章URL
    url = "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    
    # 执行爬取
    article_data = crawl_venturebeat_article(url)
    
    if article_data:
        print("\n🎉 文章抓取完成!")
        print(f"✅ 标题: {article_data['title']}")
        print(f"✅ 作者: {article_data['author']}")
        print(f"✅ 内容: {len(article_data['content'])} 字符")
        print(f"✅ 图片: {len(article_data['images'])} 张")
        print(f"✅ 下载图片: {len(article_data.get('downloaded_images', []))} 张")
    else:
        print("\n❌ 文章抓取失败!")

if __name__ == "__main__":
    main()