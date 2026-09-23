"""Pattern lab page stays in product language."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pattern_lab_install_copy_has_no_engineer_jargon():
    html = (ROOT / "static" / "pattern_lab.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "pattern_lab.js").read_text(encoding="utf-8")
    blob = html + js
    for word in ("白名单", "JSONL", "ACL", "danger-full-access"):
        assert word not in blob
    assert "重新检测" in js
    assert "先关掉" in js
    assert "jobProgressBox" in html
    assert "startPolling" in js
    assert "card_preview" in js
    assert "拆卡详细日志（进行中自动刷新）" in html
    assert 'id="versionsBox"' in html
    assert "loadVersions" in js
    assert "loadSessionLog(jobId)" in js
    assert "schema_issues" in js


def test_nav_and_homepage_expose_playbook():
    nav = (ROOT / "static" / "js" / "shared" / "app_nav.js").read_text(encoding="utf-8")
    index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    scrape = (ROOT / "static" / "scrape.html").read_text(encoding="utf-8")
    settings = (ROOT / "static" / "settings.html").read_text(encoding="utf-8")
    assert "{ href: '/pattern-lab', label: '打法学习', icon: 'film' }" in nav
    assert nav.index("打法学习") < nav.index("视频制作")
    assert 'id="playbookDraftBtn"' in index
    assert 'id="playbookDraftBtn"' in scrape
    assert "disabled" in index
    assert "打法版本在打法学习页发布，这里的保存不会写入打法。" in settings
    main = (ROOT / "static" / "js" / "index" / "main.js").read_text(encoding="utf-8")
    modal = (ROOT / "static" / "js" / "shared" / "publish_modal.js").read_text(encoding="utf-8")
    assert "edited: true" in main
    assert "这版打法，之后改过" in main
    assert "lastPlaybookStamp = null" in main
    assert "playbook_attribution" in modal
    assert "copy_draft_id" in modal
