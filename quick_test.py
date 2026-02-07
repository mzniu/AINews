"""快速测试网站连接"""
import requests
import time

url = "https://www.jiqizhixin.com/"
print(f"测试访问: {url}")
print("超时时间: 5秒")

try:
    start = time.time()
    r = requests.get(url, timeout=5, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    elapsed = time.time() - start
    print(f"✅ 成功! 状态码: {r.status_code}, 耗时: {elapsed:.2f}秒")
    print(f"内容长度: {len(r.text)} 字符")
except requests.Timeout:
    print("❌ 超时")
except requests.ConnectionError:
    print("❌ 连接错误")
except Exception as e:
    print(f"❌ 其他错误: {e}")
