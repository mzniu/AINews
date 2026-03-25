#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动内容处理API - 处理用户直接粘贴的文章内容
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Optional
from bs4 import BeautifulSoup
from loguru import logger
import re
from datetime import datetime

router = APIRouter(prefix="/api", tags=["手动内容处理"])

@router.post("/process-manual-content")
async def process_manual_content(data: Dict):
    """
    处理用户手动粘贴的内容（HTML 源码或纯文本）
    
    Args:
        data: 包含 content 和可选 url 的字典
    
    Returns:
        dict: 处理后的内容、标题、图片等
    """
    try:
        content = data.get('content', '')
        url = data.get('url', '')
        
        if not content:
            raise HTTPException(status_code=400, detail="内容不能为空")
        
        logger.info(f"收到手动内容处理请求，内容长度：{len(content)}")
        
        # 判断是 HTML 还是纯文本
        is_html = '<' in content and '>' in content
        
        if is_html:
            logger.info("检测到 HTML 格式，使用 BeautifulSoup 解析")
            result = process_html_content(content, url)
        else:
            logger.info("检测到纯文本格式")
            result = process_text_content(content, url)
        
        # 添加时间戳
        result['timestamp'] = datetime.now().isoformat()
        result['success'] = True
        
        logger.success(f"手动内容处理成功：{result.get('title', '无标题')}")
        
        return result
        
    except Exception as e:
        logger.error(f"手动内容处理失败：{e}")
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)}")

def process_html_content(html: str, base_url: str = "") -> Dict:
    """
    处理 HTML 内容
    
    Args:
        html: HTML 源码
        base_url: 原始 URL（用于处理相对路径）
    
    Returns:
        dict: 处理结果
    """
    try:
        from urllib.parse import urljoin
        
        soup = BeautifulSoup(html, 'lxml')
        
        # 移除干扰元素
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
            tag.decompose()
        
        # 提取标题
        title = extract_title(soup)
        
        # 提取主要内容
        content_text = extract_main_content(soup)
        
        # 提取图片
        images = extract_images(soup, base_url)
        
        # 提取视频
        videos = extract_videos(soup, base_url)
        
        # 清理内容（去除多余空白）
        content_text = clean_content(content_text)
        
        logger.info(f"HTML 内容提取完成：标题={title}, 内容长度={len(content_text)}, 图片数={len(images)}")
        
        return {
            'title': title or "未命名文章",
            'content': content_text,
            'images': images,
            'videos': videos,
            'source_url': base_url,
            'content_type': 'html'
        }
        
    except Exception as e:
        logger.error(f"HTML 内容处理失败：{e}")
        return {
            'title': "处理失败",
            'content': "",
            'images': [],
            'videos': [],
            'error': str(e)
        }

def process_text_content(text: str, base_url: str = "") -> Dict:
    """
    处理纯文本内容
    
    Args:
        text: 纯文本
        base_url: 原始 URL
    
    Returns:
        dict: 处理结果
    """
    try:
        # 尝试从文本中提取可能的标题（第一行或前 50 个字符）
        lines = text.strip().split('\n')
        title = lines[0].strip() if lines else "未命名文章"
        
        # 限制标题长度
        if len(title) > 200:
            title = title[:200] + "..."
        
        # 内容就是原文本
        content = text.strip()
        
        # 尝试从文本中提取 URL（如果有）
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
        image_urls = [url for url in urls if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])]
        
        images = [{'url': url, 'filename': url.split('/')[-1]} for url in image_urls[:20]]
        
        logger.info(f"文本内容提取完成：标题={title}, 内容长度={len(content)}, 图片数={len(images)}")
        
        return {
            'title': title,
            'content': content,
            'images': images,
            'videos': [],
            'source_url': base_url,
            'content_type': 'text'
        }
        
    except Exception as e:
        logger.error(f"文本内容处理失败：{e}")
        return {
            'title': "处理失败",
            'content': "",
            'images': [],
            'videos': [],
            'error': str(e)
        }

def extract_title(soup: BeautifulSoup) -> str:
    """从 HTML 中提取标题"""
    # 尝试不同的标题选择器
    title_selectors = [
        'h1', 
        '.article-title', 
        '.post-title', 
        '[class*="title"]',
        'title'
    ]
    
    for selector in title_selectors:
        element = soup.select_one(selector)
        if element:
            title = element.get_text(strip=True)
            if title and len(title) > 5:
                return title
    
    # 最后尝试<title>标签
    title_tag = soup.find('title')
    if title_tag:
        return title_tag.get_text(strip=True)
    
    return ""

def extract_main_content(soup: BeautifulSoup) -> str:
    """提取主要内容文本"""
    content_selectors = [
        'article',
        '.article-content',
        '.post-content',
        '.content',
        '[class*="article"]',
        '[id*="content"]',
        'main',
        '.main-content'
    ]
    
    content_text = ""
    for selector in content_selectors:
        elements = soup.select(selector)
        if elements:
            content_text = elements[0].get_text(separator='\n', strip=True)
            if len(content_text) > 200:
                break
    
    # 如果没找到足够内容，尝试 body
    if len(content_text) < 200:
        body = soup.find('body')
        if body:
            content_text = body.get_text(separator='\n', strip=True)
    
    return content_text

def extract_images(soup: BeautifulSoup, base_url: str) -> list:
    """提取图片"""
    from urllib.parse import urljoin
    
    images = []
    
    # 查找所有 img 标签
    img_tags = soup.find_all('img')
    
    for img in img_tags:
        # 获取图片 URL（尝试多个属性）
        src = img.get('src') or img.get('data-src') or img.get('data-original') or img.get('data-lazy-src')
        
        if src and not src.startswith('data:'):  # 排除 base64
            # 处理相对路径
            full_url = urljoin(base_url, src) if base_url else src
            
            # 添加到列表
            images.append({
                'url': full_url,
                'alt': img.get('alt', ''),
                'filename': full_url.split('/')[-1].split('?')[0]
            })
    
    # 去重（根据 URL）
    seen_urls = set()
    unique_images = []
    for img in images:
        if img['url'] not in seen_urls:
            seen_urls.add(img['url'])
            unique_images.append(img)
    
    return unique_images[:50]  # 限制最多 50 张图片

def extract_videos(soup: BeautifulSoup, base_url: str) -> list:
    """提取视频"""
    from urllib.parse import urljoin
    
    videos = []
    
    # 查找 video 标签
    video_tags = soup.find_all('video')
    for video in video_tags:
        src = video.get('src')
        if src:
            full_url = urljoin(base_url, src) if base_url else src
            videos.append({
                'url': full_url,
                'type': 'video'
            })
    
    # 查找 iframe（可能嵌入视频）
    iframe_tags = soup.find_all('iframe')
    for iframe in iframe_tags:
        src = iframe.get('src')
        if src and any(site in src for site in ['youtube', 'vimeo', 'bilibili', 'youku']):
            videos.append({
                'url': src,
                'type': 'embedded'
            })
    
    return videos[:10]  # 限制最多 10 个视频

def clean_content(text: str) -> str:
    """清理内容文本"""
    # 去除过多的空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 去除每行前后的空格
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    return text.strip()

# 导出路由
manual_content_router = router