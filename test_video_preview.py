import requests
import time

def test_video_preview_feature():
    """测试视频预览功能"""
    
    print("📺 测试视频预览功能")
    print("=" * 50)
    
    # 生成一个测试视频
    print("\n1. 生成测试视频...")
    payload = {
        'github_url': 'https://github.com/remotion-dev/remotion',
        'include_screenshots': False,
        'include_audio': False,
        'max_images': 2
    }
    
    try:
        response = requests.post(
            'http://localhost:8080/api/github/generate-video',
            json=payload,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            project_id = result['project_id']
            print("✅ 视频生成成功!")
            print(f"   项目ID: {project_id}")
            print(f"   标题: {result['video_metadata']['title']}")
            
            # 测试视频预览API
            print("\n2. 测试视频预览功能...")
            video_response = requests.get(
                f'http://localhost:8080/api/github/projects/{project_id}/video'
            )
            
            if video_response.status_code == 200:
                print("✅ 视频预览API正常工作!")
                print(f"   视频大小: {len(video_response.content)} bytes")
                print(f"   内容类型: {video_response.headers.get('content-type', 'unknown')}")
                
                # 保存测试视频
                with open(f'test_preview_{project_id}.mp4', 'wb') as f:
                    f.write(video_response.content)
                print(f"   测试视频已保存为: test_preview_{project_id}.mp4")
                
            else:
                print(f"❌ 视频预览API失败: {video_response.status_code}")
                print(f"   错误信息: {video_response.text}")
                
        else:
            print(f"❌ 视频生成失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            
    except Exception as e:
        print(f"❌ 测试过程中出现异常: {e}")
    
    print("\n🎯 功能测试完成!")
    print("请在浏览器中访问 http://localhost:8080/static/github_video_maker.html 体验视频预览功能")

if __name__ == "__main__":
    test_video_preview_feature()