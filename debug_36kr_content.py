#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试36kr页面结构，分析内容提取问题
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.crawler_service import CrawlerService
import asyncio
from bs4 import BeautifulSoup

async def debug_36kr_structure():
    """调试36kr页面结构"""
    test_url = "https://www.36kr.com/p/3678583640810112"
    
    print("🔍 调试36kr页面结构")
    print("=" * 60)
    
    try:
        # 1. 获取页面内容
        print("📥 获取页面HTML...")
        html, title = await CrawlerService.get_page_content(test_url)
        print(f"📄 标题: {title}")
        print(f"📏 HTML长度: {len(html)} 字符")
        
        # 2. 解析HTML
        soup = BeautifulSoup(html, 'lxml')
        
        # 3. 尝试各种可能的内容选择器
        selectors_to_try = [
            'article',
            '[class*="content"]',
            '[class*="article"]', 
            '[class*="post"]',
            '[id*="content"]',
            'main',
            '.main-content',
            '.article-content',
            '.post-content',
            '.content-wrapper',
            '[data-module-name*="article"]',
            '.kr-article-flow',
            '.article-detail',
            '.article-body',
            '.post-body'
        ]
        
        print(f"\n🎯 测试各种内容选择器:")
        for selector in selectors_to_try:
            elements = soup.select(selector)
            if elements:
                content_length = len(elements[0].get_text(strip=True))
                print(f"  ✅ {selector:25} -> {len(elements)}个元素, 内容长度: {content_length}")
                
                # 如果内容足够长，显示部分内容
                if content_length > 100:
                    text_preview = elements[0].get_text(strip=True)[:200]
                    print(f"     预览: {text_preview}...")
            else:
                print(f"  ❌ {selector:25} -> 未找到")
        
        # 4. 查找可能的文章容器
        print(f"\n🔍 查找可能的文章容器:")
        # 查找包含大量文本的div
        all_divs = soup.find_all('div')
        text_divs = []
        for div in all_divs:
            text_content = div.get_text(strip=True)
            if len(text_content) > 500:  # 超过500字符的div
                text_divs.append((div, len(text_content)))
        
        # 按文本长度排序
        text_divs.sort(key=lambda x: x[1], reverse=True)
        
        print(f"找到 {len(text_divs)} 个包含长文本的div:")
        for i, (div, length) in enumerate(text_divs[:5]):
            # 获取div的class和id
            classes = div.get('class', [])
            div_id = div.get('id', '')
            class_str = ' '.join(classes) if classes else '无class'
            
            print(f"  {i+1}. 长度: {length:5} 字符 | class: {class_str} | id: {div_id}")
            
            # 显示前100字符预览
            preview = div.get_text(strip=True)[:100]
            print(f"      预览: {preview}...")
            print()
            
        # 5. 检查是否有iframe或动态加载内容
        iframes = soup.find_all('iframe')
        scripts = soup.find_all('script')
        
        print(f"📊 页面结构分析:")
        print(f"   iframe数量: {len(iframes)}")
        print(f"   script标签数量: {len(scripts)}")
        
        # 查找可能的动态内容加载
        dynamic_scripts = [s for s in scripts if s.get('src') and ('react' in s['src'].lower() or 'vue' in s['src'].lower() or 'app' in s['src'].lower())]
        print(f"   可能的框架脚本: {len(dynamic_scripts)}")
        for script in dynamic_scripts[:3]:
            print(f"     - {script.get('src', '内联脚本')}")
            
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_36kr_structure())