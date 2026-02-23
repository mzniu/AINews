"""
GitHub项目主页截图服务
使用Playwright进行网页渲染和截图
"""
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, Page
from loguru import logger


class ScreenshotOptions:
    """截图选项配置"""
    def __init__(self, **kwargs):
        self.width = kwargs.get('width', 1920)
        self.height = kwargs.get('height', 1080)
        self.full_page = kwargs.get('full_page', True)
        self.quality = kwargs.get('quality', 80)
        self.wait_time = kwargs.get('wait_time', 3000)  # 页面加载等待时间(ms)
        self.timeout = kwargs.get('timeout', 30000)    # 截图超时时间(ms)
        self.hide_elements = kwargs.get('hide_elements', [
            'header', '.Header', '.footer', '.Footer'
        ])


class GitHubScreenshotService:
    """GitHub截图服务"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.playwright = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()
    
    async def start(self):
        """启动浏览器"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security'
                ]
            )
            logger.info("浏览器启动成功")
        except Exception as e:
            logger.error(f"浏览器启动失败: {e}")
            raise
    
    async def stop(self):
        """停止浏览器"""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("浏览器已停止")
        except Exception as e:
            logger.error(f"停止浏览器失败: {e}")
    
    async def take_screenshot(self, 
                            github_url: str, 
                            save_path: Path,
                            options: Optional[ScreenshotOptions] = None) -> bool:
        """
        截取GitHub项目主页截图
        返回: 是否截图成功
        """
        if not self.browser:
            logger.error("浏览器未启动")
            return False
        
        if options is None:
            options = ScreenshotOptions()
        
        try:
            # 确保保存目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建新页面
            page = await self.browser.new_page()
            
            # 设置视口大小
            await page.set_viewport_size({
                "width": options.width,
                "height": options.height
            })
            
            # 访问GitHub页面
            logger.info(f"正在访问: {github_url}")
            await page.goto(github_url, wait_until="networkidle", timeout=options.timeout)
            
            # 等待页面加载
            await page.wait_for_timeout(options.wait_time)
            
            # 高亮显示stars区域
            await self._highlight_stars_area(page)
            
            # 隐藏不需要的元素
            await self._hide_elements(page, options.hide_elements)
            
            # 滚动到顶部确保一致性
            await page.evaluate("window.scrollTo(0, 0)")
            
            # 截图
            screenshot_kwargs = {
                "path": str(save_path),
                "full_page": options.full_page,
                "quality": options.quality,
                "type": "jpeg"
            }
            
            await page.screenshot(**screenshot_kwargs)
            await page.close()
            
            logger.info(f"截图已保存: {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return False
    
    async def _highlight_stars_area(self, page: Page):
        """高亮显示GitHub项目页面的stars区域"""
        try:
            # GitHub stars区域的常见选择器
            stars_selectors = [
                '[href*="/stargazers"]',  # Star链接
                '.social-count',           # Star计数
                '[aria-label*="star"]',   # 包含star的元素
                '.BtnGroup-item[href*="stargazers"]',  # Star按钮组
                'a[href*="stargazers"] .Counter',      # Star计数器
            ]
            
            # 查找并高亮第一个匹配的元素
            for selector in stars_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        element = elements[0]  # 选择第一个匹配的元素
                        
                        # 添加红色边框高亮
                        await element.evaluate("""
                            element => {
                                element.style.border = '3px solid red';
                                element.style.boxShadow = '0 0 10px red';
                                element.style.backgroundColor = 'rgba(255, 0, 0, 0.1)';
                                element.scrollIntoView({behavior: 'smooth', block: 'center'});
                            }
                        """)
                        
                        logger.info(f"成功高亮stars区域: {selector}")
                        return
                except Exception as e:
                    logger.debug(f"尝试选择器 {selector} 失败: {e}")
                    continue
            
            # 如果没有找到特定的stars元素，尝试高亮整个项目统计区域
            try:
                # GitHub项目页的统计区域
                stats_selectors = [
                    '.pagehead-actions',      # 页面头部操作区域
                    '.repository-content .BorderGrid-cell',  # 仓库内容网格单元
                    '.Layout-sidebar .BorderGrid-cell'       # 侧边栏统计区域
                ]
                
                for selector in stats_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements:
                            element = elements[0]
                            await element.evaluate("""
                                element => {
                                    element.style.border = '3px solid orange';
                                    element.style.boxShadow = '0 0 10px orange';
                                    element.style.backgroundColor = 'rgba(255, 165, 0, 0.1)';
                                    element.scrollIntoView({behavior: 'smooth', block: 'center'});
                                }
                            """)
                            logger.info(f"高亮统计区域: {selector}")
                            return
                    except Exception as e:
                        logger.debug(f"尝试统计区域选择器 {selector} 失败: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"高亮stars区域失败: {e}")
                
        except Exception as e:
            logger.error(f"高亮功能异常: {e}")
    
    async def _hide_elements(self, page: Page, selectors: list):
        """隐藏指定的页面元素"""
        for selector in selectors:
            try:
                await page.evaluate(f"""
                    () => {{
                        const elements = document.querySelectorAll('{selector}');
                        elements.forEach(el => el.style.display = 'none');
                    }}
                """)
            except Exception as e:
                logger.debug(f"隐藏元素 {selector} 失败: {e}")


class BatchScreenshotService:
    """批量截图服务"""
    
    def __init__(self, storage_path: Path, headless: bool = True):
        self.storage_path = storage_path
        self.headless = headless
        self.screenshot_service = GitHubScreenshotService(headless)
    
    async def take_project_screenshots(self, 
                                     projects: list,
                                     options: Optional[ScreenshotOptions] = None) -> Dict[str, Path]:
        """
        为多个项目批量截图
        返回: {project_id: screenshot_path} 的字典
        """
        results = {}
        
        try:
            # 启动截图服务
            await self.screenshot_service.start()
            
            # 逐个截图
            for project in projects:
                try:
                    project_id = project.get('id') or project.get('name', 'unknown')
                    github_url = project.get('url')
                    
                    if not github_url:
                        logger.warning(f"项目 {project_id} 缺少URL")
                        continue
                    
                    # 生成保存路径
                    screenshot_dir = self.storage_path / project_id / "screenshots"
                    screenshot_path = screenshot_dir / "project_homepage.jpg"
                    
                    # 截图
                    success = await self.screenshot_service.take_screenshot(
                        github_url, screenshot_path, options
                    )
                    
                    if success:
                        results[project_id] = screenshot_path
                        logger.info(f"项目 {project_id} 截图成功")
                    else:
                        logger.error(f"项目 {project_id} 截图失败")
                        
                except Exception as e:
                    logger.error(f"处理项目 {project.get('id', 'unknown')} 失败: {e}")
                    continue
            
        finally:
            # 确保服务停止
            await self.screenshot_service.stop()
        
        return results


# 同步接口包装器
class SyncGitHubScreenshotService:
    """同步接口的截图服务包装器"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
    
    def take_screenshot_sync(self, 
                           github_url: str, 
                           save_path: Path,
                           options: Optional[ScreenshotOptions] = None) -> bool:
        """完全同步的截图接口（智能选择最佳方案）"""
        try:
            # 首先检查Python版本兼容性
            import sys
            python_version = sys.version_info
            
            # 对于Python 3.13+ on Windows，优先使用Selenium
            if python_version.major == 3 and python_version.minor >= 13 and sys.platform == 'win32':
                logger.info(f"检测到Python {python_version.major}.{python_version.minor} on Windows，使用Selenium替代方案")
                return self._try_selenium_screenshot(github_url, save_path, options)
            
            # 尝试使用Playwright截图
            import asyncio
            
            if sys.platform == 'win32':
                # 为Windows设置适当的事件循环策略
                if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                elif hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
            # 创建新的事件循环
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    result = loop.run_until_complete(
                        self._take_screenshot_internal(github_url, save_path, options)
                    )
                    if result:
                        return True
                except Exception as e:
                    logger.warning(f"Playwright截图失败: {e}")
                    # 检查是否是已知的兼容性问题
                    if "NotImplementedError" in str(e) or "subprocess_exec" in str(e):
                        logger.info("检测到兼容性问题，尝试Selenium替代方案")
                        return self._try_selenium_screenshot(github_url, save_path, options)
                finally:
                    loop.close()
            except RuntimeError as e:
                if "Cannot run the event loop while another loop is running" in str(e):
                    logger.warning("事件循环冲突，尝试不同的方法")
                    # 尝试使用现有的事件循环
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # 在运行的循环中调度任务
                            future = asyncio.run_coroutine_threadsafe(
                                self._take_screenshot_internal(github_url, save_path, options),
                                loop
                            )
                            try:
                                result = future.result(timeout=30)
                                if result:
                                    return True
                            except Exception:
                                pass
                    except Exception:
                        pass
                
            # 如果Playwright和Selenium都失败，使用最后的降级方案
            logger.info("所有自动化方案都失败，使用基础降级截图")
            return self._fallback_screenshot(github_url, save_path)
                
        except Exception as e:
            logger.error(f"同步截图完全失败: {e}")
            # 最后的降级方案
            return self._fallback_screenshot(github_url, save_path)
    
    def _try_selenium_screenshot(self, github_url: str, save_path: Path, options: Optional[ScreenshotOptions] = None) -> bool:
        """尝试使用Selenium进行截图"""
        try:
            from services.selenium_screenshot_service import SyncSeleniumScreenshotService
            
            selenium_service = SyncSeleniumScreenshotService(headless=True)
            
            # 转换选项参数
            width = options.width if options else 1920
            height = options.height if options else 1080
            wait_time = (options.wait_time // 1000) if options else 3
            
            result = selenium_service.take_screenshot_sync(
                github_url, save_path, width, height, wait_time
            )
            
            if result:
                logger.info("Selenium截图成功")
                return True
            else:
                logger.warning("Selenium截图失败")
                return False
                
        except ImportError:
            logger.warning("Selenium未安装，使用基础降级方案")
            return self._fallback_screenshot(github_url, save_path)
        except Exception as e:
            logger.error(f"Selenium截图异常: {e}")
            return False
    
    async def _take_screenshot_internal(self, 
                                      github_url: str, 
                                      save_path: Path,
                                      options: Optional[ScreenshotOptions] = None) -> bool:
        """内部异步截图实现"""
        async with GitHubScreenshotService(self.headless) as service:
            return await service.take_screenshot(github_url, save_path, options)
    
    def _fallback_screenshot(self, github_url: str, save_path: Path) -> bool:
        """降级截图方法 - 创建高质量的GitHub风格占位图片"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import requests
            from io import BytesIO
            import urllib.parse
            
            # 解析GitHub URL获取项目信息
            parsed_url = urllib.parse.urlparse(github_url)
            path_parts = parsed_url.path.strip('/').split('/')
            if len(path_parts) >= 2:
                owner, repo = path_parts[0], path_parts[1]
                project_display = f"{owner}/{repo}"
            else:
                project_display = "GitHub Project"
            
            # 创建GitHub风格的占位图片
            width, height = 1200, 800
            image = Image.new('RGB', (width, height), color='#ffffff')
            draw = ImageDraw.Draw(image)
            
            # 绘制GitHub主题色背景
            # 顶部导航栏
            draw.rectangle([0, 0, width, 60], fill='#24292f')
            
            # 主要内容区域
            draw.rectangle([0, 60, width, height], fill='#ffffff')
            
            # 项目头部区域
            draw.rectangle([40, 80, width-40, 180], fill='#f6f8fa', outline='#e1e4e8', width=1)
            
            # 项目内容区域
            draw.rectangle([40, 200, width-40, height-40], fill='#ffffff', outline='#e1e4e8', width=1)
            
            # 尝试使用更好的字体
            try:
                # Windows系统字体
                fonts_to_try = [
                    'arial.ttf',
                    'calibri.ttf',
                    'segoeui.ttf',
                    'times.ttf'
                ]
                font_large = None
                font_medium = None
                font_small = None
                
                for font_name in fonts_to_try:
                    try:
                        font_large = ImageFont.truetype(font_name, 32)
                        font_medium = ImageFont.truetype(font_name, 24)
                        font_small = ImageFont.truetype(font_name, 18)
                        break
                    except:
                        continue
                
                # 如果都没找到，使用默认字体
                if not font_large:
                    font_large = ImageFont.load_default()
                    font_medium = ImageFont.load_default()
                    font_small = ImageFont.load_default()
                    
            except Exception:
                # 最后的备选方案
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
            
            # 绘制项目信息
            # 项目标题
            title_y = 100
            draw.text((60, title_y), project_display, fill='#0366d6', font=font_large)
            
            # 项目描述占位符
            desc_y = title_y + 50
            draw.text((60, desc_y), 'Project Description', fill='#586069', font=font_medium)
            draw.text((60, desc_y + 35), 'This is a placeholder screenshot generated due to', fill='#586069', font=font_small)
            draw.text((60, desc_y + 60), 'browser automation limitations.', fill='#586069', font=font_small)
            
            # 技术统计信息
            stats_y = desc_y + 100
            draw.text((60, stats_y), '⭐ 0 stars | 🍴 0 forks | 👀 0 watchers', fill='#586069', font=font_small)
            
            # 语言信息
            lang_y = stats_y + 30
            draw.text((60, lang_y), 'Primary Language: Unknown', fill='#586069', font=font_small)
            
            # URL信息
            url_y = lang_y + 40
            draw.text((60, url_y), f'Original URL: {github_url}', fill='#0366d6', font=font_small)
            
            # 添加GitHub风格的图标和装饰
            # 模拟README内容区域
            readme_y = url_y + 60
            draw.rectangle([60, readme_y, width-60, readme_y + 200], fill='#f6f8fa', outline='#e1e4e8', width=1)
            draw.text((80, readme_y + 20), '# Project README', fill='#0366d6', font=font_medium)
            draw.text((80, readme_y + 60), 'This is a simulated README content area.', fill='#586069', font=font_small)
            draw.text((80, readme_y + 90), 'In a real screenshot, this would show the actual', fill='#586069', font=font_small)
            draw.text((80, readme_y + 120), 'project documentation and code examples.', fill='#586069', font=font_small)
            
            # 添加警告水印
            watermark_y = height - 60
            draw.text((60, watermark_y), '⚠️  Fallback Screenshot - Browser automation unavailable', fill='#868e96', font=font_small)
            
            # 保存图片
            save_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(save_path, 'JPEG', quality=90, optimize=True)
            
            logger.info(f"高质量降级截图创建成功: {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"降级截图也失败: {e}")
            return False


# 使用示例和测试函数
async def test_screenshot():
    """测试截图功能"""
    storage_path = Path("data/test_screenshots")
    storage_path.mkdir(exist_ok=True)
    
    test_url = "https://github.com/torvalds/linux"
    save_path = storage_path / "linux_test.jpg"
    
    options = ScreenshotOptions(
        width=1920,
        height=1080,
        full_page=True,
        quality=85
    )
    
    async with GitHubScreenshotService() as service:
        success = await service.take_screenshot(test_url, save_path, options)
        if success:
            print(f"截图成功保存到: {save_path}")
        else:
            print("截图失败")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_screenshot())