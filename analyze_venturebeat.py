import requests
from bs4 import BeautifulSoup
import json
from urllib.parse import urljoin
import time

def analyze_venturebeat_page(url):
    """分析VentureBeat页面结构"""
    
    print("🔍 分析VentureBeat页面结构")
    print("=" * 50)
    print(f"目标URL: {url}")
    
    # 设置请求头避免被反爬
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        # 添加延迟避免触发反爬机制
        time.sleep(2)
        
        print("正在请求页面...")
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ 请求成功! 状态码: {response.status_code}")
            print(f"页面大小: {len(response.content)} 字节")
            
            # 解析HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 分析页面结构
            print("\n📄 页面结构分析:")
            
            # 查找标题
            title_selectors = [
                'h1.article-title',
                'h1.entry-title', 
                'h1.post-title',
                'h1[class*="title"]',
                'title'
            ]
            
            print("标题元素:")
            title_found = False
            for selector in title_selectors:
                elements = soup.select(selector)
                if elements:
                    for elem in elements:
                        print(f"  ✓ {selector}: {elem.get_text(strip=True)[:100]}...")
                        title_found = True
                        break
                if title_found:
                    break
            
            if not title_found:
                print("  ✗ 未找到标题元素")
            
            # 查找作者信息
            print("\n作者信息:")
            author_selectors = [
                '.author-name',
                '.byline-author',
                '[rel="author"]',
                '.post-author a',
                '.entry-author'
            ]
            
            author_found = False
            for selector in author_selectors:
                elements = soup.select(selector)
                if elements:
                    for elem in elements:
                        print(f"  ✓ {selector}: {elem.get_text(strip=True)}")
                        author_found = True
                        break
                if author_found:
                    break
            
            if not author_found:
                print("  ✗ 未找到作者信息")
            
            # 查找发布时间
            print("\n发布时间:")
            date_selectors = [
                'time[datetime]',
                '.published',
                '.post-date',
                '.entry-date',
                '[class*="date"]'
            ]
            
            date_found = False
            for selector in date_selectors:
                elements = soup.select(selector)
                if elements:
                    for elem in elements:
                        date_text = elem.get('datetime') or elem.get_text(strip=True)
                        print(f"  ✓ {selector}: {date_text}")
                        date_found = True
                        break
                if date_found:
                    break
            
            if not date_found:
                print("  ✗ 未找到发布时间")
            
            # 查找主要内容区域
            print("\n主要内容区域:")
            content_selectors = [
                '.article-content',
                '.post-content',
                '.entry-content',
                '.content',
                '[class*="content"] article',
                'main article'
            ]
            
            content_found = False
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    content_length = len(elements[0].get_text())
                    print(f"  ✓ {selector}: {content_length} 字符")
                    content_found = True
                    # 显示部分内容预览
                    content_preview = elements[0].get_text()[:200].replace('\n', ' ')
                    print(f"    预览: {content_preview}...")
                    break
            
            if not content_found:
                print("  ✗ 未找到主要内容区域")
            
            # 查找图片
            print("\n图片资源:")
            img_selectors = [
                '.article-content img',
                '.post-content img',
                '.entry-content img',
                'article img',
                'main img'
            ]
            
            images = []
            for selector in img_selectors:
                img_elements = soup.select(selector)
                if img_elements:
                    print(f"  ✓ {selector}: 找到 {len(img_elements)} 张图片")
                    for i, img in enumerate(img_elements[:3]):  # 只显示前3张
                        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                        if src:
                            full_url = urljoin(url, src)
                            alt = img.get('alt', '无alt文本')
                            images.append({'url': full_url, 'alt': alt})
                            print(f"    图片{i+1}: {alt[:50]}... -> {full_url}")
                    break
            
            if not images:
                print("  ✗ 未找到图片")
            
            # 查找标签
            print("\n标签信息:")
            tag_selectors = [
                '.tags a',
                '.post-tags a',
                '.entry-tags a',
                '[rel="tag"]'
            ]
            
            tags = []
            for selector in tag_selectors:
                tag_elements = soup.select(selector)
                if tag_elements:
                    print(f"  ✓ {selector}: 找到 {len(tag_elements)} 个标签")
                    for tag in tag_elements[:5]:
                        tag_text = tag.get_text(strip=True)
                        tags.append(tag_text)
                        print(f"    标签: {tag_text}")
                    break
            
            if not tags:
                print("  ✗ 未找到标签")
            
            # 生成分析报告
            analysis_result = {
                'url': url,
                'title_found': title_found,
                'author_found': author_found,
                'date_found': date_found,
                'content_found': content_found,
                'images_found': len(images),
                'tags_found': len(tags),
                'images': images[:10],  # 限制保存的图片数量
                'tags': tags
            }
            
            # 保存分析结果
            with open('venturebeat_analysis.json', 'w', encoding='utf-8') as f:
                json.dump(analysis_result, f, ensure_ascii=False, indent=2)
            
            print(f"\n📊 分析完成! 结果已保存到 venturebeat_analysis.json")
            
            return analysis_result
            
        else:
            print(f"❌ 请求失败! 状态码: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ 分析过程中出现错误: {e}")
        return None

def main():
    url = "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    result = analyze_venturebeat_page(url)
    
    if result:
        print("\n🎯 分析总结:")
        print(f"  标题提取: {'✓' if result['title_found'] else '✗'}")
        print(f"  作者提取: {'✓' if result['author_found'] else '✗'}")
        print(f"  时间提取: {'✓' if result['date_found'] else '✗'}")
        print(f"  内容提取: {'✓' if result['content_found'] else '✗'}")
        print(f"  图片数量: {result['images_found']}")
        print(f"  标签数量: {result['tags_found']}")

if __name__ == "__main__":
    main()