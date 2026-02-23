#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GitHub项目视频生成完整演示脚本
展示了如何一键生成GitHub项目的介绍视频
"""

import requests
import time
import os
from pathlib import Path

def demo_github_video_generation():
    """演示GitHub视频生成功能"""
    
    print("🎬 GitHub项目视频生成演示")
    print("=" * 60)
    
    # 测试项目列表
    test_projects = [
        "https://github.com/remotion-dev/remotion",
        "https://github.com/http-party/http-server",
        "https://github.com/vuejs/vue"
    ]
    
    for i, github_url in enumerate(test_projects, 1):
        print(f"\n📋 测试项目 {i}: {github_url}")
        print("-" * 40)
        
        # 1. 生成视频
        print("🎥 正在生成视频...")
        start_time = time.time()
        
        payload = {
            'github_url': github_url,
            'include_screenshots': True,
            'max_images': 5,
            'effect': 'none'
        }
        
        try:
            response = requests.post(
                'http://localhost:8080/api/github/generate-video',
                json=payload,
                timeout=120
            )
            
            processing_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 视频生成成功! (耗时: {processing_time:.1f}秒)")
                
                # 显示生成的内容
                metadata = result['video_metadata']
                print(f"   标题: {metadata['title']}")
                print(f"   副标题: {metadata.get('subtitle', '无')}")
                print(f"   摘要: {metadata['summary'][:60]}...")
                print(f"   标签: {', '.join(metadata['tags'][:3])}")
                print(f"   项目ID: {result['project_id']}")
                
                # 2. 获取项目信息
                projects_response = requests.get('http://localhost:8080/api/github/projects')
                if projects_response.status_code == 200:
                    projects = projects_response.json()
                    latest_project = projects[0]
                    
                    # 3. 尝试获取视频文件
                    video_response = requests.get(
                        f"http://localhost:8080/api/github/projects/{latest_project['id']}/video"
                    )
                    
                    if video_response.status_code == 200:
                        video_filename = f"demonstration_video_{i}_{latest_project['id']}.mp4"
                        with open(video_filename, 'wb') as f:
                            f.write(video_response.content)
                        
                        file_size = os.path.getsize(video_filename)
                        print(f"   📦 视频文件已保存: {video_filename} ({file_size/1024/1024:.2f} MB)")
                    else:
                        print(f"   ⚠️  视频文件获取失败: {video_response.status_code}")
                
            else:
                print(f"❌ 视频生成失败: {response.status_code}")
                print(f"   错误详情: {response.text}")
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
        
        # 添加间隔避免过于频繁的请求
        if i < len(test_projects):
            print("\n⏳ 等待5秒后继续下一个项目...")
            time.sleep(5)
    
    print("\n" + "=" * 60)
    print("🎉 演示完成!")
    print("\n💡 使用说明:")
    print("1. 访问 http://localhost:8080/static/github_video_maker.html 使用Web界面")
    print("2. 或者调用API: POST /api/github/generate-video")
    print("3. 获取视频: GET /api/github/projects/{project_id}/video")

if __name__ == "__main__":
    demo_github_video_generation()