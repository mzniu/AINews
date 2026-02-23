"""
GitHub项目解析工具
负责解析GitHub项目信息、README内容和图片链接
"""
import re
import requests
from typing import List, Tuple, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from loguru import logger
from src.models.github_models import GitHubProjectBase, ProjectImage
from datetime import datetime


class GitHubUrlParser:
    """GitHub URL解析器"""
    
    @staticmethod
    def parse_github_url(url: str) -> dict:
        """
        解析GitHub URL，提取owner和repo信息
        支持多种URL格式:
        - https://github.com/owner/repo
        - https://github.com/owner/repo/
        - https://github.com/owner/repo.git
        """
        parsed = urlparse(url.rstrip('/'))
        if parsed.netloc != 'github.com':
            raise ValueError("不是有效的GitHub URL")
        
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) < 2:
            raise ValueError("URL格式不正确，应包含owner/repo")
        
        owner = path_parts[0]
        repo = path_parts[1].replace('.git', '')
        
        return {
            'owner': owner,
            'repo': repo,
            'full_url': f"https://github.com/{owner}/{repo}",
            'api_url': f"https://api.github.com/repos/{owner}/{repo}",
            'raw_url': f"https://raw.githubusercontent.com/{owner}/{repo}"
        }


class GitHubAPIClient:
    """GitHub API客户端"""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'AINews-GitHub-Parser'
        }
        if token:
            self.headers['Authorization'] = f'token {token}'
    
    def get_repo_info(self, owner: str, repo: str) -> dict:
        """获取仓库基本信息"""
        url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"获取仓库信息失败: {e}")
            raise
    
    def get_readme(self, owner: str, repo: str, branch: str = 'main') -> Tuple[str, str]:
        """
        获取README内容
        返回: (原始markdown内容, HTML内容)
        """
        # 尝试不同的README文件名
        readme_names = ['README.md', 'readme.md', 'Readme.md']
        
        for readme_name in readme_names:
            try:
                # 先尝试获取README文件信息
                contents_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{readme_name}?ref={branch}"
                response = requests.get(contents_url, headers=self.headers, timeout=10)
                
                if response.status_code == 200:
                    # 获取原始README内容
                    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{readme_name}"
                    raw_response = requests.get(raw_url, timeout=10)
                    raw_response.raise_for_status()
                    
                    # 获取HTML渲染版本
                    html_url = f"https://api.github.com/markdown"
                    html_response = requests.post(
                        html_url,
                        json={
                            "text": raw_response.text,
                            "mode": "gfm",
                            "context": f"{owner}/{repo}"
                        },
                        headers=self.headers,
                        timeout=10
                    )
                    
                    html_content = html_response.text if html_response.status_code == 200 else ""
                    
                    return raw_response.text, html_content
                    
            except requests.RequestException as e:
                logger.debug(f"尝试 {readme_name} 失败: {e}")
                continue
        
        raise FileNotFoundError("未找到README文件")


class ReadmeImageExtractor:
    """README图片提取器"""
    
    def __init__(self, base_url: str, owner: str, repo: str, branch: str = 'main'):
        self.base_url = base_url
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.raw_base_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
    
    def extract_images_from_markdown(self, markdown_content: str) -> List[ProjectImage]:
        """从Markdown内容中提取图片链接"""
        images = []
        
        # 1. 匹配Markdown图片语法: ![alt](url) 或 ![alt](url "title")
        md_pattern = r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)'
        md_matches = re.finditer(md_pattern, markdown_content)
        
        for i, match in enumerate(md_matches):
            alt_text = match.group(1) or ""
            image_url = match.group(2)
            title = match.group(3) or ""
            
            # 处理相对路径和绝对路径
            full_url = self._resolve_image_url(image_url)
            
            if full_url:
                image = ProjectImage(
                    id=f"img_md_{i:03d}",
                    url=full_url,
                    source="readme",
                    alt_text=alt_text or title
                )
                images.append(image)
        
        # 2. 匹配HTML img标签
        html_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        html_matches = re.finditer(html_pattern, markdown_content, re.IGNORECASE)
        
        for i, match in enumerate(html_matches):
            image_url = match.group(1)
            
            # 提取alt属性（如果存在）
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', match.group(0), re.IGNORECASE)
            alt_text = alt_match.group(1) if alt_match else ""
            
            # 处理相对路径和绝对路径
            full_url = self._resolve_image_url(image_url)
            
            if full_url:
                image = ProjectImage(
                    id=f"img_html_{i:03d}",
                    url=full_url,
                    source="readme",
                    alt_text=alt_text
                )
                images.append(image)
        
        return images
    
    def _resolve_image_url(self, url: str) -> Optional[str]:
        """解析并补全图片URL"""
        # 如果已经是完整URL
        if url.startswith(('http://', 'https://')):
            return url
        
        # 处理相对路径
        if url.startswith('./'):
            url = url[2:]
        elif url.startswith('../'):
            # 简单处理上级目录（实际项目中可能需要更复杂的逻辑）
            url = url[3:]
        
        # 构建完整的原始文件URL
        return f"{self.raw_base_url}/{url.lstrip('/')}"


class GitHubProjectParser:
    """GitHub项目解析主类"""
    
    def __init__(self, github_token: Optional[str] = None):
        self.api_client = GitHubAPIClient(github_token)
    
    def parse_project(self, github_url: str) -> GitHubProjectBase:
        """解析完整的GitHub项目信息"""
        # 解析URL
        url_info = GitHubUrlParser.parse_github_url(github_url)
        
        # 获取仓库信息
        repo_data = self.api_client.get_repo_info(
            url_info['owner'], 
            url_info['repo']
        )
        
        # 创建项目基础信息对象
        project = GitHubProjectBase(
            id=f"{url_info['owner']}_{url_info['repo']}",
            url=url_info['full_url'],
            name=repo_data['name'],
            full_name=repo_data['full_name'],
            description=repo_data.get('description'),
            language=repo_data.get('language'),
            stars=repo_data.get('stargazers_count', 0),
            forks=repo_data.get('forks_count', 0),
            watchers=repo_data.get('watchers_count', 0),
            created_at=datetime.fromisoformat(repo_data['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(repo_data['updated_at'].replace('Z', '+00:00')),
            owner=url_info['owner'],
            default_branch=repo_data.get('default_branch', 'main')
        )
        
        return project
    
    def extract_readme_images(self, github_url: str, markdown_content: str) -> List[ProjectImage]:
        """提取README中的图片"""
        url_info = GitHubUrlParser.parse_github_url(github_url)
        
        extractor = ReadmeImageExtractor(
            github_url,
            url_info['owner'],
            url_info['repo'],
            'main'  # 默认分支
        )
        
        return extractor.extract_images_from_markdown(markdown_content)