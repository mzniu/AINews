#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试GIF动画视频化问题
"""

import sys
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def debug_gif_processing():
    """调试GIF处理流程"""
    print("🔍 调试GIF动画视频化流程")
    print("=" * 50)
    
    # 测试GIF文件
    test_gif = Path("data/test_gifs/bouncing_ball.gif")
    
    if not test_gif.exists():
        print("❌ 测试GIF文件不存在")
        return
    
    print(f"🎯 测试文件: {test_gif}")
    
    # 1. 检查文件是否为GIF
    is_gif = test_gif.suffix.lower() == '.gif'
    print(f"1. 文件格式检查: {is_gif}")
    
    # 2. 使用GIF处理器分析
    from services.gif_processor import gif_processor
    
    print("2. GIF属性分析:")
    props = gif_processor.get_gif_properties(str(test_gif))
    if props:
        print(f"   帧数: {props.get('frame_count', '未知')}")
        print(f"   持续时间: {props.get('duration', '未知')} ms")
        print(f"   循环次数: {props.get('loop_count', '未知')}")
        print(f"   尺寸: {props.get('size', '未知')}")
    
    # 3. 提取帧测试
    print("3. 帧提取测试:")
    frames = gif_processor.extract_gif_frames(str(test_gif))
    if frames:
        print(f"   成功提取 {len(frames)} 帧")
        print(f"   第一帧尺寸: {frames[0].shape}")
    else:
        print("   ❌ 帧提取失败")
        return
    
    # 4. 转换为视频测试
    print("4. 视频转换测试:")
    output_dir = Path("data/debug_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "debug_test.mp4"
    
    success = gif_processor.convert_gif_to_video(
        gif_path=str(test_gif),
        output_path=str(output_path),
        target_duration=3.0
    )
    
    if success and output_path.exists():
        file_size = output_path.stat().st_size / 1024  # KB
        print(f"   ✅ 转换成功: {output_path} ({file_size:.1f} KB)")
        
        # 5. 验证生成的视频
        print("5. 视频验证:")
        try:
            from moviepy.editor import VideoFileClip
            clip = VideoFileClip(str(output_path))
            print(f"   视频时长: {clip.duration:.2f} 秒")
            print(f"   视频FPS: {clip.fps}")
            print(f"   视频尺寸: {clip.size}")
            clip.close()
        except Exception as e:
            print(f"   ❌ 视频验证失败: {e}")
    else:
        print("   ❌ 转换失败")
    
    print(f"\n📊 调试完成！输出文件: {output_dir}")

if __name__ == "__main__":
    debug_gif_processing()