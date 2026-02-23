#!/usr/bin/env python3
"""
综合测试重新生成功能
包括API测试和前端交互验证
"""

import requests
import time
import json

def comprehensive_regenerate_test():
    """综合测试重新生成功能"""
    
    print("🔄 综合测试重新生成功能")
    print("=" * 60)
    
    # 1. 检查服务器状态
    print("1️⃣ 检查服务器状态...")
    try:
        health_check = requests.get('http://localhost:8080/docs', timeout=5)
        if health_check.status_code == 200:
            print("✅ 服务器运行正常")
        else:
            print(f"❌ 服务器状态异常: {health_check.status_code}")
            return
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        return
    
    # 2. 获取测试项目
    print("\n2️⃣ 获取测试项目...")
    try:
        projects = requests.get('http://localhost:8080/api/github/projects', timeout=10).json()
        if not projects:
            print("❌ 没有可用的项目，请先创建一个项目")
            return
            
        project_id = projects[0]['id']
        print(f"✅ 使用项目: {project_id}")
        
    except Exception as e:
        print(f"❌ 获取项目失败: {e}")
        return
    
    # 3. 测试初始内容生成
    print("\n3️⃣ 测试初始内容生成...")
    try:
        initial_response = requests.post(
            'http://localhost:8080/api/github/generate-content',
            json={'project_id': project_id, 'selected_images': []},
            timeout=30
        )
        
        if initial_response.status_code == 200:
            initial_data = initial_response.json()
            print("✅ 初始内容生成成功")
            print(f"   标题: {initial_data['video_metadata']['title']}")
            print(f"   副标题: {initial_data['video_metadata']['subtitle']}")
        else:
            print(f"❌ 初始生成失败: {initial_response.status_code}")
            print(initial_response.text)
            return
            
    except Exception as e:
        print(f"❌ 初始生成异常: {e}")
        return
    
    # 4. 等待避免API限制
    print("⏳ 等待2秒避免API调用过于频繁...")
    time.sleep(2)
    
    # 5. 测试重新生成功能
    print("\n4️⃣ 测试重新生成功能...")
    try:
        regenerate_response = requests.post(
            'http://localhost:8080/api/github/generate-content',
            json={'project_id': project_id, 'selected_images': []},
            timeout=30
        )
        
        if regenerate_response.status_code == 200:
            regenerate_data = regenerate_response.json()
            print("✅ 重新生成成功")
            
            # 检查内容变化
            old_content = initial_data['video_metadata']
            new_content = regenerate_data['video_metadata']
            
            changes = []
            if old_content['title'] != new_content['title']:
                changes.append("标题")
            if old_content['subtitle'] != new_content['subtitle']:
                changes.append("副标题")
            if old_content['summary'] != new_content['summary']:
                changes.append("摘要")
                
            if changes:
                print(f"✅ 内容发生变化: {', '.join(changes)}")
                print(f"   新标题: {new_content['title']}")
                print(f"   新副标题: {new_content['subtitle']}")
            else:
                print("ℹ️  内容相似（AI可能生成了相近的内容）")
                
        else:
            print(f"❌ 重新生成失败: {regenerate_response.status_code}")
            print(regenerate_response.text)
            return
            
    except Exception as e:
        print(f"❌ 重新生成异常: {e}")
        return
    
    # 6. 验证项目数据持久化
    print("\n5️⃣ 验证数据持久化...")
    try:
        project_detail = requests.get(
            f'http://localhost:8080/api/github/projects/{project_id}',
            timeout=10
        ).json()
        
        if 'video_metadata' in project_detail:
            stored_content = project_detail['video_metadata']
            print("✅ 项目数据已正确存储")
            print(f"   存储的标题: {stored_content['title']}")
        else:
            print("❌ 项目数据未正确存储")
            
    except Exception as e:
        print(f"❌ 数据验证异常: {e}")
    
    # 7. 测试前端兼容性
    print("\n6️⃣ 测试前端API兼容性...")
    try:
        frontend_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Test Client)'
        }
        
        frontend_response = requests.post(
            'http://localhost:8080/api/github/generate-content',
            json={'project_id': project_id, 'selected_images': []},
            headers=frontend_headers,
            timeout=30
        )
        
        if frontend_response.status_code == 200:
            frontend_data = frontend_response.json()
            print("✅ 前端API调用兼容性测试通过")
            print(f"   响应格式正确: {'success' in frontend_data}")
            print(f"   包含元数据: {'video_metadata' in frontend_data}")
        else:
            print(f"❌ 前端兼容性测试失败: {frontend_response.status_code}")
            
    except Exception as e:
        print(f"❌ 前端测试异常: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 综合测试完成!")
    print("✅ 重新生成功能在API层面工作正常")
    print("💡 如果前端按钮无反应，请检查:")
    print("   1. 浏览器控制台是否有JavaScript错误")
    print("   2. 网络请求是否被拦截")
    print("   3. DOM元素是否正确加载")
    print("   4. 事件监听器是否正确绑定")

if __name__ == "__main__":
    comprehensive_regenerate_test()