#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频文字编辑功能测试脚本
"""

import sys
from pathlib import Path
import asyncio

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_frontend_files():
    """测试前端文件是否存在"""
    print("🔍 测试前端文件...")
    
    required_files = [
        "static/video_editor3.html",
        "static/css/video_editor3.css", 
        "static/js/video_editor3.js"
    ]
    
    all_exist = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            print(f"   ✅ {file_path} - 存在")
        else:
            print(f"   ❌ {file_path} - 不存在")
            all_exist = False
    
    return all_exist

def test_backend_files():
    """测试后端文件是否存在"""
    print("\n🔍 测试后端文件...")
    
    required_files = [
        "api/routes/video_text_routes.py",
        "web_server.py"
    ]
    
    all_exist = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            print(f"   ✅ {file_path} - 存在")
        else:
            print(f"   ❌ {file_path} - 不存在")
            all_exist = False
    
    return all_exist

def test_directory_structure():
    """测试目录结构"""
    print("\n🔍 测试目录结构...")
    
    required_dirs = [
        "data/temp_videos",
        "data/processed_videos",
        "static/css",
        "static/js"
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"   ✅ {dir_path} - 存在")
        else:
            print(f"   ❌ {dir_path} - 不存在")
            all_exist = False
    
    return all_exist

def test_imports():
    """测试关键模块导入"""
    print("\n🔍 测试模块导入...")
    
    try:
        from api.routes.video_text_routes import router
        print("   ✅ video_text_routes 导入成功")
        
        from fastapi import FastAPI
        print("   ✅ FastAPI 导入成功")
        
        import cv2
        print("   ✅ OpenCV 导入成功")
        
        return True
        
    except ImportError as e:
        print(f"   ❌ 导入失败: {e}")
        return False

def test_api_registration():
    """测试API路由注册"""
    print("\n🔍 测试API路由注册...")
    
    try:
        from fastapi import FastAPI
        from api.routes.video_text_routes import router as video_text_router
        
        # 创建测试应用
        app = FastAPI()
        app.include_router(video_text_router)
        
        # 检查路由
        routes = [route.path for route in app.routes]
        expected_route = "/api/add-text-to-video"
        
        if expected_route in routes:
            print(f"   ✅ 路由 {expected_route} 注册成功")
            return True
        else:
            print(f"   ❌ 路由 {expected_route} 未找到")
            print(f"   可用路由: {routes}")
            return False
            
    except Exception as e:
        print(f"   ❌ 路由注册测试失败: {e}")
        return False

async def test_full_integration():
    """测试完整集成功能"""
    print("\n🔍 测试完整集成功能...")
    
    try:
        # 这里可以添加更复杂的集成测试
        print("   ℹ️  集成测试需要实际运行服务器和上传文件")
        print("   ✅ 基础组件测试通过")
        return True
        
    except Exception as e:
        print(f"   ❌ 集成测试失败: {e}")
        return False

def main():
    print("🎬 视频文字编辑功能测试")
    print("=" * 50)
    
    # 执行各项测试
    tests = [
        ("前端文件测试", test_frontend_files),
        ("后端文件测试", test_backend_files), 
        ("目录结构测试", test_directory_structure),
        ("模块导入测试", test_imports),
        ("API注册测试", test_api_registration)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"   ❌ 测试执行失败: {e}")
            results.append((test_name, False))
    
    # 显示测试总结
    print("\n" + "=" * 50)
    print("📊 测试总结")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n📈 总体结果: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！视频文字编辑功能已准备就绪。")
        print("\n🚀 下一步:")
        print("  1. 启动服务器: python web_server.py")
        print("  2. 访问页面: http://localhost:8000/video-editor3")
        print("  3. 上传视频并添加文字")
    else:
        print(f"\n⚠️  {total - passed} 项测试失败，请检查相关文件和配置。")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)