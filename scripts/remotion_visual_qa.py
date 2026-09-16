#!/usr/bin/env python3
"""Render Python vs Remotion comparison for the latest ingested article."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ingestion.chronicle_render import render_chronicle_cover
from services.ingestion.cover_video_utils import prepend_cover_intro_to_video
from services.ingestion.render_templates import get_render_template
from services.ingestion.video_render_service import render_ingested_video, resolve_ingested_clip_durations
from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import ArticleImage, IngestedArticle

QA_DIR = ROOT / "data" / "qa" / "remotion-comparison"
QA_ARTIFACTS = ROOT / "remotion" / "qa-artifacts"
VENTUREBEAT_FIXTURE = ROOT / "venturebeat_article_complete.json"
DEFAULT_TEMPLATE_ID = "chronicle_archive_tech_blue"
FEATURED_BGM_PATH = "static/music/Memories.mp3"
FALLBACK_BGM_PATH = "static/music/background.mp3"
GIF_PATH = "data/test_gifs/moving_circle.gif"


def _repo_bgm() -> str:
    """Resolve featured BGM (Memories.mp3) for QA; symlink test-bgm for npm render:bgm."""
    for rel in (FEATURED_BGM_PATH, FALLBACK_BGM_PATH):
        candidate = ROOT / rel
        if candidate.is_file():
            bgm_path = rel
            break
    else:
        fallback = ROOT / FALLBACK_BGM_PATH
        fallback.parent.mkdir(parents=True, exist_ok=True)
        sine = QA_DIR / "generated-test-bgm.mp3"
        sine.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-q:a", "5", str(sine)],
            check=False,
            capture_output=True,
        )
        if sine.is_file():
            shutil.copy2(sine, fallback)
        bgm_path = FALLBACK_BGM_PATH if fallback.is_file() else ""

    if not bgm_path:
        return ""

    test_link = ROOT / "remotion" / "public" / "static" / "music" / "test-bgm.mp3"
    test_link.parent.mkdir(parents=True, exist_ok=True)
    resolved = (ROOT / bgm_path).resolve()
    if test_link.is_symlink() or test_link.exists():
        if test_link.is_symlink() and test_link.resolve() == resolved:
            return bgm_path
        test_link.unlink(missing_ok=True)
    test_link.symlink_to(resolved)
    return bgm_path


def _latest_from_db() -> dict | None:
    init_db()
    factory = get_session_factory()
    session = factory()
    try:
        article = (
            session.query(IngestedArticle)
            .order_by(IngestedArticle.created_at.desc())
            .first()
        )
        if article is None:
            return None
        images = (
            session.query(ArticleImage)
            .filter_by(article_id=article.id, download_status="ok")
            .order_by(ArticleImage.sort_order.asc())
            .all()
        )
        draft = json.loads(article.video_draft_json or "{}") if article.video_draft_json else {}
        if not draft:
            draft = {
                "main_line1": (article.title or "AI 快讯")[:24],
                "main_line2": "",
                "sub_title": "快讯",
                "summary": article.summary or article.content_text or "",
                "tags": "",
                "highlight_keywords": [],
            }
        image_paths = [img.local_path for img in images if img.local_path][:4]
        return {
            "source": "database",
            "article_id": article.id,
            "title": article.title,
            "created_at": article.created_at.isoformat() if article.created_at else None,
            "draft": draft,
            "image_paths": image_paths,
            "template_id": DEFAULT_TEMPLATE_ID,
        }
    finally:
        session.close()


def _download_fixture_images(asset_dir: Path, urls: list[str]) -> list[str]:
    image_paths: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AINews-QA/1.0)"}
    for index, url in enumerate(urls[:3], start=1):
        dest = asset_dir / f"img_{index:02d}.jpg"
        if not dest.is_file():
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    dest.write_bytes(resp.read())
            except Exception:
                continue
        if dest.is_file() and dest.stat().st_size > 0:
            image_paths.append(dest.relative_to(ROOT).as_posix())
    return image_paths


def _latest_from_fixture() -> dict:
    payload = json.loads(VENTUREBEAT_FIXTURE.read_text(encoding="utf-8"))
    article_id = "qa-venturebeat-gea"
    asset_dir = QA_DIR / article_id / "images"
    asset_dir.mkdir(parents=True, exist_ok=True)
    urls = [str(item.get("url") or "") for item in payload.get("images", []) if item.get("url")]
    image_paths = _download_fixture_images(asset_dir, urls)

    if len(image_paths) < 2:
        for fallback in ("static/imgs/bg-2.png", "static/imgs/bg.png"):
            p = ROOT / fallback
            if p.is_file():
                image_paths.append(fallback)
        image_paths = list(dict.fromkeys(image_paths))[:3]

    gif = ROOT / GIF_PATH
    if gif.is_file() and GIF_PATH not in image_paths:
        image_paths = [image_paths[0], GIF_PATH] + image_paths[1:3]

    title = payload.get("title") or "AI agent framework breakthrough"
    draft = {
        "main_line1": "突发！Agent框架新突破",
        "main_line2": "匹配人类工程化AI系统",
        "sub_title": "VentureBeat",
        "sub_title2": "零推理部署成本",
        "summary": f"小牛说：{payload.get('summary') or title}",
        "tags": "#Agent #AI",
        "highlight_keywords": ["Agent", "AI"],
    }
    return {
        "source": "fixture",
        "article_id": article_id,
        "title": title,
        "created_at": payload.get("publish_date"),
        "draft": draft,
        "image_paths": image_paths[:4],
        "template_id": DEFAULT_TEMPLATE_ID,
    }


def _resolve_subject() -> dict:
    subject = _latest_from_db()
    if subject and len(subject.get("image_paths") or []) >= 2:
        return subject
    fixture = _latest_from_fixture()
    if subject:
        fixture["db_article_id"] = subject.get("article_id")
        fixture["note"] = "DB article lacked images; used venturebeat fixture"
    return fixture


def _render_cover(article_id: str, draft: dict, image_paths: list[str], template: dict) -> str:
    if not image_paths:
        return ""
    result = render_chronicle_cover(
        article_id=article_id,
        draft=draft,
        image_path=image_paths[0],
        template=template,
    )
    if result.get("success"):
        return str(result.get("cover_path") or "")
    return ""


def _publish_artifacts(article_id: str, python_path: str, remotion_path: str) -> dict[str, str]:
    QA_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    published: dict[str, str] = {}
    for label, src in (("python", python_path), ("remotion", remotion_path)):
        raw = str(src or "").lstrip("/")
        source = ROOT / raw
        if not source.is_file():
            continue
        dest = QA_ARTIFACTS / f"{article_id}_{label}_qa.mp4"
        shutil.copy2(source, dest)
        published[label] = str(dest.resolve())
    return published


def main() -> int:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    subject = _resolve_subject()
    article_id = subject["article_id"]
    template = get_render_template(subject["template_id"])
    durations = resolve_ingested_clip_durations(len(subject["image_paths"]), template=template)
    bgm = _repo_bgm()
    cover_path = _render_cover(article_id, subject["draft"], subject["image_paths"], template)
    intro_sec = 1.0

    meta_path = QA_DIR / f"{article_id}_meta.json"
    meta_path.write_text(json.dumps({**subject, "cover_path": cover_path, "bgm_path": bgm}, ensure_ascii=False, indent=2), encoding="utf-8")

    python_out = render_ingested_video(
        article_id=article_id,
        draft=subject["draft"],
        image_paths=subject["image_paths"],
        bgm_path=bgm,
        template=template,
        renderer="python",
    )
    if python_out.get("success") and cover_path:
        intro = prepend_cover_intro_to_video(
            video_path=str(python_out["video_path"]).lstrip("/"),
            cover_path=cover_path,
            intro_duration=intro_sec,
        )
        python_out["cover_intro"] = intro
        if intro.get("success") and intro.get("video_path"):
            python_out["video_path"] = intro["video_path"]

    remotion_out = render_ingested_video(
        article_id=article_id,
        draft=subject["draft"],
        image_paths=subject["image_paths"],
        bgm_path=bgm,
        template=template,
        renderer="remotion",
    )

    published = _publish_artifacts(
        article_id,
        str(python_out.get("video_path") or ""),
        str(remotion_out.get("video_path") or ""),
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "subject": subject,
        "bgm_path": bgm,
        "cover_path": cover_path,
        "cover_intro_sec": intro_sec,
        "gif_included": GIF_PATH in subject["image_paths"],
        "python": python_out,
        "remotion": remotion_out,
        "published_artifacts": published,
    }
    report_path = QA_DIR / f"{article_id}_comparison.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if python_out.get("success") and remotion_out.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
