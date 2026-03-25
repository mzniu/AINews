#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 51CTO 网站抓取
"""

from playwright.sync_api import sync_playwright
import json
from bs4 import BeautifulSoup

url = "https://www.51cto.com/aigc/10718.html"

with sync_playwright() as p:
    # 启动浏览器
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # 访问页面
    print(f"正在访问：{url}")
    response = page.goto(url, wait_until='networkidle', timeout=30000)
    
    print(f"响应状态码：{response.status}")
    
    # 等待内容加载
    page.wait_for_timeout(3000)
    
    # 获取完整 HTML
    html = page.content()
    soup = BeautifulSoup(html, 'lxml')
    
    # 检查页面标题
    title = soup.find('title')
    print(f"\n📋 页面标题：{title.text if title else '无'}")
    
    # 尝试不同的选择器
    selectors_to_try = [
        '.article-content',
        '.content',
        'article',
        '[class*="article"]',
        '[id*="article"]',
        '.main',
        '#article',
        '.detail-content',
        '[class*="content"]'
    ]
    
    print("\n🔍 尝试不同选择器:")
    for selector in selectors_to_try:
        elements = soup.select(selector)
        if elements:
            text = elements[0].get_text(strip=True)[:200]
            print(f"✅ {selector}: 找到 {len(elements)} 个元素，文本前 200 字：{text}...")
        else:
            print(f"❌ {selector}: 未找到元素")
    
    # 查找所有包含"文章"或"内容"的 class
    print("\n🔍 查找可能的内容容器:")
    all_divs = soup.find_all(['div', 'article', 'section'])
    potential_containers = []
    
    for div in all_divs:
        classes = div.get('class', [])
        div_id = div.get('id', '')
        
        # 检查 class 或 id 是否包含相关关键词
        class_str = ' '.join(classes) if classes else ''
        keywords = ['article', 'content', 'detail', 'main', 'body']
        
        for keyword in keywords:
            if keyword in class_str.lower() or keyword in div_id.lower():
                text = div.get_text(strip=True)
                if len(text) > 500:  # 只关心内容较多的容器
                    potential_containers.append({
                        'tag': div.name,
                        'class': classes,
                        'id': div_id,
                        'text_length': len(text),
                        'text_preview': text[:200]
                    })
                    break
    
    print(f"\n找到 {len(potential_containers)} 个潜在内容容器:")
    for i, container in enumerate(potential_containers[:5], 1):
        print(f"\n{i}. 标签：{container['tag']}")
        print(f"   Class: {container['class']}")
        print(f"   ID: {container['id']}")
        print(f"   文本长度：{container['text_length']}")
        print(f"   预览：{container['text_preview']}...")
    
    # 保存完整 HTML 以便分析
    with open('51cto_debug.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n💾 完整 HTML 已保存到：51cto_debug.html")
    
    # 检查是否有反爬机制
    print("\n🔍 检查反爬机制:")
    if 'robot' in html.lower() or 'captcha' in html.lower():
        print("⚠️ 可能触发了反爬机制（检测到 robot/captcha 相关字样）")
    else:
        print("✅ 未明显触发反爬机制")
    
    browser.close()

print("\n分析完成！")
