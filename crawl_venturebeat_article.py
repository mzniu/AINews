"""
VentureBeat文章完整爬虫
抓取文章内容、图片和其他元数据
"""
import requests
from bs4 import BeautifulSoup
import json
import time
import os
from urllib.parse import urljoin, urlparse
from pathlib import Path

class VentureBeatArticleCrawler:
    """VentureBeat文章爬虫类"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_article_content(self, url):
        """获取文章完整内容"""
        try:
            print(f"正在抓取: {url}")
            time.sleep(2)  # 避免请求过于频繁
            
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # 提取文章信息
                article_data = {
                    'url': url,
                    'title': self._extract_title(soup),
                    'author': self._extract_author(soup),
                    'publish_date': self._extract_publish_date(soup),
                    'content': self._extract_content(soup),
                    'images': self._extract_images(soup, url),
                    'tags': self._extract_tags(soup),
                    'summary': self._extract_summary(soup)
                }
                
                return article_data
            else:
                print(f"HTTP错误: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"抓取失败: {e}")
            return None
    
    def _extract_title(self, soup):
        """提取标题"""
        # VentureBeat通常使用h1标签
        title_elem = soup.find('h1')
        if title_elem:
            return title_elem.get_text(strip=True)
        return "未找到标题"
    
    def _extract_author(self, soup):
        """提取作者信息"""
        # 尝试多种选择器
        author_selectors = [
            '[class*="author"] a',
            '[rel="author"]',
            '.byline-author',
            '.author-name'
        ]
        
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                return author_elem.get_text(strip=True)
        return "未知作者"
    
    def _extract_publish_date(self, soup):
        """提取发布日期"""
        # 查找time标签或包含日期的元素
        time_elem = soup.find('time')
        if time_elem and time_elem.has_attr('datetime'):
            return time_elem['datetime']
        
        # 查找包含日期文本的元素
        date_selectors = ['.publish-date', '.entry-date', '[class*="date"]']
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                return date_elem.get_text(strip=True)
        return "未知日期"
    
    def _extract_content(self, soup):
        """提取文章正文内容"""
        # VentureBeat的内容通常在特定的div中
        content_selectors = [
            '[class*="content"]',
            'article',
            '.post-content',
            '.entry-content',
            'main'
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 清理不需要的元素
                for unwanted in content_elem.select('script, style, .ad, .advertisement, .related-posts, nav'):
                    unwanted.decompose()
                
                # 获取纯文本内容
                content_text = content_elem.get_text(separator='\n', strip=True)
                return content_text[:2000] + "..." if len(content_text) > 2000 else content_text
        
        return "未找到文章内容"
    
    def _extract_images(self, soup, base_url):
        """提取图片信息"""
        images = []
        
        # 查找所有图片
        img_elements = soup.find_all('img')
        
        for img in img_elements:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                # 处理相对URL
                full_url = urljoin(base_url, src)
                alt_text = img.get('alt', '')
                
                images.append({
                    'url': full_url,
                    'alt': alt_text,
                    'title': img.get('title', '')
                })
        
        return images
    
    def _extract_tags(self, soup):
        """提取标签"""
        tags = []
        tag_selectors = [
            '.tags a',
            '.post-tags a',
            '[rel="tag"]'
        ]
        
        for selector in tag_selectors:
            tag_elements = soup.select(selector)
            for tag in tag_elements:
                tag_text = tag.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)
        
        return tags
    
    def _extract_summary(self, soup):
        """提取文章摘要"""
        # 查找meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            return meta_desc.get('content', '')
        
        # 或者从内容中提取前几句话
        content = self._extract_content(soup)
        sentences = content.split('.')[:3]
        return '.'.join(sentences) + '.' if sentences else ""

def download_images(article_data, output_dir="downloaded_images"):
    """下载文章中的图片"""
    if not article_data or not article_data.get('images'):
        print("没有图片需要下载")
        return []
    
    # 创建输出目录
    images_dir = Path(output_dir) / "venturebeat"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded_images = []
    
    print(f"开始下载 {len(article_data['images'])} 张图片...")
    
    for i, img_info in enumerate(article_data['images']):
        try:
            img_url = img_info['url']
            print(f"下载图片 {i+1}/{len(article_data['images'])}: {img_url}")
            
            # 发送请求下载图片
            response = requests.get(img_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }, timeout=30)
            
            if response.status_code == 200:
                # 生成文件名
                parsed_url = urlparse(img_url)
                filename = f"image_{i+1:03d}_{os.path.basename(parsed_url.path)}"
                if not filename.endswith(('.jpg', '.png', '.gif', '.webp')):
                    filename += '.jpg'
                
                filepath = images_dir / filename
                
                # 保存图片
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                downloaded_images.append(str(filepath))
                print(f"  ✓ 已保存: {filepath}")
            else:
                print(f"  ✗ 下载失败，状态码: {response.status_code}")
                
            time.sleep(1)  # 避免请求过于频繁
            
        except Exception as e:
            print(f"  ✗ 下载异常: {e}")
            continue
    
    return downloaded_images

def main():
    """主函数"""
    url = "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    
    print("🚀 开始抓取VentureBeat文章")
    print("=" * 50)
    
    # 创建爬虫实例
    crawler = VentureBeatArticleCrawler()
    
    # 抓取文章
    article_data = crawler.get_article_content(url)
    
    if article_data:
        print("✅ 文章抓取成功!")
        print(f"标题: {article_data['title']}")
        print(f"作者: {article_data['author']}")
        print(f"发布日期: {article_data['publish_date']}")
        print(f"内容长度: {len(article_data['content'])} 字符")
        print(f"图片数量: {len(article_data['images'])}")
        print(f"标签: {', '.join(article_data['tags'])}")
        print(f"摘要: {article_data['summary'][:100]}...")
        
        # 保存文章数据
        with open('venturebeat_article_full.json', 'w', encoding='utf-8') as f:
            json.dump(article_data, f, ensure_ascii=False, indent=2, default=str)
        print("📝 文章数据已保存到 venturebeat_article_full.json")
        
        # 下载图片
        downloaded_images = download_images(article_data)
        print(f"🖼️  成功下载 {len(downloaded_images)} 张图片")
        
        # 更新文章数据中的下载图片路径
        article_data['downloaded_images'] = downloaded_images
        
        # 保存更新后的数据
        with open('venturebeat_article_with_images.json', 'w', encoding='utf-8') as f:
            json.dump(article_data, f, ensure_ascii=False, indent=2, default=str)
        print("💾 完整数据已保存到 venturebeat_article_with_images.json")
        
    else:
        print("❌ 文章抓取失败")

if __name__ == "__main__":
    main()