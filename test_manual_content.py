#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试手动内容处理功能
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_html_processing():
    """测试 HTML 内容处理"""
    print("🔍 测试 HTML 内容处理...")
    
    # 模拟 HTML 内容
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>测试文章标题</title></head>
    <body>
        <article>
            <h1>这是一个测试标题</h1>
            <div class="article-content">
                <p>这是第一段内容，包含一些测试文本。</p>
                <p>这是第二段内容，继续测试。</p>
                <img src="/images/test1.jpg" alt="测试图片 1">
                <img src="https://example.com/images/test2.png" alt="测试图片 2">
                <video src="/videos/test.mp4"></video>
            </div>
        </article>
    </body>
    </html>
    """
    
    from api.routes.manual_content_routes import process_html_content
    
    result = process_html_content(html_content, "https://example.com/article/123")
    
    print(f"   ✅ 标题：{result['title']}")
    print(f"   ✅ 内容长度：{len(result['content'])} 字符")
    print(f"   ✅ 图片数量：{len(result['images'])}")
    print(f"   ✅ 视频数量：{len(result['videos'])}")
    
    assert '测试' in result['title']
    assert len(result['images']) >= 2
    
    return True

def test_text_processing():
    """测试纯文本处理"""
    print("\n🔍 测试纯文本处理...")
    
    text_content = """
    这是一篇纯文本文章
    
    第一段内容：介绍主题。
    第二段内容：详细说明。
    第三段内容：总结。
    
    参考链接：https://example.com/image.jpg
    """
    
    from api.routes.manual_content_routes import process_text_content
    
    result = process_text_content(text_content)
    
    print(f"   ✅ 标题：{result['title']}")
    print(f"   ✅ 内容长度：{len(result['content'])} 字符")
    print(f"   ✅ 图片数量：{len(result['images'])}")
    
    assert '纯文本' in result['title']
    
    return True

def test_api_router():
    """测试 API 路由注册"""
    print("\n🔍 测试 API 路由注册...")
    
    from fastapi import FastAPI
    from api.routes.manual_content_routes import router
    
    app = FastAPI()
    app.include_router(router)
    
    routes = [route.path for route in app.routes]
    
    print(f"   ✅ 可用路由：{routes}")
    assert '/api/process-manual-content' in routes
    
    return True

def main():
    print("🎬 手动内容处理功能测试")
    print("=" * 50)
    
    tests = [
        ("HTML 处理测试", test_html_processing),
        ("文本处理测试", test_text_processing),
        ("API 路由测试", test_api_router)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"   ❌ 测试失败：{e}")
            import traceback
            traceback.print_exc()
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
    
    print(f"\n📈 总体结果：{passed}/{total} 项测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！手动内容处理功能已准备就绪。")
        print("\n🚀 使用方法:")
        print("  1. 启动服务器：python web_server.py")
        print("  2. 访问页面：http://localhost:8000/")
        print("  3. 切换到'手动粘贴'模式")
        print("  4. 粘贴 HTML 源码或纯文本")
        print("  5. 点击'处理内容'按钮")
    else:
        print(f"\n⚠️  {total - passed} 项测试失败，请检查相关代码。")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)