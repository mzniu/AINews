"""对比 requests 和 Playwright 抓取到的图片差异"""
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urljoin

url = 'https://www.qbitai.com/2026/02/377824.html'

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=15000)
        except:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
        
        html = await page.content()
        await browser.close()
    
    soup = BeautifulSoup(html, 'lxml')
    imgs = soup.find_all('img')
    print(f"Playwright 找到 {len(imgs)} 张图片\n")
    
    for i, img in enumerate(imgs[:15]):
        src = img.get('src', '')
        data_src = img.get('data-src', '')
        data_original = img.get('data-original', '')
        cls = ' '.join(img.get('class', []))
        print(f"[{i+1}] class={cls}")
        print(f"  src         = {src[:200]}")
        if data_src:
            print(f"  data-src    = {data_src[:200]}")
        if data_original:
            print(f"  data-original = {data_original[:200]}")
        
        # 检查src是否是data URI或空
        if src.startswith('data:'):
            print(f"  *** 这是 data URI (占位图)! 真实URL可能在data-src ***")
        elif not src:
            print(f"  *** src为空! ***")
        print()

asyncio.run(main())
