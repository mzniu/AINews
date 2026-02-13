#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试GIF处理功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.crawler_service import CrawlerService
import base64

def test_gif_functions():
    """测试GIF相关功能"""
    print("🔍 测试GIF处理功能")
    print("=" * 30)
    
    # 创建测试目录
    test_dir = Path("data/test_gif_functions")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 测试GIF data URI处理
    print("\n1. 测试GIF data URI处理")
    print("-" * 20)
    
    # 简单的1x1透明GIF
    simple_gif_base64 = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    gif_data_uri = f"data:image/gif;base64,{simple_gif_base64}"
    
    result = CrawlerService._handle_gif_data_uri(gif_data_uri, test_dir, 1)
    print(f"处理结果: {result}")
    
    if result['success']:
        print(f"✅ GIF data URI处理成功")
        print(f"   保存路径: {result['local_path']}")
        print(f"   格式: {result['format']}")
    else:
        print(f"❌ GIF data URI处理失败: {result['error']}")
    
    # 2. 测试Content-Type检测
    print("\n2. 测试HTTP Content-Type检测")
    print("-" * 20)
    
    test_urls = [
        "https://httpbin.org/image/jpeg",  # JPEG图片
        "https://httpbin.org/image/png",   # PNG图片
        "https://httpbin.org/image/svg",   # SVG图片
    ]
    
    for url in test_urls:
        try:
            import requests
            response = requests.head(url, timeout=10)
            content_type = response.headers.get('content-type', 'unknown')
            print(f"URL: {url}")
            print(f"Content-Type: {content_type}")
            
            # 模拟我们的扩展名检测逻辑
            if 'gif' in content_type:
                ext = '.gif'
            elif 'png' in content_type:
                ext = '.png'
            elif 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            else:
                ext = '.unknown'
            
            print(f"检测到的扩展名: {ext}")
            print()
            
        except Exception as e:
            print(f"测试 {url} 失败: {e}")
    
    # 3. 测试文件格式验证
    print("3. 测试图片文件验证")
    print("-" * 20)
    
    try:
        from PIL import Image
        import io
        
        # 创建一个简单的测试图片
        test_image = Image.new('RGB', (10, 10), color='red')
        test_buffer = io.BytesIO()
        test_image.save(test_buffer, format='JPEG')
        test_buffer.seek(0)
        
        # 保存到文件
        test_file = test_dir / "test_image.jpg"
        with open(test_file, 'wb') as f:
            f.write(test_buffer.getvalue())
        
        # 验证图片
        try:
            with Image.open(test_file) as img:
                img.verify()
            print(f"✅ 图片验证成功: {test_file}")
        except Exception as e:
            print(f"❌ 图片验证失败: {e}")
            
    except ImportError:
        print("⚠️  PIL库未安装，跳过图片验证测试")

if __name__ == "__main__":
    test_gif_functions()