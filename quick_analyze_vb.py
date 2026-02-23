import requests
from bs4 import BeautifulSoup
import json
import time

def quick_analyze():
    url = "https://venturebeat.com/orchestration/new-agent-framework-matches-human-engineered-ai-systems-and-adds-zero"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        print("正在分析VentureBeat页面...")
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=15)
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 快速查找关键元素
            findings = {}
            
            # 标题
            title = soup.find('h1')
            findings['title'] = title.get_text().strip() if title else "未找到"
            
            # 主要内容
            content_divs = soup.find_all(['div', 'article'], class_=lambda x: x and ('content' in x.lower() or 'article' in x.lower()))
            findings['content_sections'] = len(content_divs)
            
            # 图片
            images = soup.find_all('img')
            findings['total_images'] = len(images)
            findings['image_urls'] = [img.get('src', '')[:100] for img in images[:5]]
            
            # 作者信息
            author = soup.find(['a', 'span'], class_=lambda x: x and 'author' in x.lower())
            findings['author'] = author.get_text().strip() if author else "未找到"
            
            print("分析结果:")
            for key, value in findings.items():
                print(f"{key}: {value}")
                
            with open('quick_analysis.json', 'w', encoding='utf-8') as f:
                json.dump(findings, f, ensure_ascii=False, indent=2)
                
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    quick_analyze()