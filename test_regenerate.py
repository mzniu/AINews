import requests
import time

def test_regenerate_function():
    """测试重新生成功能"""
    
    print("🔄 测试重新生成功能")
    print("=" * 50)
    
    # 获取现有项目
    projects_response = requests.get('http://localhost:8080/api/github/projects')
    projects = projects_response.json()
    
    if not projects:
        print("❌ 没有找到现有项目，请先创建一个项目")
        return
    
    project_id = projects[0]['id']
    print(f"✅ 使用项目: {project_id}")
    
    # 第一次生成内容
    print("\n1️⃣ 首次生成内容...")
    first_response = requests.post(
        'http://localhost:8080/api/github/generate-content',
        json={
            'project_id': project_id,
            'selected_images': []
        }
    )
    
    if first_response.status_code == 200:
        first_result = first_response.json()
        first_content = first_result['video_metadata']
        print("✅ 首次生成成功!")
        print(f"   标题: {first_content['title']}")
        print(f"   副标题: {first_content['subtitle']}")
        print(f"   摘要: {first_content['summary'][:50]}...")
    else:
        print(f"❌ 首次生成失败: {first_response.status_code}")
        print(first_response.text)
        return
    
    # 等待一下避免API调用过于频繁
    time.sleep(2)
    
    # 重新生成内容
    print("\n2️⃣ 重新生成内容...")
    regenerate_response = requests.post(
        'http://localhost:8080/api/github/generate-content',
        json={
            'project_id': project_id,
            'selected_images': []
        }
    )
    
    if regenerate_response.status_code == 200:
        regenerate_result = regenerate_response.json()
        regenerated_content = regenerate_result['video_metadata']
        print("✅ 重新生成成功!")
        print(f"   标题: {regenerated_content['title']}")
        print(f"   副标题: {regenerated_content['subtitle']}")
        print(f"   摘要: {regenerated_content['summary'][:50]}...")
        
        # 检查内容是否有变化
        content_changed = (
            first_content['title'] != regenerated_content['title'] or
            first_content['subtitle'] != regenerated_content['subtitle'] or
            first_content['summary'] != regenerated_content['summary']
        )
        
        if content_changed:
            print("✅ 内容确实发生了变化（AI重新生成）")
        else:
            print("⚠️  内容相同，可能是缓存或者AI生成了一样的内容")
            
    else:
        print(f"❌ 重新生成失败: {regenerate_response.status_code}")
        print(regenerate_response.text)
        return
    
    # 测试前端调用
    print("\n3️⃣ 测试前端API调用...")
    frontend_response = requests.post(
        'http://localhost:8080/api/github/generate-content',
        json={
            'project_id': project_id,
            'selected_images': []
        },
        headers={'Content-Type': 'application/json'}
    )
    
    if frontend_response.status_code == 200:
        print("✅ 前端API调用正常!")
        frontend_result = frontend_response.json()
        print(f"   返回格式正确: {'success' in frontend_result}")
        print(f"   包含视频元数据: {'video_metadata' in frontend_result}")
    else:
        print(f"❌ 前端API调用失败: {frontend_response.status_code}")
    
    print("\n🎯 重新生成功能测试完成!")

if __name__ == "__main__":
    test_regenerate_function()