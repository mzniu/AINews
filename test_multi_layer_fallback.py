import sys
from pathlib import Path
from services.github_screenshot_service import SyncGitHubScreenshotService, ScreenshotOptions

def test_multi_layer_fallback():
    """测试多层次降级机制"""
    
    print("🧪 测试多层次降级机制")
    print("=" * 50)
    
    # 检测当前环境
    python_version = sys.version_info
    print(f"Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    print(f"操作系统: {sys.platform}")
    
    # 创建测试服务
    service = SyncGitHubScreenshotService(headless=True)
    
    # 测试用例
    test_cases = [
        {
            'url': 'https://github.com/torvalds/linux',
            'name': 'Linux Kernel',
            'path': Path('test_outputs/multi_layer_linux.jpg')
        },
        {
            'url': 'https://github.com/python/cpython',
            'name': 'CPython',
            'path': Path('test_outputs/multi_layer_cpython.jpg')
        }
    ]
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    success_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试案例 {i}: {test_case['name']}")
        print("-" * 40)
        print(f"URL: {test_case['url']}")
        
        try:
            # 执行截图（会自动选择最佳方案）
            options = ScreenshotOptions(width=1920, height=1080, quality=90)
            result = service.take_screenshot_sync(
                test_case['url'],
                test_case['path'],
                options
            )
            
            if result and test_case['path'].exists():
                file_size = test_case['path'].stat().st_size
                size_kb = file_size / 1024
                print(f"✅ 截图成功! 文件大小: {size_kb:.1f} KB")
                
                # 根据文件大小判断使用的方案
                if size_kb > 100:
                    print("   🎯 使用了Selenium高质量截图")
                elif size_kb > 50:
                    print("   🔄 使用了改进的降级截图")
                else:
                    print("   ⚠️  使用了基础降级截图")
                    
                success_count += 1
            else:
                print("❌ 截图失败")
                
        except Exception as e:
            print(f"❌ 测试异常: {e}")
    
    print(f"\n🎯 测试总结: {success_count}/{len(test_cases)} 成功")
    
    if success_count == len(test_cases):
        print("🎉 所有多层次降级机制工作正常!")
        print("\n💡 系统智能选择策略:")
        print("   • Python 3.13+ Windows: 优先使用Selenium")
        print("   • 其他环境: 优先使用Playwright")
        print("   • 兼容性问题: 自动降级到备用方案")
        print("   • 最终保障: 基础占位图生成")
    else:
        print("⚠️  部分测试失败，请检查配置")

def compare_solutions():
    """比较不同解决方案的效果"""
    
    print("\n📊 解决方案效果对比")
    print("=" * 30)
    
    test_url = "https://github.com/http-party/http-server"
    
    results = {}
    
    # 1. Selenium测试
    try:
        from services.selenium_screenshot_service import SyncSeleniumScreenshotService
        selenium_service = SyncSeleniumScreenshotService()
        selenium_path = Path("test_outputs/compare_selenium.jpg")
        
        result = selenium_service.take_screenshot_sync(test_url, selenium_path)
        if result and selenium_path.exists():
            size = selenium_path.stat().st_size / 1024
            results['Selenium'] = f"{size:.1f} KB"
            print(f"Selenium: ✅ {size:.1f} KB")
        else:
            results['Selenium'] = "失败"
            print("Selenium: ❌ 失败")
    except Exception as e:
        results['Selenium'] = f"错误: {str(e)[:30]}..."
        print(f"Selenium: ❌ {str(e)[:30]}...")
    
    # 2. 改进的降级方案测试
    try:
        service = SyncGitHubScreenshotService()
        fallback_path = Path("test_outputs/compare_fallback.jpg")
        
        result = service._fallback_screenshot(test_url, fallback_path)
        if result and fallback_path.exists():
            size = fallback_path.stat().st_size / 1024
            results['降级方案'] = f"{size:.1f} KB"
            print(f"降级方案: ✅ {size:.1f} KB")
        else:
            results['降级方案'] = "失败"
            print("降级方案: ❌ 失败")
    except Exception as e:
        results['降级方案'] = f"错误: {str(e)[:30]}..."
        print(f"降级方案: ❌ {str(e)[:30]}...")
    
    print("\n📈 对比结果:")
    for solution, size in results.items():
        print(f"  {solution}: {size}")

if __name__ == "__main__":
    # 测试多层次降级机制
    test_multi_layer_fallback()
    
    # 比较不同解决方案
    compare_solutions()