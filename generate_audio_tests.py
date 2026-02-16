#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成用于测试的加速音频文件
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

def generate_test_audio():
    """生成不同速度的测试音频"""
    print("🎵 生成音频速度测试文件")
    print("=" * 40)
    
    try:
        from moviepy.editor import AudioFileClip
        
        # 检查源音频文件
        source_audio = Path("static/music/background.mp3")
        if not source_audio.exists():
            print("❌ 源音频文件不存在:", source_audio)
            return
        
        print(f"🔊 源文件: {source_audio}")
        print(f"   大小: {source_audio.stat().st_size / 1024:.1f} KB")
        
        # 创建测试目录
        test_dir = Path("data/audio_speed_comparison")
        test_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 输出目录: {test_dir}")
        
        # 加载源音频
        audio = AudioFileClip(str(source_audio))
        original_duration = audio.duration
        print(f"⏱️  原始时长: {original_duration:.3f} 秒")
        
        # 生成不同速度的版本
        speeds = [1.0, 1.1, 1.2, 1.25, 1.3, 1.5]
        
        for speed in speeds:
            print(f"\n⚙️  生成 {speed}倍速版本...")
            
            if speed == 1.0:
                # 原始速度直接复制
                output_file = test_dir / f"original_{speed}x.mp3"
                audio.write_audiofile(str(output_file))
            else:
                # 应用速度变换
                audio_sped = audio.fl_time(lambda t: t * speed).set_duration(original_duration / speed)
                output_file = test_dir / f"speed_{speed}x.mp3"
                audio_sped.write_audiofile(str(output_file))
                audio_sped.close()
            
            # 验证生成的文件
            if output_file.exists():
                file_size = output_file.stat().st_size / 1024
                if speed == 1.0:
                    actual_duration = original_duration
                else:
                    test_audio = AudioFileClip(str(output_file))
                    actual_duration = test_audio.duration
                    test_audio.close()
                
                print(f"   ✅ {output_file.name}")
                print(f"      时长: {actual_duration:.3f} 秒")
                print(f"      大小: {file_size:.1f} KB")
                print(f"      压缩: {(original_duration - actual_duration) / original_duration * 100:.1f}%")
            else:
                print(f"   ❌ {output_file.name} 生成失败")
        
        # 生成说明文件
        readme_content = f"""# 音频速度测试文件说明

源文件: {source_audio}
原始时长: {original_duration:.3f} 秒

## 生成的测试文件:

"""
        
        for speed in speeds:
            filename = f"speed_{speed}x.mp3" if speed != 1.0 else f"original_{speed}x.mp3"
            if speed == 1.0:
                duration = original_duration
                compression = 0
            else:
                duration = original_duration / speed
                compression = (original_duration - duration) / original_duration * 100
            
            readme_content += f"- {filename}: {duration:.3f}秒 (快{compression:.1f}%)\n"
        
        readme_content += """
## 测试建议:

1. 按顺序播放文件对比速度差异
2. 注意听语音清晰度和音调变化
3. 选择您认为合适的加速倍数

## 当前视频生成使用的设置:
- 速度: 1.2倍速
- 时长压缩: 16.7%
"""
        
        readme_file = test_dir / "README.md"
        readme_file.write_text(readme_content, encoding='utf-8')
        print(f"\n📝 说明文件: {readme_file}")
        
        # 清理资源
        audio.close()
        
        print(f"\n✅ 测试文件生成完成!")
        print(f"📂 请在 {test_dir} 目录中找到所有测试文件")
        print(f"🎧 建议按顺序试听对比效果")
        
    except Exception as e:
        print(f"❌ 生成过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generate_test_audio()