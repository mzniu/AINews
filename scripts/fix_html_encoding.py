"""Restore static HTML from git HEAD and re-apply app shell nav (UTF-8 safe).

WARNING: Do not use this to restore publish_center.html or settings.html —
those pages have features beyond git HEAD (metrics tab, scoring tab). Use only
for emergency UTF-8 repair on pages without extra UI.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SHELL = """    <link rel="stylesheet" href="/static/css/app_shell.css?v=20260815a">
    <script src="/static/js/shared/app_nav.js?v=20260813c" defer></script>"""

NAV_PATTERNS = [
    re.compile(r"\n\s*<!--[^\n]*导航[^\n]*-->\n\s*<nav class=\"navbar\">.*?</nav>\s*", re.DOTALL),
    re.compile(r"\n\s*<nav class=\"navbar[^\"]*\">.*?</nav>\s*", re.DOTALL),
]


def git_text(path: str) -> str:
    raw = subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)
    return raw.decode("utf-8")


def insert_shell(head_html: str) -> str:
    if "app_shell.css" in head_html:
        return head_html
    token = '<link rel="stylesheet" href="/static/css/tokens.css">'
    if token in head_html:
        return head_html.replace(token, token + "\n" + SHELL, 1)
    return head_html


def strip_nav(html: str) -> str:
    for pat in NAV_PATTERNS:
        html = pat.sub("\n", html)
    return html


def set_body(html: str) -> str:
    if 'class="app-page"' not in html:
        html = re.sub(r"<body\s*>", '<body class="app-page">', html, count=1)
    if "app-nav-root" not in html:
        html = html.replace(
            '<body class="app-page">',
            '<body class="app-page">\n    <div id="app-nav-root"></div>\n',
            1,
        )
    return html


def patch_file(rel: str) -> None:
    text = git_text(rel)
    if rel.endswith("video_editor3.html"):
        text = text.replace('href="css/', 'href="/static/css/')
    if rel.endswith("publish_center.html"):
        # Keep page-specific inline styles but remove legacy nav/body rules if re-added from git
        pass
    head, sep, rest = text.partition("</head>")
    if sep:
        text = insert_shell(head) + sep + rest
    text = strip_nav(text)
    text = set_body(text)
    out = ROOT / rel
    out.write_text(text, encoding="utf-8", newline="\n")
    out.read_text(encoding="utf-8")


def write_ingestion_library() -> None:
    """Current soft-UI layout (not in git HEAD)."""
    content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>资讯库 - AINews</title>
    <link rel="stylesheet" href="/static/css/tokens.css">
    <link rel="stylesheet" href="/static/css/app_shell.css?v=20260815a">
    <link rel="stylesheet" href="/static/css/ingestion_library.css?v=20260813c">
    <script src="/static/js/shared/app_nav.js?v=20260813c" defer></script>
</head>
<body class="app-page">
    <div id="app-nav-root"></div>

    <div class="ingestion-shell">
        <header class="ingestion-header">
            <div class="ingestion-header-text">
                <p class="ingestion-eyebrow">news library</p>
                <h1>资讯库</h1>
                <p class="ingestion-lead">定时抓取入库 · 选题后跳转主页生成视频</p>
            </div>
            <div class="ingestion-header-search">
                <label class="sr-only" for="searchInput">搜索标题</label>
                <input id="searchInput" class="form-control ingestion-search" type="search" placeholder="搜索标题…">
            </div>
        </header>

        <div id="ingestionWorkerBanner" class="soft-banner soft-banner-warn" style="display:none;">
            ⚠️ 爬取 Worker 未运行。请重启 web_server，或在 <code>.env</code> 设置 <code>INGESTION_WORKER_MODE=separate</code> 后运行 worker。
        </div>

        <section class="soft-card toolbar">
            <div class="toolbar-grid">
                <div class="toolbar-field">
                    <label class="field-label" for="sourceSelect">数据源</label>
                    <select id="sourceSelect" class="form-control"></select>
                </div>
                <div class="toolbar-field">
                    <label class="field-label" for="sortSelect">排序</label>
                    <select id="sortSelect" class="form-control">
                        <option value="published_desc">发布时间</option>
                        <option value="score_desc">评分优先</option>
                    </select>
                </div>
                <div class="toolbar-field">
                    <label class="field-label" for="gradeSelect">等级</label>
                    <select id="gradeSelect" class="form-control">
                        <option value="">全部等级</option>
                        <option value="S">S 级</option>
                        <option value="A">A 级</option>
                        <option value="B">B 级</option>
                        <option value="C">C 级</option>
                        <option value="D">D 级</option>
                        <option value="unscored">未评分</option>
                    </select>
                </div>
                <div class="toolbar-field">
                    <label class="field-label">列表视图</label>
                    <div class="view-toggle" role="group" aria-label="列表视图">
                        <button type="button" class="view-toggle-btn active" id="viewListBtn" data-view="list">文章列表</button>
                        <button type="button" class="view-toggle-btn" id="viewTreeBtn" data-view="tree">同题树</button>
                    </div>
                </div>
                <div class="toolbar-actions">
                    <button class="btn btn-primary" id="refreshBtn" type="button">刷新</button>
                    <button class="btn btn-soft" id="runSourceBtn" type="button">立即抓取</button>
                    <button class="btn btn-soft" id="scoreBatchBtn" type="button">批量评分</button>
                    <button class="btn btn-accent" id="useOnHomeBtn" type="button" disabled>用于主页</button>
                </div>
            </div>
            <div id="statusBar" class="status-bar"></div>
        </section>

        <div class="ingestion-grid">
            <section class="soft-card list-panel-card">
                <div class="list-panel-header">
                    <div>
                        <p class="panel-eyebrow">articles</p>
                        <h2 class="panel-title">
                            <span id="listPanelTitleText">文章列表</span>
                            <span id="articleCount" class="count-pill">0</span>
                        </h2>
                    </div>
                    <div class="list-panel-tools">
                        <label class="tree-filter-label" id="treeFilterWrap" style="display:none;">
                            <input type="checkbox" id="treeMultiOnly" checked>
                            仅多篇同题
                        </label>
                        <button type="button" class="btn btn-soft btn-sm" id="aiReviewBtn" style="display:none;">AI 巡检</button>
                    </div>
                </div>
                <div class="article-list-scroll">
                    <div id="articleList"></div>
                </div>
                <div id="articleLoadMore" class="story-load-more" style="display:none;">
                    <button type="button" class="btn btn-soft btn-sm" id="loadMoreArticlesBtn">加载更多</button>
                </div>
                <div id="storyLoadMore" class="story-load-more" style="display:none;">
                    <button type="button" class="btn btn-soft btn-sm" id="loadMoreStoriesBtn">加载更多 Story</button>
                </div>
            </section>

            <div class="ingestion-detail-column">
                <section class="soft-card" id="aiReviewPanel" style="display:none;">
                    <div class="panel-header-row">
                        <h3 class="panel-title">AI 聚类巡检</h3>
                        <button type="button" class="btn btn-soft btn-sm" id="closeAiReviewBtn">关闭</button>
                    </div>
                    <div id="aiReviewContent" class="text-muted">点击「AI 巡检」分析近期 Story。</div>
                </section>
                <section class="soft-card detail-card" id="articleDetail">
                    <div class="detail-empty">
                        <p class="panel-eyebrow">detail</p>
                        <p class="text-muted">选择一篇文章查看详情</p>
                    </div>
                </section>
            </div>
        </div>
    </div>

    <script src="/static/js/shared/publish_modal.js?v=20260815a"></script>
    <script src="/static/js/ingestion_library.js?v=20260813a"></script>
</body>
</html>
"""
    path = ROOT / "static/ingestion_library.html"
    path.write_text(content, encoding="utf-8", newline="\n")
    path.read_text(encoding="utf-8")


