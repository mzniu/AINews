import requests
import time

def test_vertical_layout():
    """测试竖版界面布局"""
    
    print("📱 测试竖版界面布局")
    print("=" * 50)
    
    # 测试完整的四步流程
    print("\n🚀 开始完整流程测试...")
    
    # 步骤1: 处理项目
    print("\n1️⃣ 步骤1：处理GitHub项目")
    payload = {
        'github_url': 'https://github.com/remotion-dev/remotion',
        'include_screenshots': False,
        'include_audio': False,
        'max_images': 2
    }
    
    try:
        response = requests.post(
            'http://localhost:8080/api/github/process-project',
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            project_id = result['project_id']
            print("✅ 项目处理成功!")
            print(f"   项目ID: {project_id}")
            
            # 步骤2: 生成内容
            print("\n2️⃣ 步骤2：生成视频内容")
            content_payload = {
                'project_id': project_id,
                'selected_images': []
            }
            
            content_response = requests.post(
                'http://localhost:8080/api/github/generate-content',
                json=content_payload,
                timeout=30
            )
            
            if content_response.status_code == 200:
                content_result = content_response.json()
                print("✅ 内容生成成功!")
                print(f"   标题: {content_result['video_metadata']['title']}")
                
                # 步骤3: 生成视频
                print("\n3️⃣ 步骤3：生成视频")
                video_payload = {
                    'project_id': project_id,
                    'selected_images': [],
                    'include_audio': False
                }
                
                video_response = requests.post(
                    'http://localhost:8080/api/github/generate-video',
                    json=video_payload,
                    timeout=120
                )
                
                if video_response.status_code == 200:
                    video_result = video_response.json()
                    print("✅ 视频生成成功!")
                    print(f"   视频标题: {video_result['video_metadata']['title']}")
                    
                    # 步骤4: 验证视频预览
                    print("\n4️⃣ 步骤4：验证视频预览")
                    preview_response = requests.get(
                        f'http://localhost:8080/api/github/projects/{project_id}/video'
                    )
                    
                    if preview_response.status_code == 200:
                        print("✅ 视频预览功能正常!")
                        print(f"   视频大小: {len(preview_response.content)} bytes")
                    else:
                        print(f"❌ 视频预览失败: {preview_response.status_code}")
                        
                else:
                    print(f"❌ 视频生成失败: {video_response.status_code}")
                    
            else:
                print(f"❌ 内容生成失败: {content_response.status_code}")
                
        else:
            print(f"❌ 项目处理失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 测试过程中出现异常: {e}")
    
    print("\n🎯 竖版界面布局测试完成!")
    print("请在浏览器中访问 http://localhost:8080/static/github_video_maker.html 体验新界面")

if __name__ == "__main__":
    test_vertical_layout()