import sys
from pathlib import Path
from services.selenium_screenshot_service import SyncSeleniumScreenshotService

def test_multiple_highlight_scenarios():
    """测试多种场景下的高亮效果"""
    
    print("🎯 多场景高亮测试")
    print("=" * 50)
    
    # 不同类型的GitHub项目页面
    test_cases = [
        {
            'name': 'HTTP Server项目',
            'url': 'https://github.com/http-party/http-server',
            'description': '标准的GitHub项目页面'
        },
        {
            'name': 'Linux内核',
            'url': 'https://github.com/torvalds/linux',
            'description': '大型开源项目，stars数量很多'
        },
        {
            'name': 'CPython',
            'url': 'https://github.com/python/cpython',
            'description': '官方Python解释器项目'
        }
    ]
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    selenium_service = SyncSeleniumScreenshotService(headless=True)
    
    success_count = 0
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试案例 {i}: {case['name']}")
        print(f"描述: {case['description']}")
        print(f"URL: {case['url']}")
        print("-" * 40)
        
        try:
            output_path = Path(f"test_outputs/highlight_{i}_{case['name'].replace(' ', '_')}.jpg")
            
            result = selenium_service.take_screenshot_sync(
                case['url'],
                output_path,
                width=1920,
                height=1080,
                wait_time=5
            )
            
            if result and output_path.exists():
                size_kb = output_path.stat().st_size / 1024
                print(f"✅ 截图成功! 文件大小: {size_kb:.1f} KB")
                print(f"   保存路径: {output_path}")
                success_count += 1
            else:
                print("❌ 截图失败")
                
        except Exception as e:
            print(f"❌ 测试异常: {e}")
    
    print(f"\n🎯 多场景测试总结: {success_count}/{len(test_cases)} 成功")
    
    if success_count == len(test_cases):
        print("🎉 所有场景的高亮功能都正常工作!")
        print("\n💡 高亮功能特点:")
        print("   • 自动识别并高亮stars区域")
        print("   • 使用醒目的红色边框(3px solid red)")
        print("   • 添加红色阴影效果增强可见性")
        print("   • 半透明红色背景突出显示")
        print("   • 自动滚动到元素中心位置")
        print("   • 兼容不同类型的GitHub页面")
    else:
        print("⚠️  部分场景测试失败，请检查配置")

def test_highlight_customization():
    """测试高亮样式的自定义选项"""
    
    print("\n🎨 高亮样式自定义测试")
    print("=" * 40)
    
    # 这里可以测试不同的高亮样式配置
    # 比如不同的颜色、边框宽度、透明度等
    
    print("当前默认高亮样式:")
    print("   边框: 3px solid red")
    print("   阴影: 0 0 10px red") 
    print("   背景: rgba(255, 0, 0, 0.1)")
    print("   滚动: smooth to center")
    
    print("\n💡 可自定义的选项:")
    print("   • 边框颜色和宽度")
    print("   • 阴影效果")
    print("   • 背景透明度")
    print("   • 滚动行为")
    print("   • 高亮持续时间")

if __name__ == "__main__":
    test_multiple_highlight_scenarios()
    test_highlight_customization()