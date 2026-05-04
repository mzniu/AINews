"""
GitHub 资源镜像（可选，适合国内网络）

通过环境变量把请求走公共代理或自建镜像，无需改业务代码。

环境变量（均为可选）：

1) GITHUB_RAW_MIRROR_PREFIX
   加在「完整原始 URL」前面。常见写法（以 ghproxy 类为例）：
     set GITHUB_RAW_MIRROR_PREFIX=https://ghproxy.com/
   则下载
     https://raw.githubusercontent.com/org/repo/main/a.png
   变为
     https://ghproxy.com/https://raw.githubusercontent.com/org/repo/main/a.png

2) GITHUB_API_MIRROR
   替换 api.github.com 的协议与主机部分，用于 REST API。示例：
     set GITHUB_API_MIRROR=https://ghproxy.com/https://api.github.com
   则
     https://api.github.com/repos/...
   变为
     https://ghproxy.com/https://api.github.com/repos/...

说明：
- 镜像站域名、是否可用以各站当前服务为准，请自行选用可访问的线路。
- 若未设置上述变量，行为与直连 GitHub 一致。
"""
from __future__ import annotations

import os
from urllib.parse import urlparse, unquote


def normalize_github_image_url(url: str) -> str:
    """
    将 github.com/{owner}/{repo}/blob/{ref}/path 或 .../raw/{ref}/path
    转为 https://raw.githubusercontent.com/{owner}/{repo}/{ref}/path。
    直接请求 blob 网页会得到 HTML，无法作为图片解码。
    """
    try:
        p = urlparse(url.strip())
        host = (p.netloc or "").lower()
        if host not in ("github.com", "www.github.com"):
            return url
        parts = [x for x in p.path.strip("/").split("/") if x]
        if len(parts) < 4:
            return url
        owner, repo = parts[0], parts[1]
        if parts[2] not in ("blob", "raw"):
            return url
        ref = parts[3]
        path_in_repo = "/".join(unquote(seg) for seg in parts[4:])
        if not path_in_repo:
            return url
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path_in_repo}"
    except Exception:
        return url


def mirror_github_raw_url(url: str) -> str:
    """为 raw.githubusercontent.com 的完整 https URL 加前缀（若已配置）。"""
    url = normalize_github_image_url(url)
    prefix = os.environ.get("GITHUB_RAW_MIRROR_PREFIX", "").strip()
    if not prefix or "raw.githubusercontent.com" not in url:
        return url
    if not url.startswith("https://"):
        return url
    sep = "" if prefix.endswith("/") else "/"
    return f"{prefix}{sep}{url}"


def mirror_github_api_url(url: str) -> str:
    """将 https://api.github.com 替换为 GITHUB_API_MIRROR（若已配置）。"""
    base = os.environ.get("GITHUB_API_MIRROR", "").strip().rstrip("/")
    if not base or "api.github.com" not in url:
        return url
    return url.replace("https://api.github.com", base, 1)
