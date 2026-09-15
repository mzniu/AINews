#!/usr/bin/env python3
"""Render Python vs Remotion comparison for the latest ingested article."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.engine import get_session_factory, init_db
from src.db.models.ingestion import ArticleImage, IngestedArticle
from services.ingestion.render_templates import get_render_template
from services.ingestion.video_render_service import render_ingested_video, resolve_ingested_clip_durations


QA_DIR = ROOT / "data" / "qa" / "remotion-comparison"
VENTUREBEAT_FIXTURE = ROOT / "venturebeat_article_complete.json"
DEFAULT_TEMPLATE_ID = "chronicle_archive_tech_blue"
TEST_BGM = ROOT / "remotion" / "public" / "static" / "music" / "test-bgm.mp3"


def _ensure_test_bgm() -> str:
    TEST_BGM.parent.mkdir(parents=True, exist_ok=True)
    if TEST_BGM.is_file() and TEST_BGM.stat().st_size > 0:
        return f"static/music/test-bgm.mp3"
    sine = QA_DIR / "generated-test-bgm.mp3"
    sine.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=8",
        "-q:a",
        "5",
        str(sine),
    ]
    subprocess.run(cmd, check=False, capture_output=True)
    if sine.is_file():
        TEST_BGM.write_bytes(sine.read_bytes())
    return "static/music/test-bgm.mp3" if TEST_BGM.is_file() else ""


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


def _latest_from_fixture() -> dict:
    payload = json.loads(VENTUREBEAT_FIXTURE.read_text(encoding="utf-8"))
    article_id = "qa-venturebeat-gea"
    asset_dir = QA_DIR / article_id / "images"
    asset_dir.mkdir(parents=True, exist_ok=True)
    image_paths: list[str] = []
    for index, image in enumerate(payload.get("images", [])[:3], start=1):
        url = image.get("url")
        if not url:
            continue
        dest = asset_dir / f"img_{index:02d}.jpg"
        if not dest.is_file():
            try:
                urllib.request.urlretrieve(url, dest)
            except Exception:
                continue
        if dest.is_file():
            image_paths.append(dest.relative_to(ROOT).as_posix())
    if len(image_paths) < 2:
        for fallback in ("static/imgs/bg-2.png", "static/imgs/bg.png"):
            p = ROOT / fallback
            if p.is_file():
                image_paths.append(fallback)
        image_paths = list(dict.fromkeys(image_paths))[:3]
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
        "image_paths": image_paths,
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


def main() -> int:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    subject = _resolve_subject()
    article_id = subject["article_id"]
    template = get_render_template(subject["template_id"])
    durations = resolve_ingested_clip_durations(len(subject["image_paths"]), template=template)
    bgm = _ensure_test_bgm()

    meta_path = QA_DIR / f"{article_id}_meta.json"
    meta_path.write_text(json.dumps(subject, ensure_ascii=False, indent=2), encoding="utf-8")

    python_out = render_ingested_video(
        article_id=article_id,
        draft=subject["draft"],
        image_paths=subject["image_paths"],
        bgm_path=bgm,
        template=template,
        renderer="python",
    )
    remotion_out = render_ingested_video(
        article_id=article_id,
        draft=subject["draft"],
        image_paths=subject["image_paths"],
        bgm_path=bgm,
        template=template,
        renderer="remotion",
    )

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "subject": subject,
        "bgm_path": bgm,
        "python": python_out,
        "remotion": remotion_out,
    }
    report_path = QA_DIR / f"{article_id}_comparison.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if python_out.get("success") and remotion_out.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
