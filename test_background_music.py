import requests
import time

def test_background_music_feature():
    """测试背景音乐功能"""
    
    print("🎵 测试背景音乐功能")
    print("=" * 50)
    
    # 测试1: 不包含音频的视频生成
    print("\n1. 测试不包含背景音乐的视频生成...")
    payload_no_audio = {
        'github_url': 'https://github.com/remotion-dev/remotion',
        'include_screenshots': False,
        'include_audio': False,  # 不包含音频
        'max_images': 2
    }
    
    try:
        response = requests.post(
            'http://localhost:8080/api/github/generate-video',
            json=payload_no_audio,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 无音频视频生成成功!")
            print(f"   项目: {result['project_id']}")
            print(f"   标题: {result['video_metadata']['title']}")
        else:
            print(f"❌ 无音频视频生成失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 无音频视频生成异常: {e}")
    
    # 等待一下避免请求过于频繁
    time.sleep(2)
    
    # 测试2: 包含音频的视频生成
    print("\n2. 测试包含背景音乐的视频生成...")
    payload_with_audio = {
        'github_url': 'https://github.com/http-party/http-server',
        'include_screenshots': False,
        'include_audio': True,  # 包含音频
        'max_images': 2
    }
    
    try:
        response = requests.post(
            'http://localhost:8080/api/github/generate-video',
            json=payload_with_audio,
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 有音频视频生成成功!")
            print(f"   项目: {result['project_id']}")
            print(f"   标题: {result['video_metadata']['title']}")
        else:
            print(f"❌ 有音频视频生成失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 有音频视频生成异常: {e}")
    
    print("\n🎯 功能测试完成!")
    print("请在浏览器中访问 http://localhost:8080/static/github_video_maker.html 体验完整功能")

if __name__ == "__main__":
    test_background_music_feature()