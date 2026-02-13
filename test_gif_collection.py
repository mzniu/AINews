#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试GIF图片采集功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.crawler_service import CrawlerService
import asyncio

async def test_gif_collection():
    """测试GIF图片采集功能"""
    # 测试URL（选择一个可能包含GIF的网站）
    test_urls = [
        "https://www.36kr.com/",  # 36氪首页
        "https://www.qbitai.com/",  # 机器之心
    ]
    
    print("🔍 测试GIF图片采集功能")
    print("=" * 50)
    
    for url in test_urls:
        print(f"\n🌐 测试网站: {url}")
        print("-" * 30)
        
        try:
            # 1. 获取页面内容
            print("📥 正在获取页面内容...")
            html, title = await CrawlerService.get_page_content(url)
            print(f"📄 页面标题: {title}")
            
            # 2. 提取内容和图片
            print("\n🖼️  正在提取图片...")
            result = CrawlerService.extract_content(html, url)
            
            print(f"📝 内容长度: {len(result['content'])} 字符")
            print(f"📊 总图片数量: {len(result['images'])} 张")
            
            # 3. 统计图片格式
            gif_count = 0
            jpg_count = 0
            png_count = 0
            other_count = 0
            
            for img in result['images']:
                img_url = img.get('url', '')
                if '.gif' in img_url.lower() or 'data:image/gif' in img_url.lower():
                    gif_count += 1
                elif '.jpg' in img_url.lower() or '.jpeg' in img_url.lower():
                    jpg_count += 1
                elif '.png' in img_url.lower():
                    png_count += 1
                else:
                    other_count += 1
            
            print(f"📈 图片格式统计:")
            print(f"   GIF图片: {gif_count} 张")
            print(f"   JPG图片: {jpg_count} 张")
            print(f"   PNG图片: {png_count} 张")
            print(f"   其他格式: {other_count} 张")
            
            # 4. 如果发现GIF，尝试下载测试
            if gif_count > 0:
                print(f"\n🎯 发现 {gif_count} 张GIF图片，正在进行下载测试...")
                
                # 只测试前3张GIF图片
                gif_images = [img for img in result['images'] 
                            if '.gif' in img.get('url', '').lower() or 'data:image/gif' in img.get('url', '').lower()][:3]
                
                for i, img in enumerate(gif_images):
                    print(f"\n--- 测试 GIF {i+1} ---")
                    download_result = CrawlerService.download_image(
                        img['url'], 
                        Path("data/test_gifs"), 
                        i+1, 
                        url
                    )
                    
                    if download_result['success']:
                        print(f"✅ 下载成功: {download_result['local_path']}")
                        print(f"   格式: {download_result.get('format', 'Unknown')}")
                    else:
                        print(f"❌ 下载失败: {download_result['error']}")
                        
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_gif_collection())