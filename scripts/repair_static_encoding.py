#!/usr/bin/env python3
"""Repair UTF-8 corruption in static HTML files caused by PowerShell re-encoding."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

GIT_RESTORE_REF = "ed2c419"
AUTH_RESTORE_REF = "origin/master"

APP_SHELL_VERSION = "20260917"
THEME_JS_VERSION = "20260917"
APP_NAV_VERSION = "20260917a"
EMBED_JS_VERSION = "20260917b"
UI_JS_VERSION = "20260916"
DESKTOP_WINDOW_VERSION = "20260911c"

HTML_FILES = [
    "auth.html",
    "candidate_pool.html",
    "dashboard.html",
    "design-system.html",
    "digital_human.html",
    "github_video_maker.html",
    "hot_radar.html",
    "index.html",
    "ingestion_library.html",
    "model_settings.html",
    "publish_center.html",
    "publish_comments.html",
    "publish_metrics.html",
    "publish_queue.html",
    "scrape.html",
    "settings.html",
    "video_editor3.html",
    "video_maker.html",
]

EMBED_PAGES = {
    "publish_queue.html",
    "publish_metrics.html",
    "publish_comments.html",
    "candidate_pool.html",
}

# auth.html is loaded from Tauri frontendDist (`static/`), so it cannot use /static/... paths.
THEME_PAGES = set(HTML_FILES) - {"favicon_test.html", "auth.html"}


def git_show(path: str, ref: str = GIT_RESTORE_REF) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8")


def restore_html(name: str) -> str:
    path = f"static/{name}"
    ref = AUTH_RESTORE_REF if name == "auth.html" else GIT_RESTORE_REF
    return git_show(path, ref=ref)


def upsert_script(text: str, src: str, *, before: str | None = None) -> str:
    if src in text:
        return text
    tag = f'    <script src="{src}"></script>\n'
    if before and before in text:
        return text.replace(before, tag + before, 1)
    return text.replace("</head>", tag + "</head>", 1)


def patch_common(text: str, name: str) -> str:
    text = re.sub(
        r"/static/css/app_shell\.css\?v=[^\"']+",
        f"/static/css/app_shell.css?v={APP_SHELL_VERSION}",
        text,
    )
    if "app_shell.css" not in text:
        text = text.replace(
            '<link rel="stylesheet" href="/static/css/tokens.css">',
            '<link rel="stylesheet" href="/static/css/tokens.css">\n'
            f'    <link rel="stylesheet" href="/static/css/app_shell.css?v={APP_SHELL_VERSION}">',
            1,
        )
    text = re.sub(
        r"/static/js/shared/app_nav\.js\?v=[^\"']+",
        f"/static/js/shared/app_nav.js?v={APP_NAV_VERSION}",
        text,
    )
    if name in THEME_PAGES:
        text = re.sub(
            r"/static/js/shared/theme\.js\?v=[^\"']+",
            f"/static/js/shared/theme.js?v={THEME_JS_VERSION}",
            text,
        )
        text = upsert_script(
            text,
            f"/static/js/shared/theme.js?v={THEME_JS_VERSION}",
            before='    <script src="/static/js/shared/app_nav.js',
        )
    if name in EMBED_PAGES:
        text = re.sub(
            r"/static/js/shared/embed\.js\?v=[^\"']+",
            f"/static/js/shared/embed.js?v={EMBED_JS_VERSION}",
            text,
        )
        text = upsert_script(
            text,
            f"/static/js/shared/embed.js?v={EMBED_JS_VERSION}",
            before='    <script src="/static/js/shared/theme.js',
        )
    return text


def apply_publish_ui_pages() -> None:
    """Re-apply slim publish center + accounts page (not in old git restore ref)."""
    import runpy

    runpy.run_path(str(ROOT / "scripts" / "ensure_publish_ui_pages.py"), run_name="__main__")


def patch_file_specific(text: str, name: str) -> str:
    if name == "auth.html":
        text = re.sub(
            r'(?:/static)?/js/shared/theme\.js(\?v=[^"\']+)?',
            f"/js/shared/theme.js?v={THEME_JS_VERSION}",
            text,
        )
        text = upsert_script(
            text,
            f"/js/shared/theme.js?v={THEME_JS_VERSION}",
            before='    <script src="/js/auth.js"',
        )
    if name == "dashboard.html":
        text = upsert_script(text, f"/static/js/shared/ui.js?v={UI_JS_VERSION}", before='    <script src="/static/js/shared/app_nav.js')
        text = re.sub(
            r"/static/js/dashboard\.js\?v=[^\"']+",
            "/static/js/dashboard.js?v=20260917c",
            text,
        )
        text = re.sub(
            r"/static/css/dashboard\.css\?v=[^\"']+",
            "/static/css/dashboard.css?v=20260916",
            text,
        )
    if name == "ingestion_library.html":
        text = re.sub(
            r"/static/css/ingestion_library\.css\?v=[^\"']+",
            "/static/css/ingestion_library.css?v=20260917",
            text,
        )
    if name == "hot_radar.html":
        text = re.sub(
            r"/static/css/hot_radar\.css\?v=[^\"']+",
            "/static/css/hot_radar.css?v=20260917",
            text,
        )
    if name == "publish_metrics.html":
        text = re.sub(
            r"/static/css/publish_metrics\.css\?v=[^\"']+",
            "/static/css/publish_metrics.css?v=20260917",
            text,
        )
    if name == "settings.html" or name == "model_settings.html":
        text = re.sub(
            r"/static/css/model_settings\.css\?v=[^\"']+",
            "/static/css/model_settings.css?v=20260917",
            text,
        )
    if name in {"publish_center.html", "ingestion_library.html", "publish_metrics.html", "scrape.html"}:
        desktop_tag = f'<script src="/static/js/shared/desktop_window.js?v={DESKTOP_WINDOW_VERSION}" defer></script>'
        if "desktop_window.js" not in text:
            text = text.replace(
                '    <script src="/static/js/shared/app_nav.js',
                f'    {desktop_tag}\n    <script src="/static/js/shared/app_nav.js',
                1,
            )
    return text


def is_corrupt(text: str) -> bool:
    if "\ufffd" in text:
        return True
    if re.search(r"[^\s<][?]/title>", text):
        return True
    if re.search(r"[^\s<][?]/h1>", text):
        return True
    if "路 " in text and "AINews" in text:
        return True
    return False


def main() -> int:
    bad_after: list[str] = []
    for name in HTML_FILES:
        text = restore_html(name)
        text = patch_common(text, name)
        text = patch_file_specific(text, name)
        path = STATIC / name
        path.write_text(text, encoding="utf-8", newline="\n")
        if is_corrupt(text):
            bad_after.append(name)

    apply_publish_ui_pages()

    print("Repair complete.")
    if bad_after:
        print("Still corrupt:", ", ".join(bad_after))
        return 1
    print("All HTML files restored with valid UTF-8.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
