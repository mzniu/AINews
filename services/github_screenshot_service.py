"""
GitHub项目主页截图服务
使用Playwright进行网页渲染和截图
"""
import asyncio
import concurrent.futures
import os
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, Page
from loguru import logger


def _env_allow_fallback_screenshot() -> bool:
    """是否允许在浏览器自动化失败时仍写入 PIL 占位图（默认否，避免误判为截图成功）。"""
    v = os.environ.get("GITHUB_SCREENSHOT_ALLOW_FALLBACK", "").strip().lower()
    return v in ("1", "true", "yes")


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
            'header[role="banner"]',
            '.Header',
            'div[data-hpc="true"]',
            '.footer',
            '.Footer',
        ])
        # 整页缩放，略大于 1 可使正文更易读（与浏览器 Ctrl+ 类似）
        self.font_scale = float(kwargs.get('font_scale', 1.12))


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
                    '--disable-web-security',
                    # 避免无头模式按深色主题渲染网页（GitHub 等会整页黑底）
                    '--disable-features=WebContentsForceDark',
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
            
            # 独立上下文：强制浅色模式（否则 headless 常出 GitHub 深色/黑底）
            context = await self.browser.new_context(
                color_scheme="light",
                viewport={"width": options.width, "height": options.height},
            )
            page = await context.new_page()
            try:
                await page.emulate_media(color_scheme="light")

                # 访问GitHub页面
                logger.info(f"正在访问: {github_url}")
                await page.goto(github_url, wait_until="networkidle", timeout=options.timeout)

                # 等待页面加载
                await page.wait_for_timeout(options.wait_time)

                # GitHub：再写一次根节点属性，避免仍按 dark 渲染
                await page.evaluate(
                    """() => {
                  const root = document.documentElement;
                  root.setAttribute('data-color-mode', 'light');
                  root.style.colorScheme = 'light';
                  try { root.classList.remove('dark'); } catch (e) {}
                }"""
                )

                # 高亮显示stars区域
                await self._highlight_stars_area(page)

                # 隐藏不需要的元素
                await self._hide_elements(page, options.hide_elements)

                # 滚动到顶部确保一致性
                await page.evaluate("window.scrollTo(0, 0)")

                # 略放大整页（含文字），便于成片里阅读
                fs = max(1.0, min(1.35, float(getattr(options, "font_scale", 1.12))))
                await page.evaluate(
                    "(z) => { document.documentElement.style.zoom = String(z); }", fs
                )

                # 截图
                screenshot_kwargs = {
                    "path": str(save_path),
                    "full_page": options.full_page,
                    "quality": options.quality,
                    "type": "jpeg",
                }

                await page.screenshot(**screenshot_kwargs)
            finally:
                await context.close()

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

    def _run_playwright_in_thread(
        self,
        github_url: str,
        save_path: Path,
        options: Optional[ScreenshotOptions] = None,
        *,
        timeout_sec: float = 180.0,
    ) -> bool:
        """
        在独立线程中用 asyncio.run() 执行 Playwright。
        解决 FastAPI 等场景下主线程已有运行中的事件循环时，
        run_until_complete / asyncio.run 报错「Cannot run the event loop while another loop is running」。
        """
        import sys

        def runner() -> bool:
            if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            try:
                return asyncio.run(
                    self._take_screenshot_internal(github_url, save_path, options)
                )
            except Exception as e:
                logger.warning(f"Playwright截图失败: {e}")
                return False

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(runner)
                return bool(fut.result(timeout=timeout_sec))
        except concurrent.futures.TimeoutError:
            logger.warning(f"Playwright截图超时（{timeout_sec}s）")
            return False
        except Exception as e:
            logger.warning(f"Playwright线程执行失败: {e}")
            return False
    
    def take_screenshot_sync(self, 
                           github_url: str, 
                           save_path: Path,
                           options: Optional[ScreenshotOptions] = None) -> bool:
        """
        完全同步的截图接口（Playwright → Selenium，按平台分支）。
        仅当真实浏览器截图成功时返回 True。
        自动化失败时默认不把 PIL 占位图当作成功；需要占位图可设 GITHUB_SCREENSHOT_ALLOW_FALLBACK=1。
        """
        try:
            import sys
            python_version = sys.version_info
            
            # Python 3.13+ Windows：历史上优先 Selenium；若 Chrome/驱动不可用则回退 Playwright
            if python_version.major == 3 and python_version.minor >= 13 and sys.platform == 'win32':
                logger.info(
                    f"检测到 Python {python_version.major}.{python_version.minor} on Windows，先尝试 Selenium"
                )
                if self._try_selenium_screenshot(github_url, save_path, options):
                    return True
                logger.warning(
                    "Selenium 截图不可用（Chrome/Chromedriver 或网络问题），回退尝试 Playwright"
                )
            
            if self._run_playwright_in_thread(github_url, save_path, options):
                return True

            # 非 Windows 3.13 路径：Playwright 失败后再尝试 Selenium（兼容性问题等）
            if not (python_version.major == 3 and python_version.minor >= 13 and sys.platform == 'win32'):
                if self._try_selenium_screenshot(github_url, save_path, options):
                    return True
                
            return self._finish_with_optional_fallback(
                github_url,
                save_path,
                "Playwright 与 Selenium 均未成功截取真实页面",
            )
                
        except Exception as e:
            logger.error(f"同步截图完全失败: {e}")
            return self._finish_with_optional_fallback(
                github_url,
                save_path,
                f"同步截图异常: {e}",
            )
    
    def _try_selenium_screenshot(self, github_url: str, save_path: Path, options: Optional[ScreenshotOptions] = None) -> bool:
        """尝试使用Selenium进行截图"""
        try:
            from services.selenium_screenshot_service import SyncSeleniumScreenshotService
            
            selenium_service = SyncSeleniumScreenshotService(headless=True)
            
            # 转换选项参数
            width = options.width if options else 1920
            height = options.height if options else 1080
            wait_time = (options.wait_time // 1000) if options else 3
            
            fs = float(getattr(options, "font_scale", 1.12)) if options else 1.12
            result = selenium_service.take_screenshot_sync(
                github_url, save_path, width, height, wait_time, font_scale=fs
            )
            
            if result:
                logger.info("Selenium截图成功")
                return True
            else:
                logger.warning("Selenium截图失败")
                return False
                
        except ImportError:
            logger.warning("Selenium 未安装")
            return self._finish_with_optional_fallback(
                github_url,
                save_path,
                "Selenium 未安装",
            )
        except Exception as e:
            logger.error(f"Selenium截图异常: {e}")
            return False
    
    def _finish_with_optional_fallback(
        self, github_url: str, save_path: Path, reason: str
    ) -> bool:
        """
        自动化失败时的收尾：默认返回 False；仅当 GITHUB_SCREENSHOT_ALLOW_FALLBACK=1 时写入占位图并返回 True。
        """
        if _env_allow_fallback_screenshot():
            logger.warning(f"{reason}；已设置 GITHUB_SCREENSHOT_ALLOW_FALLBACK，写入占位图")
            return self._fallback_screenshot(github_url, save_path)
        logger.error(
            f"{reason}。未写入占位图（避免误判为截图成功）。"
            "若界面仍见「Fallback / placeholder」字样，多为历史生成的占位文件，可删除后重试「重新获取主页截图」。"
            "请安装 Playwright 浏览器：在项目目录执行 `playwright install chromium`，并确保可访问 GitHub。"
        )
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