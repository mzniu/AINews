"""Desktop upgrade drill for video-performance-recovery.

Creates an isolated AppData-like directory, optionally seeds from a source DB,
ensures schema/config migration, runs rebuild dry-run, and verifies flag rollback.

Never mutates the live production database.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_TABLES = (
    "auto_publish_candidates",
    "auto_publish_dispatch_leases",
    "publish_jobs",
    "publisher_accounts",
    "ingested_articles",
)


def _utc_stamp() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def prepare_drill_root(root: Path) -> dict[str, Path]:
    root = root.expanduser().resolve()
    data_dir = root / "data"
    config_dir = root / "config"
    backup_dir = data_dir / "publish" / "backups"
    for path in (data_dir, config_dir, backup_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "data_dir": data_dir,
        "config_dir": config_dir,
        "db_path": data_dir / "ainews.db",
        "local_config": config_dir / "article_scoring.local.yaml",
        "backup_dir": backup_dir,
    }


def seed_database(db_path: Path, source_db: Path | None) -> str:
    if source_db is None:
        return "empty"
    source = source_db.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"source database missing: {source}")
    shutil.copy2(source, db_path)
    return str(source)


def ensure_schema(db_path: Path) -> list[str]:
    from src.db.engine import init_db

    init_db(f"sqlite:///{db_path.as_posix()}")
    with sqlite3.connect(db_path) as connection:
        names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = [name for name in REQUIRED_TABLES if name not in names]
    if missing:
        raise RuntimeError(f"schema missing tables after init_db: {missing}")
    return sorted(names)


def migrate_local_config(paths: dict[str, Path], source_local: Path | None = None) -> dict:
    from services.ingestion import scoring_settings

    previous_local = scoring_settings.SCORING_LOCAL_PATH
    scoring_settings.SCORING_LOCAL_PATH = paths["local_config"]
    try:
        if source_local and source_local.is_file() and not paths["local_config"].exists():
            shutil.copy2(source_local, paths["local_config"])
        scoring_settings._migrate_legacy_local_config()
        before = scoring_settings.get_publish_policy_settings()
        # Shadow deploy defaults: policy enabled false unless already present.
        saved = scoring_settings.save_publish_policy_settings(
            {
                "enabled": False,
                "shadow_mode": True,
                "platforms": {
                    "wechat_channels": {"enabled": False, "shadow_mode": True},
                    "douyin": {"enabled": False, "shadow_mode": True},
                    "kuaishou": {
                        "enabled": False,
                        "shadow_mode": True,
                        "paused": False,
                    },
                },
            }
        )
        return {"before": before, "after": saved}
    finally:
        scoring_settings.SCORING_LOCAL_PATH = previous_local


def run_rebuild_dry_run(db_path: Path) -> dict:
    import scripts.rebuild_pending_publish_queue as rebuild

    report = rebuild.inspect_database(db_path)
    return {
        "schema_ready": report.get("schema_ready"),
        "schema_warnings": report.get("schema_warnings"),
        "summary": report.get("summary"),
        "policy_version": report.get("policy_version"),
    }


def verify_flag_rollback(paths: dict[str, Path]) -> dict:
    from services.ingestion import scoring_settings

    previous_local = scoring_settings.SCORING_LOCAL_PATH
    scoring_settings.SCORING_LOCAL_PATH = paths["local_config"]
    try:
        enabled = scoring_settings.save_publish_policy_settings(
            {
                "enabled": True,
                "shadow_mode": False,
                "platforms": {
                    "wechat_channels": {"enabled": True, "shadow_mode": False},
                },
            }
        )
        rolled_back = scoring_settings.save_publish_policy_settings(
            {
                "enabled": False,
                "shadow_mode": True,
                "platforms": {
                    "wechat_channels": {"enabled": False, "shadow_mode": True},
                },
            }
        )
        return {"enabled": enabled, "rolled_back": rolled_back}
    finally:
        scoring_settings.SCORING_LOCAL_PATH = previous_local


def run_drill(
    *,
    root: Path,
    source_db: Path | None = None,
    source_local: Path | None = None,
) -> dict:
    paths = prepare_drill_root(root)
    os.environ["AINEWS_DATA_DIR"] = str(paths["data_dir"])
    try:
        from src.utils.paths import get_data_dir

        get_data_dir.cache_clear()
    except Exception:
        pass
    seed = seed_database(paths["db_path"], source_db)
    tables = ensure_schema(paths["db_path"])
    config = migrate_local_config(paths, source_local=source_local)
    dry_run = run_rebuild_dry_run(paths["db_path"])
    flags = verify_flag_rollback(paths)
    report = {
        "ok": True,
        "stamp": _utc_stamp(),
        "root": str(paths["root"]),
        "seed_source": seed,
        "tables": tables,
        "config": {
            "local_config": str(paths["local_config"]),
            "policy_enabled_after_shadow_deploy": config["after"]["enabled"],
            "kuaishou_paused": bool(
                ((config["after"].get("platforms") or {}).get("kuaishou") or {}).get(
                    "paused", False
                )
            ),
        },
        "dry_run": dry_run,
        "flag_rollback": {
            "enabled_was": flags["enabled"]["enabled"],
            "rolled_back_enabled": flags["rolled_back"]["enabled"],
            "wechat_mode_after_rollback": (
                (flags["rolled_back"].get("platforms") or {})
                .get("wechat_channels", {})
                .get("shadow_mode")
            ),
        },
        "go_live_order": [
            "1. File-level backup production ainews.db",
            "2. Deploy desktop build / restart once so init_db creates candidate tables",
            "3. Keep publish_policy.enabled=false (shadow)",
            "4. python scripts/rebuild_pending_publish_queue.py --db <prod>  # dry-run",
            "5. Only after review: --apply --backup <path>",
            "6. Enable wechat_channels only (enabled=true, shadow_mode=false)",
            "7. Promote douyin then kuaishou after stage gates",
            "8. Kill-switch auto-disables weak wechat policy; never pauses kuaishou",
        ],
    }
    if not dry_run.get("schema_ready"):
        report["ok"] = False
    if flags["rolled_back"]["enabled"] is not False:
        report["ok"] = False
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("tmp") / f"desktop-upgrade-drill-{_utc_stamp()}",
        help="Isolated drill directory (default under ./tmp)",
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=None,
        help="Optional source DB to copy (for example production AppData ainews.db)",
    )
    parser.add_argument(
        "--source-local",
        type=Path,
        default=None,
        help="Optional article_scoring.local.yaml to copy into the drill config dir",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write the drill report JSON to this path",
    )
    args = parser.parse_args(argv)
    report = run_drill(
        root=args.root,
        source_db=args.source_db,
        source_local=args.source_local,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
