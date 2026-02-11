#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试36kr网站image-wrapper图片提取功能
注意：36kr的图片结构是 <p class="image-wrapper"><img ...></p>
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.crawler_service import CrawlerService
import asyncio

async def test_36kr_image_extraction():
    """测试36kr图片提取"""
    # 使用一个真实的36kr文章URL进行测试
    test_url = "https://www.36kr.com/p/3678583640810112"  # 可以替换为其他36kr文章URL
    
    print("🔍 测试36kr网站image-wrapper图片提取功能")
    print("=" * 60)
    
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
        image_wrapper_count = 0
        other_count = 0
        
        for img in result['images']:
            if img.get('class') == 'image-wrapper':
                image_wrapper_count += 1
                print(f"🎯 发现image-wrapper图片: {img['url']}")
            else:
                other_count += 1
        
        print(f"\n📈 提取统计:")
        print(f"   image-wrapper容器中的图片: {image_wrapper_count} 张")
        print(f"   其他图片: {other_count} 张")
        print(f"   总计: {len(result['images'])} 张")
        
        # 4. 显示前几张图片URL
        print(f"\n📋 前5张图片URL:")
        for i, img in enumerate(result['images'][:5]):
            source_class = img.get('class', 'unknown')
            container_info = img.get('container', '')
            container_text = f" [{container_info}]" if container_info else ""
            print(f"   {i+1}. [{source_class}]{container_text} {img['url']}")
            
        if len(result['images']) > 5:
            print(f"   ... 还有 {len(result['images']) - 5} 张图片")
            
        # 5. 验证是否只提取了image-wrapper中的图片
        if image_wrapper_count > 0 and other_count == 0:
            print(f"\n✅ 成功！只提取了image-wrapper容器中的图片")
        elif image_wrapper_count > 0 and other_count > 0:
            print(f"\n⚠️  注意：提取到了{image_wrapper_count}张image-wrapper图片和{other_count}张其他图片")
        else:
            print(f"\n❌ 未找到任何image-wrapper图片")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_36kr_image_extraction())