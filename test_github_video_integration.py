import requests
import os

def test_github_video_integration():
    print("🚀 GitHub视频生成功能完整测试")
    print("=" * 50)
    
    # 1. 测试视频生成
    print("\n1. 生成GitHub项目视频...")
    payload = {
        'github_url': 'https://github.com/http-party/http-server',
        'include_screenshots': True,
        'max_images': 3
    }
    
    response = requests.post(
        'http://localhost:8080/api/github/generate-video',
        json=payload,
        timeout=120
    )
    
    if response.status_code == 200:
        result = response.json()
        print("✅ 视频生成成功!")
        print(f"   项目ID: {result['project_id']}")
        metadata = result['video_metadata']
        print(f"   标题: {metadata['title']}")
        print(f"   摘要: {metadata['summary'][:50]}...")
        print(f"   标签: {', '.join(metadata['tags'][:3])}")
    else:
        print("❌ 视频生成失败:", response.text)
        return
    
    # 2. 获取项目列表
    print("\n2. 获取项目信息...")
    projects_response = requests.get('http://localhost:8080/api/github/projects')
    projects = projects_response.json()
    latest_project = projects[0]
    print(f"   最新项目: {latest_project['name']} ({latest_project['id']})")
    
    # 3. 测试获取视频文件
    print("\n3. 获取生成的视频文件...")
    video_response = requests.get(f"http://localhost:8080/api/github/projects/{latest_project['id']}/video")
    
    if video_response.status_code == 200:
        # 保存视频文件
        video_filename = f"generated_video_{latest_project['id']}.mp4"
        with open(video_filename, 'wb') as f:
            f.write(video_response.content)
        
        file_size = os.path.getsize(video_filename)
        print(f"✅ 视频文件获取成功!")
        print(f"   文件名: {video_filename}")
        print(f"   大小: {file_size} bytes ({file_size/1024/1024:.2f} MB)")
    else:
        print("❌ 获取视频文件失败:", video_response.text)

if __name__ == "__main__":
    test_github_video_integration()