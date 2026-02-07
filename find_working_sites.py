"""查找可用的AI资讯源"""
import requests
from bs4 import BeautifulSoup

test_sites = [
    ("IT之家AI", "https://www.ithome.com/blog/ai"),
    ("InfoQ AI", "https://www.infoq.cn/topic/ai"),
    ("CSDN AI", "https://blog.csdn.net/nav/ai"),
    ("51CTO AI", "https://www.51cto.com/ai/"),
    ("雷锋网", "https://www.leiphone.com/category/ai"),
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

for name, url in test_sites:
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"URL: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=5)
        print(f"✅ 状态码: {r.status_code}")
        
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            print(f"标题: {soup.title.string if soup.title else '无'}")
            
            # 查找链接
            links = soup.find_all('a', href=True)
            print(f"链接数: {len(links)}")
            
            # 显示前5个链接文本
            for i, link in enumerate(links[:5], 1):
                text = link.get_text(strip=True)[:50]
                href = link['href'][:60]
                print(f"  [{i}] {text} -> {href}")
            
    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {str(e)[:50]}")
