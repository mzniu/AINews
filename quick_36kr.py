"""快速测试36kr连接"""
import requests

url = "https://www.36kr.com/information/AI/"
print(f"测试: {url}")

try:
    r = requests.get(url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
    print(f"✅ 成功! 状态码: {r.status_code}, 长度: {len(r.text)}")
except requests.Timeout:
    print("❌ 超时")
except Exception as e:
    print(f"❌ 错误: {type(e).__name__}")
