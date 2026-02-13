#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GIF动画视频化功能综合测试
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.gif_processor import gif_processor
from services.crawler_service import CrawlerService
import asyncio
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def comprehensive_gif_test():
    """GIF功能综合测试"""
    print("🎭 GIF动画视频化功能综合测试")
    print("=" * 50)
    
    # 1. 测试本地GIF文件处理
    print("\n1️⃣ 测试本地GIF文件处理")
    test_dir = Path("data/test_gifs")
    if test_dir.exists():
        test_gifs = list(test_dir.glob("*.gif"))
        print(f"   找到 {len(test_gifs)} 个测试GIF文件")
        
        for gif_path in test_gifs[:2]:  # 只测试前2个
            print(f"\n   🔍 测试: {gif_path.name}")
            
            # 分析GIF
            analysis = gif_processor.analyze_gif_compatibility(str(gif_path))
            print(f"   兼容性: {'✅' if analysis['is_valid'] else '⚠️'}")
            if analysis['issues']:
                print(f"   问题: {', '.join(analysis['issues'])}")
            
            # 转换为视频
            output_path = Path("data/test_outputs") / f"{gif_path.stem}_converted.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            success = gif_processor.convert_gif_to_video(
                gif_path=str(gif_path),
                output_path=str(output_path),
                target_duration=3.0
            )
            
            if success and output_path.exists():
                size_kb = output_path.stat().st_size / 1024
                print(f"   ✅ 转换成功 ({size_kb:.1f} KB)")
            else:
                print("   ❌ 转换失败")
    else:
        print("   ⚠️  未找到测试GIF文件")
    
    # 2. 测试网络GIF采集
    print("\n2️⃣ 测试网络GIF采集")
    test_urls = [
        "https://www.36kr.com/",
        "https://www.qbitai.com/"
    ]
    
    for url in test_urls:
        print(f"\n   🌐 测试网站: {url}")
        try:
            html, title = await CrawlerService.get_page_content(url)
            result = CrawlerService.extract_content(html, url)
            
            # 统计GIF图片
            gif_images = [img for img in result['images'] 
                         if '.gif' in img.get('url', '').lower() or 
                            'data:image/gif' in img.get('url', '').lower()]
            
            print(f"   标题: {title}")
            print(f"   总图片: {len(result['images'])} 张")
            print(f"   GIF图片: {len(gif_images)} 张")
            
            if gif_images:
                print("   🎬 发现的GIF:")
                for i, img in enumerate(gif_images[:3]):  # 显示前3个
                    print(f"     {i+1}. {img.get('url', '')[:60]}...")
                    
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")
    
    # 3. 测试API功能
    print("\n3️⃣ 测试API功能")
    print("   启动服务器后可访问以下端点:")
    print("   - GET  /api/gif/analyze-gif?gif_path={path}")
    print("   - POST /api/gif/process-gif")
    print("   - POST /api/gif/batch-process-gifs")
    print("   - GET  /api/gif/extract-frames?gif_path={path}")
    
    # 4. 性能基准测试
    print("\n4️⃣ 性能基准测试")
    if test_dir.exists():
        benchmark_gif = list(test_dir.glob("*.gif"))[0] if list(test_dir.glob("*.gif")) else None
        if benchmark_gif:
            import time
            
            print(f"   基准文件: {benchmark_gif.name}")
            
            # 测试帧提取性能
            start_time = time.time()
            frames = gif_processor.extract_gif_frames(str(benchmark_gif))
            extract_time = time.time() - start_time
            
            # 测试转换性能
            start_time = time.time()
            output_path = Path("data/benchmark_output.mp4")
            success = gif_processor.convert_gif_to_video(
                gif_path=str(benchmark_gif),
                output_path=str(output_path),
                target_duration=2.0
            )
            convert_time = time.time() - start_time
            
            if success:
                print(f"   帧提取: {len(frames)} 帧, 耗时 {extract_time:.2f} 秒")
                print(f"   视频转换: 耗时 {convert_time:.2f} 秒")
                print(f"   输出大小: {output_path.stat().st_size / 1024:.1f} KB")
            else:
                print("   ❌ 性能测试失败")
    
    print("\n🎉 综合测试完成！")
    print("\n💡 使用建议:")
    print("   1. 在网页界面中选择包含GIF的图片")
    print("   2. 点击'分析GIF'按钮查看详细信息") 
    print("   3. 生成视频时会自动处理GIF动画")
    print("   4. 最终视频将包含GIF的动态效果")

if __name__ == "__main__":
    asyncio.run(comprehensive_gif_test())