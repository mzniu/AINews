"""检查机器之心网站结构"""
import requests
from bs4 import BeautifulSoup
import json

def check_homepage():
    """检查首页"""
    print("=" * 60)
    print("检查机器之心首页")
    print("=" * 60)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        r = requests.get('https://www.jiqizhixin.com/', headers=headers, timeout=15)
        print(f"✅ 状态码: {r.status_code}")
        print(f"📄 内容长度: {len(r.text)} 字符")
        
        soup = BeautifulSoup(r.text, 'lxml')
        title = soup.title.string if soup.title else "无标题"
        print(f"📌 页面标题: {title}")
        
        # 查找文章链接
        links = soup.find_all('a', href=True)
        article_links = [l['href'] for l in links if '/articles/' in str(l.get('href', ''))]
        
        print(f"\n🔗 找到 {len(article_links)} 个文章链接")
        
        # 去重并显示前10个
        unique_links = list(set(article_links))[:10]
        for i, link in enumerate(unique_links, 1):
            if not link.startswith('http'):
                link = 'https://www.jiqizhixin.com' + link
            print(f"  [{i}] {link}")
        
        return unique_links
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        return []

def check_article_page(url):
    """检查文章页面"""
    print("\n" + "=" * 60)
    print(f"检查文章页: {url}")
    print("=" * 60)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    if not url.startswith('http'):
        url = 'https://www.jiqizhixin.com' + url
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print(f"✅ 状态码: {r.status_code}")
        
        soup = BeautifulSoup(r.text, 'lxml')
        
        # 尝试多种选择器查找标题
        title = None
        title_selectors = [
            ('h1', {'class': 'article-title'}),
            ('h1', {}),
            ('div', {'class': 'title'}),
            ('meta', {'property': 'og:title'}),
        ]
        
        for tag, attrs in title_selectors:
            elem = soup.find(tag, attrs)
            if elem:
                if tag == 'meta':
                    title = elem.get('content')
                else:
                    title = elem.get_text(strip=True)
                if title:
                    print(f"📌 标题: {title}")
                    break
        
        # 查找内容区域
        content_selectors = [
            ('div', {'class': 'article-content'}),
            ('article', {}),
            ('div', {'class': 'content'}),
            ('div', {'class': 'post-content'}),
        ]
        
        for tag, attrs in content_selectors:
            elem = soup.find(tag, attrs)
            if elem:
                content = elem.get_text(strip=True)
                print(f"📝 正文长度: {len(content)} 字符")
                print(f"📝 正文预览: {content[:100]}...")
                break
        
        # 查找所有class包含article或content的div
        print("\n🔍 页面中的主要容器:")
        for div in soup.find_all('div', class_=True)[:20]:
            classes = ' '.join(div.get('class', []))
            if any(keyword in classes.lower() for keyword in ['article', 'content', 'post', 'main']):
                print(f"  - div.{classes}")
        
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    # 检查首页
    links = check_homepage()
    
    # 检查第一篇文章
    if links:
        check_article_page(links[0])
