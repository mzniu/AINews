"""
测试GitHub截图服务的高亮功能和图片显示
"""

import sys
from pathlib import Path
from services.github_screenshot_service import SyncGitHubScreenshotService
from services.selenium_screenshot_service import SyncSeleniumScreenshotService

def test_github_screenshot_issues():
    """测试GitHub截图的相关问题"""
    print("🔍 测试GitHub截图服务问题")
    print("=" * 50)
    
    # 测试项目URL
    test_url = "https://github.com/ZiYang-xie/WorldGen"
    
    # 确保输出目录存在
    Path('test_outputs').mkdir(exist_ok=True)
    
    print(f"测试项目: {test_url}")
    print("-" * 40)
    
    # 测试1: Selenium截图服务
    print("1️⃣ 测试Selenium截图服务...")
    try:
        selenium_service = SyncSeleniumScreenshotService(headless=True)
        selenium_path = Path('test_outputs/selenium_debug.jpg')
        
        result = selenium_service.take_screenshot_sync(
            test_url,
            selenium_path,
            width=1920,
            height=1080,
            wait_time=10,  # 增加等待时间
            timeout=60
        )
        
        if result and selenium_path.exists():
            size_kb = selenium_path.stat().st_size / 1024
            print(f"✅ Selenium截图成功! 文件大小: {size_kb:.1f} KB")
            
            # 检查图片内容
            print("   📸 截图已保存，可以检查:")
            print(f"   - Stars区域是否被红色高亮框包围")
            print(f"   - 页面图片是否正常显示")
            print(f"   - 文件路径: {selenium_path.absolute()}")
        else:
            print("❌ Selenium截图失败")
            
    except Exception as e:
        print(f"❌ Selenium测试异常: {e}")
    
    print("\n" + "=" * 50)
    
    # 测试2: Playwright截图服务（如果可用）
    print("2️⃣ 测试Playwright截图服务...")
    try:
        import sys
        if sys.version_info >= (3, 13):
            print("⚠️  Python 3.13+ detected, Playwright可能不兼容")
            print("   跳过Playwright测试")
        else:
            playwright_service = SyncGitHubScreenshotService(headless=True)
            playwright_path = Path('test_outputs/playwright_debug.jpg')
            
            result = playwright_service.take_screenshot_sync(
                test_url,
                playwright_path
            )
            
            if result and playwright_path.exists():
                size_kb = playwright_path.stat().st_size / 1024
                print(f"✅ Playwright截图成功! 文件大小: {size_kb:.1f} KB")
            else:
                print("❌ Playwright截图失败")
                
    except Exception as e:
        print(f"❌ Playwright测试异常: {e}")
    
    print("\n" + "=" * 50)
    
    # 测试3: 直接检查GitHub页面元素
    print("3️⃣ 分析GitHub页面元素结构...")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        
        # 设置Chrome选项
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # 启动浏览器
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print(f"正在访问: {test_url}")
        driver.get(test_url)
        
        # 等待页面加载
        driver.implicitly_wait(10)
        
        # 检查页面标题
        title = driver.title
        print(f"页面标题: {title}")
        
        # 检查stars元素
        stars_selectors = [
            '[href*="/stargazers"]',
            '.social-count',
            '[aria-label*="star"]',
            '.BtnGroup-item[href*="stargazers"]',
            'a[href*="stargazers"] .Counter'
        ]
        
        print("\nStars元素检查:")
        for selector in stars_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"✅ 找到 {len(elements)} 个匹配元素: {selector}")
                    for i, elem in enumerate(elements[:3]):  # 只显示前3个
                        text = elem.text.strip() if elem.text else "无文本"
                        print(f"   元素 {i+1}: '{text}'")
                else:
                    print(f"❌ 未找到匹配元素: {selector}")
            except Exception as e:
                print(f"⚠️  检查选择器 {selector} 时出错: {e}")
        
        # 检查图片元素
        print("\n图片元素检查:")
        try:
            img_elements = driver.find_elements(By.TAG_NAME, 'img')
            print(f"✅ 找到 {len(img_elements)} 个图片元素")
            
            # 检查可见的图片
            visible_images = []
            for img in img_elements[:10]:  # 只检查前10个
                try:
                    if img.is_displayed():
                        src = img.get_attribute('src') or '无src属性'
                        alt = img.get_attribute('alt') or '无alt属性'
                        visible_images.append((src, alt))
                except:
                    continue
            
            print(f"✅ 找到 {len(visible_images)} 个可见图片:")
            for i, (src, alt) in enumerate(visible_images[:5]):  # 显示前5个
                print(f"   图片 {i+1}: {alt[:50]}...")
                print(f"   URL: {src[:80]}...")
                
        except Exception as e:
            print(f"❌ 检查图片元素失败: {e}")
        
        driver.quit()
        
    except Exception as e:
        print(f"❌ 页面分析失败: {e}")

def main():
    """主函数"""
    print("🚀 GitHub截图服务问题诊断")
    print("=" * 60)
    
    test_github_screenshot_issues()
    
    print(f"\n📋 诊断完成!")
    print(f"\n常见问题解决方案:")
    print(f"1. Stars未高亮:")
    print(f"   - 检查GitHub页面结构是否发生变化")
    print(f"   - 更新CSS选择器")
    print(f"   - 增加等待时间确保元素加载")
    print(f"")
    print(f"2. 图片未显示:")
    print(f"   - 检查网络连接")
    print(f"   - 增加页面加载等待时间")
    print(f"   - 检查图片懒加载问题")

if __name__ == "__main__":
    main()