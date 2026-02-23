"""
快速测试改进后的GitHub截图服务
"""

import sys
from pathlib import Path
from services.selenium_screenshot_service import SyncSeleniumScreenshotService

def quick_test_improved_screenshot():
    """快速测试改进后的截图功能"""
    print("⚡ 快速测试改进后的GitHub截图服务")
    print("=" * 50)
    
    # 测试项目URL
    test_url = "https://github.com/ZiYang-xie/WorldGen"
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    print(f"测试项目: {test_url}")
    print("-" * 40)
    
    # 使用改进后的Selenium截图服务
    print("📸 使用改进后的Selenium截图服务...")
    try:
        selenium_service = SyncSeleniumScreenshotService(headless=True)
        screenshot_path = Path('test_outputs/improved_screenshot.jpg')
        
        result = selenium_service.take_screenshot_sync(
            test_url,
            screenshot_path,
            width=1920,
            height=1080,
            wait_time=15,  # 增加等待时间
            timeout=120    # 增加超时时间
        )
        
        if result and screenshot_path.exists():
            size_kb = screenshot_path.stat().st_size / 1024
            print(f"✅ 截图成功! 文件大小: {size_kb:.1f} KB")
            print(f"📁 文件路径: {screenshot_path.absolute()}")
            print(f"\n🔍 请检查:")
            print(f"   1. Stars区域是否被红色高亮框包围")
            print(f"   2. 页面图片是否正常显示")
            print(f"   3. 整体页面布局是否完整")
            return True
        else:
            print("❌ 截图失败")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False

def main():
    """主函数"""
    print("🚀 GitHub截图服务快速测试")
    print("=" * 60)
    
    success = quick_test_improved_screenshot()
    
    print(f"\n{'='*60}")
    if success:
        print("🎉 测试成功!")
        print("请查看生成的截图文件确认效果")
    else:
        print("❌ 测试失败!")
        print("建议检查网络连接和浏览器驱动")

if __name__ == "__main__":
    main()