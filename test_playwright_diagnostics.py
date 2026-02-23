import asyncio
import sys
from playwright.async_api import async_playwright
from loguru import logger

async def test_playwright_basic():
    """测试Playwright基本功能"""
    print("🧪 测试Playwright基本功能")
    print("=" * 50)
    
    try:
        print("1. 启动Playwright...")
        playwright = await async_playwright().start()
        print("✅ Playwright启动成功")
        
        print("2. 启动Chromium浏览器...")
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        )
        print("✅ 浏览器启动成功")
        
        print("3. 创建新页面...")
        page = await browser.new_page()
        print("✅ 页面创建成功")
        
        print("4. 设置视口...")
        await page.set_viewport_size({"width": 1920, "height": 1080})
        print("✅ 视口设置成功")
        
        print("5. 访问测试页面...")
        await page.goto("https://httpbin.org/html", wait_until="networkidle", timeout=10000)
        print("✅ 页面访问成功")
        
        print("6. 等待页面加载...")
        await page.wait_for_timeout(2000)
        print("✅ 页面加载完成")
        
        print("7. 截图...")
        await page.screenshot(path="test_screenshot.jpg", full_page=True, quality=80)
        print("✅ 截图成功")
        
        print("8. 关闭资源...")
        await page.close()
        await browser.close()
        await playwright.stop()
        print("✅ 资源清理完成")
        
        print("\n🎉 Playwright基本功能测试通过!")
        return True
        
    except Exception as e:
        print(f"❌ Playwright测试失败: {e}")
        logger.exception("Playwright错误详情:")
        return False

def test_sync_wrapper():
    """测试同步包装器"""
    print("\n🔄 测试同步包装器")
    print("=" * 30)
    
    try:
        import asyncio
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(test_playwright_basic())
            print(f"同步包装器结果: {'成功' if result else '失败'}")
            return result
        finally:
            loop.close()
            
    except Exception as e:
        print(f"❌ 同步包装器测试失败: {e}")
        return False

if __name__ == "__main__":
    # 测试异步版本
    print("测试异步版本:")
    asyncio.run(test_playwright_basic())
    
    # 测试同步版本
    print("\n" + "="*60)
    test_sync_wrapper()