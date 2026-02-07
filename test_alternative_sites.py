"""测试其他AI资讯网站"""
import requests
import time

websites = [
    ("36氪AI", "https://www.36kr.com/search/articles/AI"),
    ("InfoQ AI", "https://www.infoq.cn/topic/ai"),
    ("CSDN AI", "https://blog.csdn.net/nav/ai"),
    ("知乎AI话题", "https://www.zhihu.com/topic/19551626/hot"),
    ("机器之心镜像", "https://jiqizhixin.com/"),  # 尝试不带www
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

for name, url in websites:
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        start = time.time()
        r = requests.get(url, headers=headers, timeout=5)
        elapsed = time.time() - start
        
        print(f"✅ 成功!")
        print(f"  状态码: {r.status_code}")
        print(f"  耗时: {elapsed:.2f}秒")
        print(f"  内容长度: {len(r.text)} 字符")
        
        # 如果成功，显示标题
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, 'lxml')
        if soup.title:
            print(f"  标题: {soup.title.string}")
        
    except requests.Timeout:
        print("❌ 超时（5秒）")
    except requests.ConnectionError:
        print("❌ 连接错误")
    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {str(e)[:100]}")
    
    time.sleep(1)  # 避免请求过快
