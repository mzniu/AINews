#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试GIF处理器功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.gif_processor import gif_processor
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_gif_processor():
    """测试GIF处理器的各项功能"""
    print("🧪 测试GIF处理器功能")
    print("=" * 40)
    
    # 测试目录
    test_dir = Path("data/test_gifs")
    output_dir = Path("data/test_gif_videos")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取所有测试GIF文件
    test_gifs = list(test_dir.glob("*.gif"))
    
    if not test_gifs:
        print("❌ 没有找到测试GIF文件")
        return
    
    print(f"🔍 找到 {len(test_gifs)} 个测试GIF文件")
    
    for gif_path in test_gifs:
        print(f"\n--- 测试文件: {gif_path.name} ---")
        
        # 1. 格式检测测试
        print("1. 格式检测测试:")
        is_gif = gif_processor.is_gif_file(str(gif_path))
        print(f"   是否为GIF文件: {is_gif}")
        
        # 2. 属性提取测试
        print("2. 属性提取测试:")
        props = gif_processor.get_gif_properties(str(gif_path))
        if props:
            print(f"   帧数: {props.get('frame_count', '未知')}")
            print(f"   持续时间: {props.get('duration', '未知')} ms")
            print(f"   循环次数: {props.get('loop_count', '未知')}")
            print(f"   尺寸: {props.get('size', '未知')}")
        else:
            print("   ❌ 无法提取属性")
            continue
        
        # 3. 兼容性分析测试
        print("3. 兼容性分析测试:")
        analysis = gif_processor.analyze_gif_compatibility(str(gif_path))
        print(f"   是否有效: {analysis['is_valid']}")
        if analysis['issues']:
            print(f"   问题: {', '.join(analysis['issues'])}")
        if analysis['recommendations']:
            print(f"   建议: {', '.join(analysis['recommendations'])}")
        
        # 4. 帧提取测试
        print("4. 帧提取测试:")
        frames = gif_processor.extract_gif_frames(str(gif_path))
        if frames:
            print(f"   ✅ 成功提取 {len(frames)} 帧")
            print(f"   帧尺寸: {frames[0].shape if frames else '未知'}")
        else:
            print("   ❌ 帧提取失败")
            continue
        
        # 5. 视频转换测试
        print("5. 视频转换测试:")
        output_path = output_dir / f"{gif_path.stem}_converted.mp4"
        success = gif_processor.convert_gif_to_video(
            gif_path=str(gif_path),
            output_path=str(output_path),
            target_duration=3.0  # 3秒视频
        )
        
        if success and output_path.exists():
            file_size = output_path.stat().st_size / 1024  # KB
            print(f"   ✅ 转换成功")
            print(f"   输出文件: {output_path}")
            print(f"   文件大小: {file_size:.1f} KB")
        else:
            print("   ❌ 转换失败")
    
    # 6. 测试便捷函数
    print(f"\n--- 测试便捷函数 ---")
    sample_gif = test_gifs[0] if test_gifs else None
    if sample_gif:
        print("测试 process_gif_for_video 函数:")
        result_path = gif_processor.process_gif_for_video(
            gif_path=str(sample_gif),
            target_duration=2.5,
            output_dir=str(output_dir)
        )
        
        if result_path:
            print(f"   ✅ 便捷函数执行成功: {result_path}")
        else:
            print("   ❌ 便捷函数执行失败")

if __name__ == "__main__":
    test_gif_processor()