"""检查机器之心页面结构"""
import requests
from bs4 import BeautifulSoup

# 测试列表页
print("=" * 60)
print("测试列表页")
print("=" * 60)
response = requests.get("https://www.jiqizhixin.com/articles")
soup = BeautifulSoup(response.text, 'lxml')

print(f"\nStatus Code: {response.status_code}")
print(f"Content-Length: {len(response.text)}")
print(f"\n页面标题: {soup.title.string if soup.title else 'None'}")

# 查找所有可能的链接
all_links = soup.find_all('a', href=True)
print(f"\n总链接数: {len(all_links)}")

# 查找包含articles的链接
article_links = [a['href'] for a in all_links if 'articles' in str(a.get('href', ''))]
print(f"包含'articles'的链接数: {len(article_links)}")
if article_links:
    print("前5个链接:")
    for link in article_links[:5]:
        print(f"  - {link}")

# 检查是否有JavaScript渲染的迹象
scripts = soup.find_all('script')
print(f"\nScript标签数: {len(scripts)}")

# 查找常见的列表容器
containers = soup.find_all(['div', 'ul', 'article'], class_=True)
print(f"\n带class的容器数: {len(containers)}")

# 打印body的前500个字符
if soup.body:
    print(f"\nBody内容预览 (前500字符):")
    print(soup.body.get_text()[:500])

print("\n" + "=" * 60)
print("测试文章详情页")
print("=" * 60)

# 尝试访问一个可能存在的文章
detail_urls = [
    "https://www.jiqizhixin.com/articles/2026-02-05-2",
    "https://www.jiqizhixin.com/articles/2026-02-04",
]

for url in detail_urls:
    print(f"\n尝试访问: {url}")
    try:
        r = requests.get(url, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            print(f"标题: {soup.title.string if soup.title else 'None'}")
            # 查找h1
            h1_tags = soup.find_all('h1')
            if h1_tags:
                print(f"H1标签: {h1_tags[0].get_text(strip=True)[:50]}...")
    except Exception as e:
        print(f"错误: {e}")
