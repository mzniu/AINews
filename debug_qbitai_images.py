"""调试量子位图片下载问题"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

url = 'https://www.qbitai.com/2026/02/377824.html'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

resp = requests.get(url, headers=headers, timeout=15)
print(f"页面状态: {resp.status_code}")
soup = BeautifulSoup(resp.text, 'lxml')
imgs = soup.find_all('img')
print(f"共找到 {len(imgs)} 张图片\n")

for i, img in enumerate(imgs[:15]):
    src = img.get('src', '')
    data_src = img.get('data-src', '')
    data_original = img.get('data-original', '')
    lazy = img.get('loading', '')
    cls = img.get('class', [])
    
    print(f"[{i+1}]")
    print(f"  src         = {src[:200]}")
    print(f"  data-src    = {data_src[:200]}")
    print(f"  data-original = {data_original[:200]}")
    print(f"  loading={lazy} class={cls}")
    
    # 测试下载
    test_url = src or data_src or data_original
    if test_url:
        full = urljoin(url, test_url)
        try:
            r = requests.get(full, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': url,
                'Accept': 'image/*,*/*'
            }, timeout=10)
            ct = r.headers.get('content-type', '?')
            print(f"  => status={r.status_code} size={len(r.content)} type={ct}")
            if r.status_code == 403:
                print(f"  => 403 Forbidden! 需要更多请求头")
        except Exception as e:
            print(f"  => 下载失败: {e}")
    print()
