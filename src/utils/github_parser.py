"""
GitHub项目解析工具
负责解析GitHub项目信息、README内容和图片链接
"""
import base64
import re
import requests
from typing import List, Tuple, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from loguru import logger
from src.models.github_models import GitHubProjectBase, ProjectImage, ProjectVideo
from datetime import datetime
from utils.github_mirror import mirror_github_api_url, mirror_github_raw_url


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
        url = mirror_github_api_url(f"https://api.github.com/repos/{owner}/{repo}")
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"获取仓库信息失败: {e}")
            raise
    
    def get_readme(self, owner: str, repo: str, branch: str = 'main') -> Tuple[str, str]:
        """
        获取 README 内容。
        优先使用 GitHub 官方 GET /repos/{owner}/{repo}/readme，可识别 README.md / .rst / .txt 等根目录说明文件。
        返回: (原始文本, HTML 渲染内容)
        """
        readme_api = mirror_github_api_url(
            f"https://api.github.com/repos/{owner}/{repo}/readme"
        )
        params = {'ref': branch} if branch else {}

        try:
            response = requests.get(
                readme_api, headers=self.headers, params=params, timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                raw_text = None
                # 优先解析 API 自带的 base64，避免再请求 raw.githubusercontent.com（部分网络不可用）
                if data.get('content') and data.get('encoding') == 'base64':
                    b64 = data['content'].replace('\n', '')
                    raw_text = base64.b64decode(b64).decode('utf-8', errors='replace')
                elif data.get('download_url'):
                    raw_resp = requests.get(
                        mirror_github_raw_url(data['download_url']),
                        headers=self.headers,
                        timeout=15,
                    )
                    raw_resp.raise_for_status()
                    raw_text = raw_resp.text

                if raw_text is not None:
                    html_response = requests.post(
                        mirror_github_api_url('https://api.github.com/markdown'),
                        json={
                            'text': raw_text,
                            'mode': 'gfm',
                            'context': f'{owner}/{repo}',
                        },
                        headers=self.headers,
                        timeout=15,
                    )
                    html_content = html_response.text if html_response.status_code == 200 else ''
                    logger.info(
                        f"已通过 /readme 接口获取说明文件: {data.get('name', 'README')}"
                    )
                    return raw_text, html_content

            if response.status_code not in (200, 404):
                logger.warning(
                    f'GET /readme 返回 {response.status_code}，尝试按文件名回退: {response.text[:200]}'
                )
        except requests.RequestException as e:
            logger.warning(f'GET /readme 请求异常，回退按路径查找: {e}')

        # 回退：按常见文件名请求 Contents API（含 .rst / .txt）
        readme_names = [
            'README.md', 'readme.md', 'Readme.md',
            'README.rst', 'readme.rst',
            'README.txt', 'README',
        ]
        for readme_name in readme_names:
            try:
                contents_url = mirror_github_api_url(
                    f'https://api.github.com/repos/{owner}/{repo}/contents/{readme_name}'
                )
                response = requests.get(
                    contents_url,
                    headers=self.headers,
                    params={'ref': branch},
                    timeout=15,
                )
                if response.status_code != 200:
                    continue

                data = response.json()
                if isinstance(data, dict) and data.get('encoding') == 'base64' and data.get('content'):
                    b64 = data['content'].replace('\n', '')
                    raw_text = base64.b64decode(b64).decode('utf-8', errors='replace')
                else:
                    raw_url = mirror_github_raw_url(
                        f'https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{readme_name}'
                    )
                    raw_response = requests.get(
                        raw_url, headers=self.headers, timeout=15
                    )
                    raw_response.raise_for_status()
                    raw_text = raw_response.text

                html_response = requests.post(
                    mirror_github_api_url('https://api.github.com/markdown'),
                    json={
                        'text': raw_text,
                        'mode': 'gfm',
                        'context': f'{owner}/{repo}',
                    },
                    headers=self.headers,
                    timeout=15,
                )
                html_content = html_response.text if html_response.status_code == 200 else ''
                logger.info(f'已通过 Contents 回退获取 README: {readme_name}')
                return raw_text, html_content
            except requests.RequestException as e:
                logger.debug(f'尝试 {readme_name} 失败: {e}')
                continue

        raise FileNotFoundError('未找到README文件')


class ReadmeImageExtractor:
    """README图片提取器"""
    
    def __init__(self, base_url: str, owner: str, repo: str, branch: str = 'main'):
        self.base_url = base_url
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.raw_base_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
    
    def extract_images_from_markdown(
        self,
        markdown_content: str,
        readme_html: Optional[str] = None,
    ) -> List[ProjectImage]:
        """从Markdown内容中提取图片链接"""
        images: List[ProjectImage] = []
        seen: set[str] = set()

        def push_image(prefix: str, image_url: str, alt_text: str = "") -> None:
            image_url = (image_url or "").strip()
            if not image_url:
                return

            full_url = self._resolve_image_url(image_url)
            if not full_url or full_url in seen:
                return

            seen.add(full_url)
            images.append(
                ProjectImage(
                    id=f"{prefix}_{len(images):03d}",
                    url=full_url,
                    source="readme",
                    alt_text=(alt_text or "").strip(),
                )
            )
        
        # 1. 匹配Markdown图片语法: ![alt](url) 或 ![alt](url "title")
        md_pattern = r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)'
        md_matches = re.finditer(md_pattern, markdown_content)
        
        for match in md_matches:
            alt_text = match.group(1) or ""
            image_url = match.group(2)
            title = match.group(3) or ""
            push_image("img_md", image_url, alt_text or title)
        
        # 2. 用 HTML 解析器提取 README 中的 <img>，覆盖 table/td/a/img 等复杂结构。
        for fragment in (markdown_content or "", readme_html or ""):
            if not fragment:
                continue
            try:
                soup = BeautifulSoup(fragment, "html.parser")
                for img in soup.find_all("img"):
                    image_url = (
                        img.get("data-canonical-src")
                        or img.get("src")
                        or img.get("data-src")
                        or ""
                    )
                    alt_text = (
                        img.get("alt")
                        or img.get("title")
                        or img.get("aria-label")
                        or ""
                    )
                    if not alt_text:
                        parent_cell = img.find_parent(["td", "th", "figure"])
                        if parent_cell:
                            label = parent_cell.find(["sub", "figcaption", "b", "strong"])
                            alt_text = label.get_text(" ", strip=True) if label else ""
                    push_image("img_html", image_url, alt_text)
            except Exception as e:
                logger.debug(f"BeautifulSoup 解析 README 图片片段失败: {e}")

            # 兜底：未闭合或畸形 img 标签
            html_pattern = r'<img[^>]+(?:src|data-canonical-src|data-src)=["\']([^"\']+)["\'][^>]*>'
            html_matches = re.finditer(html_pattern, fragment, re.IGNORECASE)
            for match in html_matches:
                alt_match = re.search(
                    r'alt=["\']([^"\']*)["\']', match.group(0), re.IGNORECASE
                )
                alt_text = alt_match.group(1) if alt_match else ""
                push_image("img_html", match.group(1), alt_text)
        
        return images
    
    def _resolve_image_url(self, url: str) -> Optional[str]:
        """解析并补全图片URL"""
        # 如果已经是完整URL
        if url.startswith(('http://', 'https://')):
            return mirror_github_raw_url(url)

        # 处理相对路径
        if url.startswith('./'):
            url = url[2:]
        elif url.startswith('../'):
            # 简单处理上级目录（实际项目中可能需要更复杂的逻辑）
            url = url[3:]

        # 构建完整的原始文件URL（可选走 raw 镜像）
        built = f"{self.raw_base_url}/{url.lstrip('/')}"
        return mirror_github_raw_url(built)

    def _resolve_video_url(self, url: str) -> Optional[str]:
        """与图片相同：补全相对路径；绝对 URL 走镜像。"""
        return self._resolve_image_url(url)

    def extract_videos_from_readme(
        self,
        markdown_content: str,
        readme_html: Optional[str] = None,
    ) -> List[ProjectVideo]:
        """
        从 README 原文与可选的渲染 HTML 中提取 <video> / <source> 的地址。
        GitHub 上常见：`<video src="https://private-user-images...mp4?jwt=...">`
        """
        seen: set = set()
        collected: List[ProjectVideo] = []
        idx = 0

        def push_url(raw: str, alt: Optional[str]) -> None:
            nonlocal idx
            raw = (raw or "").strip()
            if not raw:
                return
            full = self._resolve_video_url(raw)
            if not full or full in seen:
                return
            seen.add(full)
            collected.append(
                ProjectVideo(
                    id=f"vid_html_{idx:03d}",
                    url=full,
                    source="readme",
                    alt_text=alt,
                )
            )
            idx += 1

        for fragment in (markdown_content or "", readme_html or ""):
            if not fragment:
                continue
            try:
                soup = BeautifulSoup(fragment, "html.parser")
                for video in soup.find_all("video"):
                    u = (video.get("src") or video.get("data-canonical-src") or "").strip()
                    if not u:
                        for src in video.find_all("source"):
                            u = (src.get("src") or "").strip()
                            if u:
                                break
                    alt = (video.get("aria-label") or video.get("title") or "").strip() or None
                    push_url(u, alt)
            except Exception as e:
                logger.debug(f"BeautifulSoup 解析 video 片段失败: {e}")

            # 兜底：未闭合或畸形标签
            for m in re.finditer(
                r"<video[^>]+(?:src|data-canonical-src)=[\"']([^\"']+)[\"']",
                fragment,
                re.IGNORECASE,
            ):
                push_url(m.group(1), None)

        return collected


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
    
    def extract_readme_images(
        self,
        github_url: str,
        markdown_content: str,
        branch: str = 'main',
        readme_html: Optional[str] = None,
    ) -> List[ProjectImage]:
        """提取 README 中的图片（相对路径按仓库默认分支解析）"""
        url_info = GitHubUrlParser.parse_github_url(github_url)

        extractor = ReadmeImageExtractor(
            github_url,
            url_info['owner'],
            url_info['repo'],
            branch,
        )

        return extractor.extract_images_from_markdown(markdown_content, readme_html)

    def extract_readme_videos(
        self,
        github_url: str,
        markdown_content: str,
        branch: str = "main",
        readme_html: Optional[str] = None,
    ) -> List[ProjectVideo]:
        """提取 README 中的内嵌视频链接。"""
        url_info = GitHubUrlParser.parse_github_url(github_url)
        extractor = ReadmeImageExtractor(
            github_url,
            url_info["owner"],
            url_info["repo"],
            branch,
        )
        return extractor.extract_videos_from_readme(markdown_content, readme_html)