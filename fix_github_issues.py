"""
针对GitHub截图问题的专项修复和测试
"""

import sys
from pathlib import Path
from services.selenium_screenshot_service import SyncSeleniumScreenshotService

def fix_and_test_specific_issues():
    """针对具体问题的修复和测试"""
    print("🔧 GitHub截图专项问题修复测试")
    print("=" * 50)
    
    # 测试项目URL
    test_url = "https://github.com/ZiYang-xie/WorldGen"
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    print("问题诊断和修复:")
    print("1. ⚠️  页面加载超时问题")
    print("2. 🔴 Stars高亮显示问题") 
    print("3. 🖼️  图片显示不完整问题")
    print("-" * 40)
    
    # 方案1: 使用更快的轻量级截图
    print("方案1: 轻量级截图测试...")
    try:
        selenium_service = SyncSeleniumScreenshotService(headless=True)
        lightweight_path = Path('test_outputs/lightweight_screenshot.jpg')
        
        # 减少等待时间，快速截图
        result = selenium_service.take_screenshot_sync(
            test_url,
            lightweight_path,
            width=1280,    # 减小分辨率
            height=720,    # 减小分辨率
            wait_time=5,   # 减少等待时间
            timeout=30     # 减少超时时间
        )
        
        if result and lightweight_path.exists():
            size_kb = lightweight_path.stat().st_size / 1024
            print(f"✅ 轻量级截图成功! 文件大小: {size_kb:.1f} KB")
            print(f"📁 文件: {lightweight_path.absolute()}")
        else:
            print("❌ 轻量级截图失败")
            
    except Exception as e:
        print(f"❌ 轻量级测试异常: {e}")
    
    print("\n" + "-" * 40)
    
    # 方案2: 手动测试Stars高亮逻辑
    print("方案2: 手动验证Stars高亮逻辑...")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        import time
        
        # 设置Chrome选项（非headless模式便于观察）
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1280,720')
        
        print("启动浏览器进行手动测试...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print(f"打开页面: {test_url}")
        driver.get(test_url)
        
        # 等待页面加载
        time.sleep(8)
        
        # 尝试各种Stars选择器
        stars_selectors = [
            'a[href*="stargazers"] .Counter',
            '[href*="/stargazers"]',
            '.social-count.js-social-count',
            '[aria-label*="star"]',
            '.BtnGroup-item[href*="stargazers"]',
            'a[data-tab-item="i1-stargazers"]',
            '.d-inline-block.mr-3',
            '.octicon.octicon-star'
        ]
        
        print("\n测试Stars选择器:")
        found_selector = None
        for selector in stars_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"✅ 找到匹配元素: {selector} (共{len(elements)}个)")
                    found_selector = selector
                    # 高亮第一个元素
                    driver.execute_script("""
                        arguments[0].style.border = '4px solid red';
                        arguments[0].style.boxShadow = '0 0 15px red';
                        arguments[0].style.backgroundColor = 'rgba(255, 0, 0, 0.3)';
                        arguments[0].style.zIndex = '9999';
                        arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});
                    """, elements[0])
                    break
                else:
                    print(f"❌ 未找到: {selector}")
            except Exception as e:
                print(f"⚠️  测试 {selector} 时出错: {e}")
        
        if found_selector:
            print(f"\n🎉 找到有效的Stars选择器: {found_selector}")
            print("🔴 Stars区域应该已被红色高亮框包围")
            
            # 保存截图
            manual_screenshot = Path('test_outputs/manual_stars_highlight.jpg')
            driver.save_screenshot(str(manual_screenshot))
            print(f"📸 手动测试截图已保存: {manual_screenshot.absolute()}")
            
            # 保持浏览器打开一段时间供观察
            print("\n浏览器将保持打开30秒供观察...")
            time.sleep(30)
        else:
            print("\n❌ 未找到有效的Stars选择器")
            print("可能需要更新CSS选择器或检查GitHub页面结构变化")
        
        driver.quit()
        
    except Exception as e:
        print(f"❌ 手动测试失败: {e}")

def main():
    """主函数"""
    print("🎯 GitHub截图问题专项修复")
    print("=" * 60)
    
    fix_and_test_specific_issues()
    
    print(f"\n{'='*60}")
    print("📋 问题解决建议:")
    print("1. 页面加载超时:")
    print("   - 检查网络连接稳定性")
    print("   - 考虑使用代理或VPN")
    print("   - 减少截图分辨率和等待时间")
    print("")
    print("2. Stars高亮问题:")
    print("   - GitHub可能更新了页面结构")
    print("   - 需要更新CSS选择器")
    print("   - 可以参考手动测试结果调整选择器")
    print("")
    print("3. 图片显示问题:")
    print("   - 增加页面加载等待时间")
    print("   - 检查图片懒加载机制")
    print("   - 考虑分段截图策略")

if __name__ == "__main__":
    main()