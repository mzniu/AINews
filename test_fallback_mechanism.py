import sys
import os
from pathlib import Path
from services.github_screenshot_service import SyncGitHubScreenshotService, ScreenshotOptions

def test_improved_fallback():
    """测试改进的降级机制"""
    
    print("🔧 测试改进的Playwright降级机制")
    print("=" * 50)
    
    # 创建测试服务
    service = SyncGitHubScreenshotService(headless=True)
    
    # 测试数据
    test_cases = [
        {
            'url': 'https://github.com/torvalds/linux',
            'name': 'Linux Kernel',
            'path': Path('test_outputs/linux_fallback.jpg')
        },
        {
            'url': 'https://github.com/python/cpython',
            'name': 'CPython',
            'path': Path('test_outputs/cpython_fallback.jpg')
        }
    ]
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    success_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试案例 {i}: {test_case['name']}")
        print("-" * 30)
        print(f"URL: {test_case['url']}")
        print(f"保存路径: {test_case['path']}")
        
        try:
            # 执行截图
            result = service.take_screenshot_sync(
                test_case['url'],
                test_case['path'],
                ScreenshotOptions(width=1200, height=800, quality=85)
            )
            
            if result and test_case['path'].exists():
                file_size = test_case['path'].stat().st_size
                print(f"✅ 截图成功! 文件大小: {file_size} bytes")
                success_count += 1
            else:
                print("❌ 截图失败")
                
        except Exception as e:
            print(f"❌ 测试异常: {e}")
    
    print(f"\n🎯 测试总结: {success_count}/{len(test_cases)} 成功")
    
    if success_count == len(test_cases):
        print("🎉 所有测试通过！降级机制工作正常")
    else:
        print("⚠️  部分测试失败，请检查配置")

def test_python_version_detection():
    """测试Python版本检测"""
    
    print("\n🔍 Python版本兼容性检测")
    print("=" * 30)
    
    python_version = sys.version_info
    print(f"当前Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    print(f"操作系统: {sys.platform}")
    
    # 检测已知的兼容性问题
    compatibility_issues = []
    
    if python_version.major == 3 and python_version.minor >= 13 and sys.platform == 'win32':
        compatibility_issues.append("Python 3.13+ on Windows - Playwright可能有兼容性问题")
    
    if compatibility_issues:
        print("⚠️  检测到潜在兼容性问题:")
        for issue in compatibility_issues:
            print(f"  - {issue}")
        print("💡 系统将自动使用降级方案")
    else:
        print("✅ 未检测到已知兼容性问题")

if __name__ == "__main__":
    # 先进行版本检测
    test_python_version_detection()
    
    # 然后测试降级机制
    test_improved_fallback()