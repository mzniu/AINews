import sys
from pathlib import Path
from services.github_screenshot_service import SyncGitHubScreenshotService, ScreenshotOptions
from services.selenium_screenshot_service import SyncSeleniumScreenshotService

def test_highlighted_screenshot():
    """测试带高亮的截图功能"""
    
    print("🎯 测试带高亮的截图功能")
    print("=" * 50)
    
    # 测试URL
    test_url = "https://github.com/http-party/http-server"
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    print("1️⃣ 测试Selenium带高亮截图...")
    try:
        selenium_service = SyncSeleniumScreenshotService(headless=True)
        selenium_path = Path('test_outputs/highlighted_selenium.jpg')
        
        result = selenium_service.take_screenshot_sync(
            test_url, 
            selenium_path,
            width=1920,
            height=1080,
            wait_time=5  # 增加等待时间确保元素加载
        )
        
        if result and selenium_path.exists():
            size_kb = selenium_path.stat().st_size / 1024
            print(f"✅ Selenium高亮截图成功! 文件大小: {size_kb:.1f} KB")
            print(f"   保存路径: {selenium_path}")
        else:
            print("❌ Selenium高亮截图失败")
            
    except Exception as e:
        print(f"❌ Selenium测试异常: {e}")
    
    print("\n2️⃣ 测试Playwright带高亮截图...")
    try:
        # 检查Python版本，如果是3.13则跳过Playwright测试
        python_version = sys.version_info
        if python_version.major == 3 and python_version.minor >= 13:
            print("⚠️  检测到Python 3.13，跳过Playwright测试")
            print("   （Playwright在Python 3.13 Windows环境下有兼容性问题）")
        else:
            playwright_service = SyncGitHubScreenshotService(headless=True)
            playwright_path = Path('test_outputs/highlighted_playwright.jpg')
            
            options = ScreenshotOptions(
                width=1920,
                height=1080,
                wait_time=5000,  # 5秒等待时间
                quality=90
            )
            
            result = playwright_service.take_screenshot_sync(
                test_url,
                playwright_path,
                options
            )
            
            if result and playwright_path.exists():
                size_kb = playwright_path.stat().st_size / 1024
                print(f"✅ Playwright高亮截图成功! 文件大小: {size_kb:.1f} KB")
                print(f"   保存路径: {playwright_path}")
            else:
                print("❌ Playwright高亮截图失败")
                
    except Exception as e:
        print(f"❌ Playwright测试异常: {e}")
    
    print("\n🎯 高亮功能测试完成!")
    print("💡 预期效果:")
    print("   • Stars区域应该有红色边框高亮")
    print("   • 如果找不到具体stars元素，则高亮整个统计区域（橙色边框）")
    print("   • 元素会被滚动到页面中心位置")

def compare_highlight_results():
    """比较高亮前后的效果"""
    
    print("\n📊 高亮效果对比")
    print("=" * 30)
    
    # 这里可以添加对比逻辑，比如检查文件大小差异等
    # 但由于高亮只是视觉效果，文件大小差异可能不大
    
    selenium_path = Path('test_outputs/highlighted_selenium.jpg')
    if selenium_path.exists():
        size = selenium_path.stat().st_size / 1024
        print(f"Selenium高亮截图: {size:.1f} KB")
    
    playwright_path = Path('test_outputs/highlighted_playwright.jpg')
    if playwright_path.exists():
        size = playwright_path.stat().st_size / 1024
        print(f"Playwright高亮截图: {size:.1f} KB")

if __name__ == "__main__":
    test_highlighted_screenshot()
    compare_highlight_results()