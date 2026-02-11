#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试pgc-img类图片提取功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.crawler_service import CrawlerService
import asyncio

async def test_pgc_img_extraction():
    """测试pgc-img图片提取"""
    # 测试URL（使用一个包含pgc-img的qbitai文章）
    test_url = "https://www.qbitai.com/2026/02/123456.html"  # 替换为实际URL
    
    print("🔍 测试pgc-img图片提取功能")
    print("=" * 50)
    
    try:
        # 1. 获取页面内容
        print("📥 正在获取页面内容...")
        html, title = await CrawlerService.get_page_content(test_url)
        print(f"📄 页面标题: {title}")
        
        # 2. 提取内容和图片
        print("\n🖼️  正在提取图片...")
        result = CrawlerService.extract_content(html, test_url)
        
        print(f"📝 内容长度: {len(result['content'])} 字符")
        print(f"📊 总图片数量: {len(result['images'])} 张")
        
        # 3. 分类统计
        syl_count = 0
        pgc_count = 0
        
        for img in result['images']:
            if img.get('class') == 'syl-page-img':
                syl_count += 1
            elif img.get('class') == 'pgc-img':
                pgc_count += 1
                print(f"🎯 发现pgc-img图片: {img['url']}")
        
        print(f"\n📈 提取统计:")
        print(f"   syl-page-img: {syl_count} 张")
        print(f"   pgc-img: {pgc_count} 张")
        print(f"   总计: {len(result['images'])} 张")
        
        # 4. 显示前几张图片URL
        print(f"\n📋 前5张图片URL:")
        for i, img in enumerate(result['images'][:5]):
            source_class = img.get('class', 'unknown')
            print(f"   {i+1}. [{source_class}] {img['url']}")
            
        if len(result['images']) > 5:
            print(f"   ... 还有 {len(result['images']) - 5} 张图片")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_pgc_img_extraction())