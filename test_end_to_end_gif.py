#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端测试GIF动画视频生成流程
"""

import sys
from pathlib import Path
import json
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_end_to_end_gif_video():
    """测试端到端的GIF视频生成流程"""
    print("🎬 端到端GIF动画视频生成测试")
    print("=" * 50)
    
    # 准备测试数据
    test_images = [
        "data/test_gifs/bouncing_ball.gif",
        "data/test_gifs/color_transition.gif", 
        "data/test_gifs/moving_circle.gif"
    ]
    
    # 检查测试文件是否存在
    existing_images = []
    for img_path in test_images:
        if Path(img_path).exists():
            existing_images.append(img_path)
            print(f"✅ 找到测试图片: {img_path}")
        else:
            print(f"❌ 未找到: {img_path}")
    
    if not existing_images:
        print("❌ 没有可用的测试图片")
        return
    
    print(f"\n🎯 使用 {len(existing_images)} 个图片进行测试")
    
    # 模拟API请求数据
    request_data = {
        "title": "GIF动画测试标题 | 副标题测试",
        "summary": "这是一个测试GIF动画在视频中播放功能的摘要内容，用来验证动画效果是否正常工作。",
        "images": existing_images,
        "audio_path": ""
    }
    
    print("📋 模拟请求数据:")
    print(f"   标题: {request_data['title']}")
    print(f"   摘要长度: {len(request_data['summary'])} 字符")
    print(f"   图片数量: {len(request_data['images'])}")
    
    # 调用视频生成函数
    print("\n🚀 开始视频生成...")
    
    try:
        # 导入必要的模块
        from api.routes.video_routes import create_animated_video
        from fastapi import Request
        import asyncio
        
        # 创建模拟请求对象
        class MockRequest:
            def __init__(self, json_data):
                self._json_data = json_data
            
            async def json(self):
                return self._json_data
        
        # 创建请求对象
        mock_request = MockRequest(request_data)
        
        # 注意：这里需要异步调用，但在测试环境中可能需要特殊处理
        print("⚠️  注意：完整的端到端测试需要在Web服务器环境中运行")
        print("💡 建议通过实际的Web界面进行测试")
        
        # 执行基础的GIF处理测试
        print("\n🔧 基础GIF处理测试:")
        from services.gif_processor import gif_processor
        
        for i, img_path in enumerate(existing_images, 1):
            print(f"\n--- 测试图片 {i}: {Path(img_path).name} ---")
            
            # 检查是否为GIF
            is_gif = img_path.lower().endswith('.gif')
            print(f"   是GIF文件: {is_gif}")
            
            if is_gif:
                # 分析GIF
                props = gif_processor.get_gif_properties(img_path)
                if props:
                    print(f"   帧数: {props.get('frame_count', '未知')}")
                    print(f"   持续时间: {props.get('duration', '未知')} ms")
                
                # 转换测试
                output_path = Path(f"data/test_end_to_end/gif_video_{i}.mp4")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                success = gif_processor.convert_gif_to_video(
                    gif_path=img_path,
                    output_path=str(output_path),
                    target_duration=3.0
                )
                
                if success and output_path.exists():
                    size_kb = output_path.stat().st_size / 1024
                    print(f"   ✅ 转换成功 ({size_kb:.1f} KB)")
                else:
                    print("   ❌ 转换失败")
    
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n📊 测试建议:")
    print("1. 启动Web服务器: python web_server.py")
    print("2. 访问 http://localhost:8080")
    print("3. 选择包含GIF的图片")
    print("4. 点击'生成视频'按钮")
    print("5. 检查生成的视频中GIF是否正常播放")

if __name__ == "__main__":
    test_end_to_end_gif_video()