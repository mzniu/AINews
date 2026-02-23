"""
测试更新后的Stars高亮功能
"""

import sys
from pathlib import Path
from services.selenium_screenshot_service import SyncSeleniumScreenshotService

def test_updated_stars_highlight():
    """测试更新后的Stars高亮功能"""
    print("🧪 测试更新后的Stars高亮功能")
    print("=" * 50)
    
    # 测试项目URL
    test_url = "https://github.com/ZiYang-xie/WorldGen"
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    print(f"测试项目: {test_url}")
    print(f"使用的CSS选择器: a.Link--muted[href*='stargazers']")
    print("-" * 40)
    
    try:
        # 使用更新后的Selenium截图服务
        selenium_service = SyncSeleniumScreenshotService(headless=False)  # 非headless模式便于观察
        test_path = Path('test_outputs/stars_highlight_test.jpg')
        
        print("📸 开始截图测试...")
        result = selenium_service.take_screenshot_sync(
            test_url,
            test_path,
            width=1920,
            height=1080,
            wait_time=10,
            timeout=60
        )
        
        if result and test_path.exists():
            size_kb = test_path.stat().st_size / 1024
            print(f"✅ 截图成功! 文件大小: {size_kb:.1f} KB")
            print(f"📁 截图文件: {test_path.absolute()}")
            print(f"\n🔍 请检查:")
            print(f"   ✅ Stars区域是否被红色边框包围")
            print(f"   ✅ 边框宽度是否为4像素")
            print(f"   ✅ 是否有红色阴影效果")
            print(f"   ✅ 背景是否为半透明红色")
            return True
        else:
            print("❌ 截图失败")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False

def main():
    """主函数"""
    print("🚀 Stars高亮功能测试")
    print("=" * 60)
    
    success = test_updated_stars_highlight()
    
    print(f"\n{'='*60}")
    if success:
        print("🎉 测试完成!")
        print("请查看生成的截图确认Stars高亮效果")
        print("\n💡 如果仍然没有红色边框，请检查:")
        print("   1. 网络连接是否稳定")
        print("   2. 页面是否完全加载")
        print("   3. GitHub页面结构是否发生变化")
    else:
        print("❌ 测试失败!")
        print("建议检查网络连接和浏览器驱动")

if __name__ == "__main__":
    main()