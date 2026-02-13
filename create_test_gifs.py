#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建测试用的GIF动画文件
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image, ImageDraw
import numpy as np
import imageio
import os

def create_simple_animated_gif(output_path: str, size: tuple = (200, 200), frames: int = 10):
    """创建简单的测试GIF动画"""
    images = []
    
    for i in range(frames):
        # 创建新图像
        img = Image.new('RGB', size, color='white')
        draw = ImageDraw.Draw(img)
        
        # 绘制移动的圆圈
        center_x = size[0] // 2 + int(50 * np.sin(2 * np.pi * i / frames))
        center_y = size[1] // 2 + int(30 * np.cos(2 * np.pi * i / frames))
        radius = 20
        
        # 绘制圆圈
        draw.ellipse([
            center_x - radius, center_y - radius,
            center_x + radius, center_y + radius
        ], fill=(255, 100, 100), outline=(200, 50, 50), width=3)
        
        # 添加帧编号
        draw.text((10, 10), f"Frame {i+1}/{frames}", fill=(0, 0, 0))
        
        images.append(img)
    
    # 保存为GIF
    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        duration=200,  # 每帧200ms
        loop=0  # 无限循环
    )
    print(f"✅ 创建测试GIF: {output_path}")

def create_color_transition_gif(output_path: str, size: tuple = (300, 200), frames: int = 15):
    """创建颜色渐变GIF"""
    images = []
    
    for i in range(frames):
        # 创建渐变背景
        ratio = i / (frames - 1)
        r = int(255 * ratio)
        g = int(255 * (1 - ratio))
        b = 150
        
        img = Image.new('RGB', size, color=(r, g, b))
        draw = ImageDraw.Draw(img)
        
        # 添加文字
        text = f"Color Transition {int(ratio*100)}%"
        draw.text((size[0]//2-50, size[1]//2-10), text, fill='white')
        
        images.append(img)
    
    # 保存为GIF
    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        duration=150,
        loop=0
    )
    print(f"✅ 创建颜色渐变GIF: {output_path}")

def create_bouncing_ball_gif(output_path: str, size: tuple = (250, 250), frames: int = 12):
    """创建弹跳球GIF"""
    images = []
    
    for i in range(frames):
        img = Image.new('RGB', size, color=(240, 240, 255))
        draw = ImageDraw.Draw(img)
        
        # 绘制地面
        draw.rectangle([0, size[1]-20, size[0], size[1]], fill=(100, 180, 100))
        
        # 计算球的位置（抛物线运动）
        t = i / (frames - 1)
        x = size[0] // 2
        y = size[1] - 40 - int(100 * (4 * t * (1 - t)))  # 抛物线轨迹
        
        # 绘制球
        ball_radius = 15
        draw.ellipse([
            x - ball_radius, y - ball_radius,
            x + ball_radius, y + ball_radius
        ], fill=(255, 100, 100), outline=(200, 50, 50), width=2)
        
        # 添加阴影
        shadow_offset = 3
        draw.ellipse([
            x - ball_radius + shadow_offset, size[1] - 25,
            x + ball_radius + shadow_offset, size[1] - 15
        ], fill=(150, 150, 150))
        
        images.append(img)
    
    # 保存为GIF
    images[0].save(
        output_path,
        save_all=True,
        append_images=images[1:],
        duration=180,
        loop=0
    )
    print(f"✅ 创建弹跳球GIF: {output_path}")

def main():
    """创建所有测试GIF文件"""
    print("🎨 创建测试GIF动画文件")
    print("=" * 40)
    
    # 创建测试目录
    test_dir = Path("data/test_gifs")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建不同类型的测试GIF
    test_gifs = [
        ("moving_circle.gif", create_simple_animated_gif),
        ("color_transition.gif", create_color_transition_gif),
        ("bouncing_ball.gif", create_bouncing_ball_gif),
    ]
    
    for filename, creator_func in test_gifs:
        output_path = test_dir / filename
        creator_func(str(output_path))
    
    print(f"\n🎉 所有测试GIF已创建完成！")
    print(f"📁 保存位置: {test_dir.absolute()}")

if __name__ == "__main__":
    main()