def patch_publish_center() -> None:
    """Re-apply publish_center shell on top of git restore."""
    path = ROOT / "static/publish_center.html"
    text = path.read_text(encoding="utf-8")
    # Ensure app_shell is present (git version may lack it)
    head, sep, rest = text.partition("</head>")
    head = insert_shell(head)
    if "app_shell.css" not in head and "/static/css/tokens.css" in head:
        head = head.replace(
            '<link rel="stylesheet" href="/static/css/tokens.css">',
            '<link rel="stylesheet" href="/static/css/tokens.css">\n'
            '    <link rel="stylesheet" href="/static/css/app_shell.css?v=20260815a">',
            1,
        )
    if "app_nav.js" not in head:
        head += '\n    <script src="/static/js/shared/app_nav.js?v=20260813c" defer></script>'
    text = head + sep + rest
    text = strip_nav(text)
    text = set_body(text)
    # Trim legacy light-theme nav/body rules from inline style if present
    text = text.replace(
        "body { font-family: var(--font-sans); background: var(--bg-body); margin: 0; padding-top: 80px; }\n",
        "",
    )
    text = re.sub(
        r"        \.navbar \{.*?\}\n        \.nav-container \{.*?\}\n"
        r"        \.nav-brand \{.*?\}\n        \.nav-menu \{.*?\}\n"
        r"        \.nav-link \{.*?\}\n        \.nav-link\.active, \.nav-link:hover \{.*?\}\n",
        "",
        text,
        flags=re.DOTALL,
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_video_maker() -> None:
    path = ROOT / "static/video_maker.html"
    text = path.read_text(encoding="utf-8")
    if "app_shell.css" not in text:
        text = text.replace(
            '<link rel="stylesheet" href="/static/css/tokens.css">',
            '<link rel="stylesheet" href="/static/css/tokens.css">\n'
            '    <link rel="stylesheet" href="/static/css/app_shell.css?v=20260815a">',
            1,
        )
    if "app_nav.js" not in text:
        text = text.replace("</head>", '    <script src="/static/js/shared/app_nav.js?v=20260813c" defer></script>\n</head>', 1)
    text = strip_nav(text)
    text = set_body(text)
    # Remove inline navbar + body padding block if still present
    text = re.sub(
        r"\s*/\* 导航栏样式 \*/.*?padding-top: 80px;.*?\}\n",
        "\n",
        text,
        flags=re.DOTALL,
        count=1,
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    files = [
        "static/index.html",
        "static/model_settings.html",
        "static/video_maker.html",
        "static/github_video_maker.html",
        "static/digital_human.html",
        "static/video_editor3.html",
    ]
    for rel in files:
        patch_file(rel)
        print("patched", rel)
    write_ingestion_library()
    print("patched static/ingestion_library.html")
    patch_publish_center()
    patch_video_maker()
    for p in (ROOT / "static").glob("*.html"):
        p.read_text(encoding="utf-8")
        print("utf-8 ok", p.name)


if __name__ == "__main__":
    main()
