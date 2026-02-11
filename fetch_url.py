"""
通用网页内容抓取工具
使用方法: python fetch_url.py <URL>
"""
import sys
import os
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from loguru import logger

# 配置日志
logger.add("logs/fetch_url_{time}.log", rotation="10 MB")


def get_page_content(url: str) -> tuple[str, str]:
    """使用Playwright获取页面HTML和标题"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle', timeout=30000)
            
            title = page.title()
            html = page.content()
            
            browser.close()
            logger.success(f"成功获取页面: {title}")
            return html, title
    except Exception as e:
        logger.error(f"获取页面失败: {e}")
        raise


def extract_content(html: str, base_url: str) -> dict:
    """提取页面内容和图片"""
    soup = BeautifulSoup(html, 'lxml')
    
    # 移除脚本和样式标签
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    
    # 提取正文（尝试多种选择器）
    content_selectors = [
        'article',
        '[class*="content"]',
        '[class*="article"]',
        '[class*="post"]',
        '[id*="content"]',
        'main',
        '.main-content',
        'body'
    ]
    
    content_text = ""
    for selector in content_selectors:
        elements = soup.select(selector)
        if elements:
            content_text = elements[0].get_text(separator='\n', strip=True)
            if len(content_text) > 200:  # 至少200字才算有效内容
                logger.info(f"使用选择器提取内容: {selector}")
                break
    
    # 提取图片（根据网站类型采用不同策略）
    images = []
    
    # 检查是否为qbitai网站
    parsed_url = urlparse(base_url)
    is_qbitai = 'qbitai.com' in parsed_url.netloc
    
    if is_qbitai:
        # 提取具有syl-page-img类和pgc-img类的图片
        logger.info("检测到qbitai网站，提取syl-page-img和pgc-img类的图片")
        
        # 提取syl-page-img类图片
        syl_img_elements = soup.find_all('img', class_='syl-page-img')
        for img in syl_img_elements:
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if src:
                # 转换为绝对URL
                absolute_url = urljoin(base_url, src)
                images.append({
                    'url': absolute_url,
                    'alt': img.get('alt', ''),
                    'width': img.get('width'),
                    'height': img.get('height'),
                    'class': 'syl-page-img'
                })
        
        # 提取pgc-img类图片（在pgc-img div容器内）
        pgc_containers = soup.find_all('div', class_='pgc-img')
        for container in pgc_containers:
            img = container.find('img')
            if img:
                src = img.get('src') or img.get('data-src') or img.get('data-original')
                if src:
                    # 转换为绝对URL
                    absolute_url = urljoin(base_url, src)
                    images.append({
                        'url': absolute_url,
                        'alt': img.get('alt', ''),
                        'width': img.get('width'),
                        'height': img.get('height'),
                        'class': 'pgc-img'
                    })
        
        logger.info(f"qbitai网站提取完成: syl-page-img {len(syl_img_elements)}张, pgc-img {len(pgc_containers)}张")
    else:
        # 其他网站提取所有图片
        logger.info("提取页面所有图片")
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if src:
                # 转换为绝对URL
                absolute_url = urljoin(base_url, src)
                images.append({
                    'url': absolute_url,
                    'alt': img.get('alt', ''),
                    'width': img.get('width'),
                    'height': img.get('height')
                })
    
    logger.info(f"提取到 {len(images)} 张图片 (qbitai模式: {is_qbitai})")
    
    return {
        'content': content_text,
        'images': images
    }


def download_image(image_url: str, save_dir: Path, index: int) -> str:
    """下载单张图片"""
    try:
        # 生成文件名
        parsed = urlparse(image_url)
        ext = Path(parsed.path).suffix or '.jpg'
        filename = f"image_{index:03d}{ext}"
        filepath = save_dir / filename
        
        # 下载图片
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 保存图片
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        logger.success(f"下载图片: {filename}")
        return str(filepath)
    except Exception as e:
        logger.warning(f"下载图片失败 {image_url}: {e}")
        return ""


def save_results(url: str, title: str, content: str, images: list, output_dir: Path):
    """保存抓取结果"""
    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    save_dir = output_dir / f"{url_hash}_{timestamp}"
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建图片子目录
    images_dir = save_dir / "images"
    images_dir.mkdir(exist_ok=True)
    
    # 下载所有图片
    downloaded_images = []
    for i, img in enumerate(images, 1):
        local_path = download_image(img['url'], images_dir, i)
        if local_path:
            downloaded_images.append({
                'url': img['url'],
                'local_path': local_path,
                'alt': img['alt']
            })
    
    # 保存内容为文本文件
    content_file = save_dir / "content.txt"
    with open(content_file, 'w', encoding='utf-8') as f:
        f.write(f"标题: {title}\n")
        f.write(f"URL: {url}\n")
        f.write(f"抓取时间: {datetime.now().isoformat()}\n")
        f.write(f"\n{'='*80}\n\n")
        f.write(content)
    
    # 保存元数据为JSON
    metadata = {
        'url': url,
        'title': title,
        'crawl_time': datetime.now().isoformat(),
        'content_length': len(content),
        'images_count': len(downloaded_images),
        'images': downloaded_images
    }
    
    metadata_file = save_dir / "metadata.json"
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    logger.success(f"保存完成! 目录: {save_dir}")
    logger.info(f"- 内容文件: {content_file}")
    logger.info(f"- 元数据: {metadata_file}")
    logger.info(f"- 图片数量: {len(downloaded_images)}")
    
    return save_dir


def main():
    if len(sys.argv) < 2:
        print("使用方法: python fetch_url.py <URL>")
        print("示例: python fetch_url.py https://www.36kr.com/p/123456")
        sys.exit(1)
    
    url = sys.argv[1]
    
    # 验证URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        logger.error(f"无效的URL: {url}")
        sys.exit(1)
    
    logger.info(f"开始抓取: {url}")
    
    try:
        # 1. 获取页面
        html, title = get_page_content(url)
        
        # 2. 提取内容
        result = extract_content(html, url)
        
        # 3. 保存结果
        output_dir = Path("data/fetched")
        save_dir = save_results(
            url, 
            title, 
            result['content'], 
            result['images'],
            output_dir
        )
        
        print(f"\n✅ 抓取成功!")
        print(f"📁 保存位置: {save_dir}")
        print(f"📄 内容长度: {len(result['content'])} 字符")
        print(f"🖼️  图片数量: {len(result['images'])} 张")
        
    except Exception as e:
        logger.error(f"抓取失败: {e}")
        print(f"\n❌ 抓取失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
