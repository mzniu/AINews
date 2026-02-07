"""简单测试Playwright功能"""
from playwright.sync_api import sync_playwright
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.logger import logger

def test_playwright():
    """测试Playwright基本功能"""
    logger.info("测试Playwright访问36氪AI频道")
    
    url = "https://www.36kr.com/information/AI/"
    
    try:
        with sync_playwright() as p:
            logger.info("启动浏览器...")
            browser = p.chromium.launch(headless=True)
            
            logger.info("创建页面...")
            page = browser.new_page()
            
            logger.info(f"访问: {url}")
            page.goto(url, wait_until='networkidle', timeout=30000)
            
            logger.info("等待页面加载...")
            page.wait_for_timeout(2000)
            
            # 获取标题
            title = page.title()
            logger.success(f"✅ 页面标题: {title}")
            
            # 获取页面内容
            html = page.content()
            logger.success(f"✅ 页面内容长度: {len(html)} 字符")
            
            # 查找链接
            links = page.query_selector_all('a')
            logger.success(f"✅ 找到 {len(links)} 个链接")
            
            # 显示前几个链接
            logger.info("\n前5个链接:")
            for i, link in enumerate(links[:5], 1):
                try:
                    text = link.inner_text()
                    href = link.get_attribute('href')
                    if text and href:
                        logger.info(f"  [{i}] {text[:40]} -> {href[:60]}")
                except:
                    pass
            
            browser.close()
            logger.success("\n✅ Playwright测试成功!")
            return True
            
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = test_playwright()
    sys.exit(0 if success else 1)
