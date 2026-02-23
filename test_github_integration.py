"""
GitHub项目处理完整测试脚本
测试从项目输入到内容生成的完整流程
"""
import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8080/api/github"

def test_health_check():
    """测试健康检查"""
    print("🔍 测试健康检查...")
    response = requests.get(f"{BASE_URL}/health")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 健康检查通过 - 项目数量: {data['projects_count']}")
        return True
    else:
        print(f"❌ 健康检查失败: {response.status_code}")
        return False

def test_project_list():
    """测试项目列表"""
    print("\\n📋 测试项目列表...")
    response = requests.get(f"{BASE_URL}/projects")
    if response.status_code == 200:
        projects = response.json()
        print(f"✅ 获取到 {len(projects)} 个项目")
        for project in projects:
            print(f"  - {project['name']} ({project['id']})")
        return True
    else:
        print(f"❌ 获取项目列表失败: {response.status_code}")
        return False

def test_project_processing():
    """测试项目处理"""
    print("\\n🚀 测试项目处理...")
    
    # 使用一个简单的测试项目
    test_project_url = "https://github.com/http-party/http-server"
    
    payload = {
        "github_url": test_project_url,
        "include_screenshots": False,  # 为了测试速度，不包含截图
        "max_images": 5
    }
    
    print(f"处理项目: {test_project_url}")
    
    response = requests.post(
        f"{BASE_URL}/process-project",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        result = response.json()
        if result["success"]:
            project_id = result["project_id"]
            print(f"✅ 项目处理成功!")
            print(f"  项目ID: {project_id}")
            print(f"  处理时间: {result['processing_time']:.2f}秒")
            return project_id
        else:
            print(f"❌ 项目处理失败: {result['message']}")
            return None
    else:
        print(f"❌ HTTP请求失败: {response.status_code}")
        print(f"响应内容: {response.text}")
        return None

def test_image_selection(project_id):
    """测试图片选择"""
    if not project_id:
        return False
    
    print(f"\\n🖼️ 测试图片选择 (项目ID: {project_id})...")
    
    # 获取可用图片
    response = requests.get(f"{BASE_URL}/projects/{project_id}/images")
    if response.status_code == 200:
        image_data = response.json()
        available_images = image_data["available_images"]
        print(f"✅ 找到 {len(available_images)} 张图片")
        
        # 选择前几张图片
        selected_ids = [img["id"] for img in available_images[:3]]
        print(f"选择图片: {selected_ids}")
        
        # 发送选择请求
        response = requests.post(
            f"{BASE_URL}/projects/{project_id}/select-images",
            json=selected_ids,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            print("✅ 图片选择保存成功")
            return True
        else:
            print(f"❌ 图片选择失败: {response.status_code}")
            return False
    else:
        print(f"❌ 获取图片列表失败: {response.status_code}")
        return False

def test_content_generation(project_id):
    """测试内容生成"""
    if not project_id:
        return False
    
    print(f"\\n🤖 测试内容生成 (项目ID: {project_id})...")
    
    payload = {
        "project_id": project_id,
        "selected_images": []  # 使用所有已选择的图片
    }
    
    response = requests.post(
        f"{BASE_URL}/generate-content",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        result = response.json()
        if result["success"]:
            metadata = result["video_metadata"]
            print("✅ 内容生成成功!")
            print(f"  标题: {metadata['title']}")
            print(f"  副标题: {metadata.get('subtitle', 'N/A')}")
            print(f"  摘要: {metadata['summary']}")
            print(f"  标签: {', '.join(metadata['tags'])}")
            print(f"  AI生成: {metadata['ai_generated']}")
            return True
        else:
            print(f"❌ 内容生成失败: {result.get('processing_details', {}).get('error', '未知错误')}")
            return False
    else:
        print(f"❌ 内容生成请求失败: {response.status_code}")
        print(f"响应内容: {response.text}")
        return False

def test_project_details(project_id):
    """测试项目详情获取"""
    if not project_id:
        return False
    
    print(f"\\n📄 测试项目详情获取 (项目ID: {project_id})...")
    
    response = requests.get(f"{BASE_URL}/projects/{project_id}")
    if response.status_code == 200:
        project_data = response.json()
        print("✅ 项目详情获取成功!")
        print(f"  项目名称: {project_data['name']}")
        print(f"  描述: {project_data.get('description', 'N/A')}")
        print(f"  语言: {project_data.get('language', 'N/A')}")
        print(f"  Stars: {project_data['stars']}")
        print(f"  图片数量: {len(project_data.get('images', []))}")
        return True
    else:
        print(f"❌ 获取项目详情失败: {response.status_code}")
        return False

def run_complete_test():
    """运行完整测试流程"""
    print("=" * 50)
    print("🚀 GitHub项目处理完整测试开始")
    print("=" * 50)
    
    start_time = time.time()
    
    # 1. 健康检查
    if not test_health_check():
        return False
    
    # 2. 项目列表
    test_project_list()
    
    # 3. 项目处理
    project_id = test_project_processing()
    if not project_id:
        return False
    
    # 4. 图片选择
    if not test_image_selection(project_id):
        return False
    
    # 5. 内容生成
    if not test_content_generation(project_id):
        return False
    
    # 6. 项目详情
    test_project_details(project_id)
    
    # 7. 最终项目列表
    print("\\n📋 最终项目列表:")
    test_project_list()
    
    end_time = time.time()
    print(f"\\n🎉 完整测试完成! 总耗时: {end_time - start_time:.2f}秒")
    print(f"✅ 测试项目ID: {project_id}")
    print(f"🌐 前端页面访问: http://localhost:8080/static/github_video_maker.html")
    
    return True

if __name__ == "__main__":
    success = run_complete_test()
    exit(0 if success else 1)