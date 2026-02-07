"""测试36kr AI频道"""
import requests
from bs4 import BeautifulSoup

url = "https://www.36kr.com/information/AI/"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

print(f"测试访问: {url}")

try:
    r = requests.get(url, headers=headers, timeout=10)
    print(f"✅ 状态码: {r.status_code}")
    print(f"内容长度: {len(r.text)} 字符")
    
    soup = BeautifulSoup(r.text, 'lxml')
    print(f"标题: {soup.title.string if soup.title else '无'}")
    
    # 查找文章链接
    links = soup.find_all('a', href=True)
    print(f"\n总链接数: {len(links)}")
    
    # 查找包含 /p/ 的文章链接
    article_links = []
    for link in links:
        href = link.get('href', '')
        if '/p/' in href or '/newsflashes/' in href:
            if href.startswith('/'):
                href = 'https://www.36kr.com' + href
            if href not in article_links:
                article_links.append(href)
    
    print(f"文章链接数: {len(article_links)}")
    print("\n前10个文章链接:")
    for i, link in enumerate(article_links[:10], 1):
        print(f"  [{i}] {link}")
    
    # 显示一些链接的标题
    print("\n前5个链接的标题:")
    for link_elem in links[:20]:
        text = link_elem.get_text(strip=True)
        href = link_elem.get('href', '')
        if text and len(text) > 10 and ('/p/' in href or '/newsflashes/' in href):
            print(f"  - {text[:60]}")

except Exception as e:
    print(f"❌ 错误: {e}")
