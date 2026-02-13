#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试音频速度处理功能
"""

import sys
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_audio_speed():
    """测试音频速度处理"""
    print("🎵 测试音频速度处理功能")
    print("=" * 40)
    
    # 检查音频文件是否存在
    audio_path = Path("static/music/background.mp3")
    if not audio_path.exists():
        print("❌ 音频文件不存在:", audio_path)
        return
    
    print(f"🔊 找到音频文件: {audio_path}")
    print(f"   文件大小: {audio_path.stat().st_size / 1024:.1f} KB")
    
    try:
        from moviepy.editor import AudioFileClip
        import time
        
        # 加载原始音频
        print("\n1. 加载原始音频:")
        original_audio = AudioFileClip(str(audio_path))
        original_duration = original_audio.duration
        print(f"   原始时长: {original_duration:.2f} 秒")
        
        # 应用1.1倍速
        print("\n2. 应用1.1倍速:")
        speed = 1.1
        sped_up_audio = original_audio.fl_time(lambda t: t / speed).set_duration(original_duration / speed)
        new_duration = sped_up_audio.duration
        print(f"   加速后时长: {new_duration:.2f} 秒")
        print(f"   时间压缩比例: {(original_duration - new_duration) / original_duration * 100:.1f}%")
        
        # 验证速度计算是否正确
        expected_duration = original_duration / speed
        print(f"   预期时长: {expected_duration:.2f} 秒")
        print(f"   计算准确: {abs(new_duration - expected_duration) < 0.01}")
        
        # 保存测试文件进行听觉验证
        print("\n3. 生成测试文件:")
        test_dir = Path("data/audio_test")
        test_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存原始音频片段
        original_test = test_dir / "original_3sec.mp3"
        original_segment = original_audio.subclip(0, min(3, original_duration))
        original_segment.write_audiofile(str(original_test))
        print(f"   原始音频片段: {original_test}")
        
        # 保存加速音频片段
        sped_test = test_dir / "sped_3sec.mp3"  
        sped_segment = sped_up_audio.subclip(0, min(3/speed, new_duration))
        sped_segment.write_audiofile(str(sped_test))
        print(f"   加速音频片段: {sped_test}")
        
        # 清理资源
        original_audio.close()
        sped_up_audio.close()
        original_segment.close()
        sped_segment.close()
        
        print(f"\n✅ 音频速度测试完成！")
        print(f"📊 请比较生成的两个测试文件来验证速度变化")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_audio_speed()