import requests
import json

def test_venturebeat_api():
    url = "http://localhost:8080/api/fetch-venturebeat"
    payload = {
        "url": "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    }
    
    try:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60
        )
        
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ API调用成功!")
            print(f"标题: {data.get('data', {}).get('title', 'N/A')}")
            print(f"作者: {data.get('data', {}).get('author', 'N/A')}")
            print(f"图片数量: {data.get('data', {}).get('images_count', 0)}")
        else:
            print("❌ API调用失败")
            
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    test_venturebeat_api()