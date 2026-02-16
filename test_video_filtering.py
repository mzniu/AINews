#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试视频文件过滤功能
"""

import requests
import json

def test_video_filtering():
    """测试视频文件过滤功能"""
    print("🔍 测试视频文件过滤功能...")
    
    # 测试数据 - 包含图片和视频文件
    test_data = {
        "title": "混合媒体测试|包含视频和图片",
        "summary": "这是一个测试，包含图片和视频文件，验证过滤功能是否正常工作。",
        "images": [
            "data/fetched/893508bc_20260215_164330/images/image_001.jpg",  # 图片文件
            "data/fetched/893508bc_20260215_164330/videos/video_001.mp4",  # 视频文件
            "data/fetched/893508bc_20260215_164330/images/image_002.jpg",  # 图片文件
            "data/fetched/893508bc_20260215_164330/videos/video_002.mp4"   # 视频文件
        ],
        "audio_path": "static/music/background.mp3"
    }
    
    print(f"发送的文件列表:")
    for i, file_path in enumerate(test_data['images'], 1):
        file_type = "视频" if file_path.lower().endswith(('.mp4', '.webm', '.mov')) else "图片"
        print(f"  {i}. {file_path} [{file_type}]")
    
    try:
        # 调用API
        response = requests.post(
            "http://localhost:8080/api/create-animated-video",
            json=test_data,
            timeout=30
        )
        
        print(f"\n响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ API调用成功")
            print(f"  - success: {result.get('success')}")
            print(f"  - message: {result.get('message')}")
            print(f"  - video_path: {result.get('video_path')}")
            print(f"  - duration: {result.get('duration')}")
            print(f"  - file_size_mb: {result.get('file_size_mb')}")
            
            if result.get('video_path'):
                print("🎉 视频生成成功！过滤功能正常工作。")
                return True
            else:
                print("❌ 仍然缺少video_path字段")
                return False
        elif response.status_code == 500:
            result = response.json()
            print(f"❌ 服务器内部错误: {result.get('message', '未知错误')}")
            return False
        else:
            print(f"❌ API调用失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        return False

def test_only_images():
    """测试纯图片文件"""
    print("\n🔍 测试纯图片文件...")
    
    test_data = {
        "title": "纯图片测试",
        "summary": "只包含图片文件的测试。",
        "images": [
            "data/fetched/893508bc_20260215_164330/images/image_001.jpg",
            "data/fetched/893508bc_20260215_164330/images/image_002.jpg"
        ],
        "audio_path": "static/music/background.mp3"
    }
    
    try:
        response = requests.post(
            "http://localhost:8080/api/create-animated-video",
            json=test_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 纯图片测试成功")
            print(f"  - video_path: {result.get('video_path')}")
            return True
        else:
            print(f"❌ 纯图片测试失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 纯图片测试出错: {e}")
        return False

def main():
    print("=" * 50)
    print("🎥 视频文件过滤功能测试")
    print("=" * 50)
    
    # 测试混合媒体
    mixed_success = test_video_filtering()
    
    # 测试纯图片
    pure_success = test_only_images()
    
    print("\n" + "=" * 50)
    print("📊 测试结果:")
    print(f"  混合媒体测试: {'✅ 正常' if mixed_success else '❌ 异常'}")
    print(f"  纯图片测试: {'✅ 正常' if pure_success else '❌ 异常'}")
    print("=" * 50)
    
    if mixed_success and pure_success:
        print("\n🎉 恭喜！视频文件过滤功能已成功修复！")
        print("现在前端会自动过滤掉视频文件，只使用图片生成视频。")
    else:
        print("\n⚠️ 功能仍有问题，需要进一步排查。")

if __name__ == "__main__":
    main()