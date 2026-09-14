#!/usr/bin/env python3
"""Repair UTF-8 corruption in static HTML files caused by PowerShell re-encoding."""

from __future__ import annotations

import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

# Files to fully restore from git HEAD, then re-apply intentional script patches.
RESTORE_FROM_GIT = [
    "digital_human.html",
    "github_video_maker.html",
    "hot_radar.html",
    "index.html",
    "ingestion_library.html",
    "model_settings.html",
    "publish_queue.html",
    "settings.html",
    "video_editor3.html",
    "video_maker.html",
]

APP_SHELL_VERSION = "20260911a"
APP_NAV_VERSION = "20260911b"
DESKTOP_WINDOW_VERSION = "20260911c"

PLATFORM_MODAL_HTML = """
    <div id="platformsModal" class="schedule-modal" hidden>
        <div class="schedule-box soft-card platforms-box">
            <h3>修改发布平台</h3>
            <p id="platformsModalTitle" class="hint schedule-modal-title"></p>
            <p id="platformsModalNote" class="hint schedule-modal-note">勾选要发布的平台。账号未登录的任务仍会入队，发布失败后可重试。</p>
            <div id="platformsChecklist" class="platforms-checklist"></div>
            <div class="schedule-actions">
                <button type="button" class="btn btn-soft" id="platformsCancelBtn">取消</button>
                <button type="button" class="btn" id="platformsSaveBtn">保存</button>
            </div>
        </div>
    </div>
""".strip(
    "\n"
)


def git_show(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8")


def checkout_git(paths: list[str]) -> None:
    subprocess.run(
        ["git", "checkout", "HEAD", "--", *paths],
        cwd=ROOT,
        check=True,
    )


def patch_script_tags(text: str) -> str:
    text = re.sub(
        r"/static/css/app_shell\.css\?v=[^\"']+",
        f"/static/css/app_shell.css?v={APP_SHELL_VERSION}",
        text,
    )
    text = re.sub(
        r"/static/js/shared/app_nav\.js\?v=[^\"']+",
        f"/static/js/shared/app_nav.js?v={APP_NAV_VERSION}",
        text,
    )
    desktop_tag = (
        f'<script src="/static/js/shared/desktop_window.js?v={DESKTOP_WINDOW_VERSION}" defer></script>'
    )
    if "desktop_window.js" not in text:
        text = re.sub(
            r'(\s*)<script src="/static/js/shared/app_nav\.js',
            rf"\1{desktop_tag}\n\1<script src=\"/static/js/shared/app_nav.js",
            text,
            count=1,
        )
    text = text.replace('src=\\"/static/js/shared/app_nav.js', 'src="/static/js/shared/app_nav.js')
    return text


def patch_publish_queue(text: str) -> str:
    text = patch_script_tags(text)
    text = re.sub(
        r"/static/css/publish_queue\.css\?v=[^\"']+",
        "/static/css/publish_queue.css?v=20260910a",
        text,
    )
    text = re.sub(
        r"/static/js/publish_queue\.js\?v=[^\"']+",
        "/static/js/publish_queue.js?v=20260910a",
        text,
    )
    if "platformsModal" not in text:
        text = text.replace(
            "    <div id=\"scheduleModal\" class=\"schedule-modal\" hidden>",
            PLATFORM_MODAL_HTML + "\n\n    <div id=\"scheduleModal\" class=\"schedule-modal\" hidden>",
        )
    return text


def fix_broken_closing_tags(line: str) -> str:
    line = line.replace("\ufffd", "")
    line = re.sub(
        r"([^<])\?/(p|span|button|option|td|th|h2|h3|label|div|tr|small|strong|h1)>",
        r"\1</\2>",
        line,
    )
    line = re.sub(
        r"<!-- \?([^-].*?) -->",
        lambda m: f"<!-- {m.group(1)} -->",
        line,
    )
    line = re.sub(r"<!-- \?(.*)", lambda m: f"<!-- {m.group(1)}", line)
    line = re.sub(r"（([^）]*?)\?([^）]*?)）", r"（\1→\2）", line)
    return line


def repair_publish_center(current_text: str, git_text: str) -> str:
    cur_lines = current_text.splitlines()
    git_lines = git_text.splitlines()
    matcher = difflib.SequenceMatcher(None, git_lines, cur_lines, autojunk=False)
    repaired: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(j2 - j1):
                current_line = cur_lines[j1 + offset]
                git_line = git_lines[i1 + offset]
                if "\ufffd" in current_line:
                    repaired.append(git_line)
                else:
                    repaired.append(current_line)
        elif tag == "replace":
            git_chunk = git_lines[i1:i2]
            cur_chunk = cur_lines[j1:j2]
            if len(git_chunk) == len(cur_chunk):
                for git_line, current_line in zip(git_chunk, cur_chunk):
                    if "\ufffd" in current_line:
                        repaired.append(git_line)
                    else:
                        repaired.append(current_line)
            else:
                inner = difflib.SequenceMatcher(
                    None, git_chunk, cur_chunk, autojunk=False
                )
                for inner_tag, gi1, gi2, gj1, gj2 in inner.get_opcodes():
                    if inner_tag == "equal":
                        for offset in range(gj2 - gj1):
                            current_line = cur_chunk[gj1 + offset]
                            git_line = git_chunk[gi1 + offset]
                            repaired.append(
                                git_line if "\ufffd" in current_line else current_line
                            )
                    elif inner_tag in {"insert", "replace"}:
                        for current_line in cur_chunk[gj1:gj2]:
                            repaired.append(fix_broken_closing_tags(current_line))
        elif tag == "insert":
            for current_line in cur_lines[j1:j2]:
                if "\ufffd" in current_line:
                    repaired.append(fix_broken_closing_tags(current_line))
                else:
                    repaired.append(current_line)
        elif tag == "delete":
            continue

    text = "\n".join(repaired)
    if current_text.endswith("\n"):
        text += "\n"
    return patch_script_tags(text)


def count_replacement_chars(path: Path) -> int:
    return path.read_text(encoding="utf-8-sig", errors="replace").count("\ufffd")


def main() -> int:
    restore_paths = [f"static/{name}" for name in RESTORE_FROM_GIT]
    checkout_git(restore_paths)

    for name in RESTORE_FROM_GIT:
        path = STATIC / name
        text = path.read_text(encoding="utf-8")
        if name == "publish_queue.html":
            text = patch_publish_queue(text)
        else:
            text = patch_script_tags(text)
        path.write_text(text, encoding="utf-8", newline="\n")

    publish_center_path = STATIC / "publish_center.html"
    current_pc = publish_center_path.read_text(encoding="utf-8-sig", errors="replace")
    git_pc = git_show("static/publish_center.html")
    repaired_pc = repair_publish_center(current_pc, git_pc)
    publish_center_path.write_text(repaired_pc, encoding="utf-8", newline="\n")

    print("Repair complete. Remaining replacement characters:")
    bad = []
    for path in sorted(STATIC.glob("*.html")):
        count = count_replacement_chars(path)
        if count:
            bad.append((path.name, count))
    if bad:
        for name, count in bad:
            print(f"  {name}: {count}")
        return 1

    print("  (none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
