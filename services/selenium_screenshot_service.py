"""
Selenium截图服务
作为Playwright的替代方案，特别针对Python 3.13兼容性问题
"""
import asyncio
import sys
from pathlib import Path
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from loguru import logger


class SeleniumScreenshotService:
    """基于Selenium的截图服务"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    
    def start(self):
        """启动Chrome浏览器"""
        try:
            # 配置Chrome选项
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument('--headless=new')
            
            # 基本配置
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--window-size=1920,1080')
            
            # 用户代理
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # 自动下载和配置ChromeDriver（多种备选方案）
            drivers_tried = []
            
            # 方案1: 使用webdriver-manager（在线）
            try:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Selenium Chrome浏览器启动成功 (webdriver-manager)")
                return
            except Exception as e:
                drivers_tried.append(f"webdriver-manager: {str(e)[:50]}")
                logger.debug(f"webdriver-manager失败: {e}")
            
            # 方案2: 使用系统已安装的chromedriver
            try:
                service = Service()
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.info("Selenium Chrome浏览器启动成功 (系统chromedriver)")
                return
            except Exception as e:
                drivers_tried.append(f"系统chromedriver: {str(e)[:50]}")
                logger.debug(f"系统chromedriver失败: {e}")
            
            # 方案3: 直接指定常见的ChromeDriver路径
            common_paths = [
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                "./chromedriver.exe",  # 项目目录下的chromedriver
                "chromedriver.exe"     # PATH中的chromedriver
            ]
            
            for chrome_path in common_paths:
                try:
                    if Path(chrome_path).exists() or "chrome.exe" in chrome_path:
                        service = Service(chrome_path) if "chromedriver" in chrome_path else Service()
                        self.driver = webdriver.Chrome(service=service, options=chrome_options)
                        logger.info(f"Selenium Chrome浏览器启动成功 (路径: {chrome_path})")
                        return
                except Exception as e:
                    drivers_tried.append(f"路径{chrome_path}: {str(e)[:50]}")
                    logger.debug(f"路径{chrome_path}失败: {e}")
            
            # 所有方案都失败
            error_msg = "无法启动Chrome浏览器。尝试过的驱动: " + "; ".join(drivers_tried)
            logger.error(error_msg)
            raise Exception(error_msg)
            
        except Exception as e:
            logger.error(f"Selenium浏览器启动失败: {e}")
            raise
    
    def stop(self):
        """停止浏览器"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("Selenium浏览器已停止")
        except Exception as e:
            logger.error(f"停止Selenium浏览器失败: {e}")
    
    def take_screenshot(self, 
                       url: str, 
                       save_path: Path,
                       width: int = 1920,
                       height: int = 1080,
                       wait_time: int = 3,
                       timeout: int = 60) -> bool:
        """
        截取网页截图
        """
        try:
            if not self.driver:
                logger.error("浏览器未启动")
                return False
            
            # 确保保存目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 设置窗口大小
            self.driver.set_window_size(width, height)
            
            # 访问页面并设置超时
            logger.info(f"正在访问: {url}")
            self.driver.set_page_load_timeout(max(timeout, 120))  # 增加超时时间
            self.driver.get(url)
            
            # 等待页面加载
            try:
                WebDriverWait(self.driver, min(timeout, 60)).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception as e:
                logger.warning(f"页面加载等待超时: {e}, 继续执行截图")
                pass  # 即使等待失败也继续
            
            # 额外等待时间，确保所有资源加载完成
            self.driver.implicitly_wait(max(wait_time, 10))  # 增加等待时间
            
            # 高亮显示stars区域
            self._highlight_stars_area()
            
            # 隐藏不需要的元素（类似Playwright版本）
            self._hide_elements()
            
            # 滚动到顶部
            self.driver.execute_script("window.scrollTo(0, 0)")
            
            # 截图
            success = self.driver.save_screenshot(str(save_path))
            
            if success:
                logger.info(f"截图已保存: {save_path}")
                return True
            else:
                logger.error("截图保存失败")
                return False
                
        except Exception as e:
            logger.error(f"Selenium截图失败: {e}")
            return False
    
    def _highlight_stars_area(self):
        """高亮显示GitHub项目页面的stars区域"""
        try:
            # GitHub stars区域的常见选择器（更新后的，包含您提供的准确类名）
            stars_selectors = [
                'a.Link--muted[href*="stargazers"]',     # 您提供的准确stars链接类名
                'a[href*="stargazers"] .Counter',        # Star计数器
                '[href*="/stargazers"]',                 # Star链接
                '.social-count.js-social-count',          # 社交计数
                '[aria-label*="star"]',                 # 包含star的元素
                '.BtnGroup-item[href*="stargazers"]',    # Star按钮组
                'a[data-tab-item="i1-stargazers"]',      # 新的tab结构
                '.d-inline-block.mr-3',                   # 星星图标容器
                '.octicon.octicon-star'                   # 星星图标
            ]
            
            # 查找并高亮第一个匹配的元素
            for selector in stars_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        element = elements[0]  # 选择第一个匹配的元素
                        
                        # 添加红色边框高亮
                        self.driver.execute_script("""
                            arguments[0].style.border = '4px solid red';
                            arguments[0].style.boxShadow = '0 0 15px red';
                            arguments[0].style.backgroundColor = 'rgba(255, 0, 0, 0.2)';
                            arguments[0].style.zIndex = '9999';
                            arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});
                        """, element)
                        
                        logger.info(f"成功高亮stars区域: {selector}")
                        return
                except Exception as e:
                    logger.debug(f"尝试选择器 {selector} 失败: {e}")
                    continue
            
            # 如果没有找到特定的stars元素，尝试高亮整个项目统计区域
            try:
                # GitHub项目页的统计区域
                stats_selectors = [
                    '.pagehead-actions',                   # 页面头部操作区域
                    '.repository-content .BorderGrid-cell', # 仓库内容网格单元
                    '.Layout-sidebar .BorderGrid-cell',    # 侧边栏统计区域
                    '.flex-items-center.flex-wrap',        # Flex布局的统计区域
                    '.d-flex.flex-items-center'            # Flex对齐的元素
                ]
                
                for selector in stats_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            element = elements[0]
                            self.driver.execute_script("""
                                arguments[0].style.border = '3px solid orange';
                                arguments[0].style.boxShadow = '0 0 10px orange';
                                arguments[0].style.backgroundColor = 'rgba(255, 165, 0, 0.1)';
                                arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});
                            """, element)
                            logger.info(f"高亮统计区域: {selector}")
                            return
                    except Exception as e:
                        logger.debug(f"尝试统计区域选择器 {selector} 失败: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"高亮stars区域失败: {e}")
                
        except Exception as e:
            logger.error(f"高亮功能异常: {e}")
    
    def _hide_elements(self):
        """隐藏页面上的特定元素"""
        hide_selectors = [
            'header',
            '.Header',
            '.footer',
            '.Footer',
            'nav',
            '.navigation'
        ]
        
        for selector in hide_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    self.driver.execute_script("arguments[0].style.display='none';", element)
            except Exception as e:
                logger.debug(f"隐藏元素 {selector} 失败: {e}")


class SyncSeleniumScreenshotService:
    """同步接口的Selenium截图服务"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
    
    def take_screenshot_sync(self, 
                           url: str, 
                           save_path: Path,
                           width: int = 1920,
                           height: int = 1080,
                           wait_time: int = 3,
                           timeout: int = 60) -> bool:
        """同步截图接口"""
        try:
            # 检查Python版本兼容性
            python_version = sys.version_info
            if python_version.major == 3 and python_version.minor >= 13 and sys.platform == 'win32':
                logger.info("检测到Python 3.13，优先使用Selenium替代方案")
            
            with SeleniumScreenshotService(self.headless) as service:
                return service.take_screenshot(url, save_path, width, height, wait_time, timeout)
                
        except Exception as e:
            logger.error(f"Selenium同步截图失败: {e}")
            return False
    
    def stop(self):
        """停止服务（兼容性方法）"""
        logger.info("SyncSeleniumScreenshotService不需要显式停止")
        pass


# 测试函数
def test_selenium_screenshot():
    """测试Selenium截图功能"""
    print("🧪 测试Selenium截图功能")
    print("=" * 40)
    
    service = SyncSeleniumScreenshotService()
    test_url = "https://github.com/torvalds/linux"
    save_path = Path("test_selenium_screenshot.jpg")
    
    try:
        result = service.take_screenshot_sync(test_url, save_path)
        if result and save_path.exists():
            size_kb = save_path.stat().st_size / 1024
            print(f"✅ Selenium截图成功! 文件大小: {size_kb:.1f} KB")
            return True
        else:
            print("❌ Selenium截图失败")
            return False
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False


if __name__ == "__main__":
    test_selenium_screenshot()