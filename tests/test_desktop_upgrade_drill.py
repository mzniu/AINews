from __future__ import annotations

from scripts.desktop_upgrade_drill import prepare_drill_root, run_drill


def test_desktop_upgrade_drill_creates_schema_and_rolls_back_flags(tmp_path):
    root = tmp_path / "drill"
    report = run_drill(root=root)
    assert report["ok"] is True
    assert "auto_publish_candidates" in report["tables"]
    assert "auto_publish_dispatch_leases" in report["tables"]
    assert report["config"]["policy_enabled_after_shadow_deploy"] is False
    assert report["config"]["kuaishou_paused"] is False
    assert report["flag_rollback"]["rolled_back_enabled"] is False
    assert report["dry_run"]["schema_ready"] is True
    assert (root / "config" / "article_scoring.local.yaml").is_file()


def test_prepare_drill_root_is_idempotent(tmp_path):
    first = prepare_drill_root(tmp_path / "once")
    second = prepare_drill_root(tmp_path / "once")
    assert first["db_path"] == second["db_path"]
    assert first["db_path"].parent.is_dir()
