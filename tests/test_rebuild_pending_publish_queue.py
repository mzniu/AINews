from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.rebuild_pending_publish_queue as rebuild
from src.db.engine import Base
from src.db.models.ingestion import ArticleImage, IngestedArticle, IngestionSource, Story
from src.db.models.publishing import AutoPublishCandidate, PublishJob, PublisherAccount


def _valid_runtime_override() -> dict:
    return {
        "publish_policy": {
            "policy_version": 1,
            "enabled": True,
            "shadow_mode": False,
            "platforms": {
                "wechat_channels": {
                    "enabled": True,
                    "shadow_mode": False,
                    "daily_limit": 8,
                },
                "douyin": {
                    "enabled": True,
                    "shadow_mode": True,
                    "daily_limit": 10,
                },
                "kuaishou": {
                    "enabled": True,
                    "shadow_mode": True,
                    "daily_limit": 5,
                    "paused": False,
                    "pause_windows": [],
                },
            },
        }
    }


def _write_runtime_override(db_path: Path, value: dict | None = None) -> Path:
    import yaml

    path = db_path.parent / "config" / "article_scoring.local.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            _valid_runtime_override() if value is None else value,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _article(article_id: str, *, strong: bool, story_id: str | None = None) -> IngestedArticle:
    if strong:
        title = "突发：OpenAI裁员220%，GPT-5首次突破100亿参数"
        summary = "OpenAI CEO回应大规模裁员，人工智能行业发生重大变化。"
        content = ("OpenAI 人工智能 GPT 大模型 CEO 裁员 离职 监管 突破 收入100亿。") * 20
        keywords = ["AI", "OpenAI", "GPT-5", "大模型"]
    else:
        title = "普通生活记录"
        summary = "一则没有行业信号的普通消息。"
        content = "普通内容。"
        keywords = []
    return IngestedArticle(
        id=article_id,
        source_id="source-1",
        canonical_url=f"https://example.com/{article_id}",
        title=title,
        summary=summary,
        content_text=content,
        keywords_json=json.dumps(keywords, ensure_ascii=False),
        published_at=datetime.utcnow() - timedelta(hours=2),
        score_total=12.0,
        score_grade="D",
        score_breakdown_json=json.dumps(
            {
                "industry": {"total": 12.0, "grade": "D"},
                "viral": {"total": 11.0, "grade": "D"},
            }
        ),
        score_comment="old",
        scored_at=datetime(2026, 1, 1),
        story_id=story_id,
        generated_video_path=f"data/videos/{article_id}.mp4",
        video_draft_json=json.dumps({"main_line1": title[:24]}, ensure_ascii=False),
    )


@pytest.fixture
def queue_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AINEWS_DATA_DIR", str(tmp_path))
    from src.utils.paths import get_data_dir

    get_data_dir.cache_clear()
    path = tmp_path / "ainews.db"
    _write_runtime_override(path)
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "article-strong.mp4").write_bytes(b"video")
    (videos / "article-weak.mp4").write_bytes(b"video")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        IngestionSource(
            id="source-1",
            slug="source-1",
            display_name="Source",
            adapter_class="test",
        )
    )
    session.add(Story(id="story-1", canonical_title="story", article_count=2))
    strong = _article("article-strong", strong=True, story_id="story-1")
    weak = _article("article-weak", strong=False)
    session.add_all([strong, weak])
    for index in range(3):
        session.add(
            ArticleImage(
                id=f"image-{index}",
                article_id=strong.id,
                original_url=f"https://example.com/{index}.jpg",
                local_path=f"data/images/{index}.jpg",
                download_status="ok",
            )
        )
    accounts = {
        platform: PublisherAccount(
            id=f"account-{platform}",
            platform=platform,
            session_path=f"data/{platform}.json",
            status="active",
        )
        for platform in ("wechat_channels", "douyin", "kuaishou")
    }
    session.add_all(accounts.values())
    session.flush()
    scheduled = datetime(2026, 9, 14, 1, 0)
    session.add_all(
        [
            PublishJob(
                id="wechat-strong",
                account_id=accounts["wechat_channels"].id,
                video_path="data/strong.mp4",
                title="strong",
                status="pending",
                source_type="ingestion",
                source_id=strong.id,
                scheduled_at=scheduled,
            ),
            PublishJob(
                id="wechat-weak",
                account_id=accounts["wechat_channels"].id,
                video_path="data/weak.mp4",
                title="weak",
                status="pending",
                source_type="ingestion",
                source_id=weak.id,
            ),
            PublishJob(
                id="douyin-weak",
                account_id=accounts["douyin"].id,
                video_path="data/weak.mp4",
                title="weak",
                status="pending",
                source_type="ingestion",
                source_id=weak.id,
            ),
            PublishJob(
                id="kuaishou-weak",
                account_id=accounts["kuaishou"].id,
                video_path="data/weak.mp4",
                title="weak",
                status="pending",
                source_type="ingestion",
                source_id=weak.id,
            ),
            PublishJob(
                id="uploading",
                account_id=accounts["wechat_channels"].id,
                video_path="data/strong.mp4",
                title="uploading",
                status="uploading",
                source_type="ingestion",
                source_id=strong.id,
            ),
            PublishJob(
                id="manual",
                account_id=accounts["wechat_channels"].id,
                video_path="data/manual.mp4",
                title="manual",
                status="pending",
                source_type="manual",
                source_id=strong.id,
            ),
            PublishJob(
                id="published",
                account_id=accounts["wechat_channels"].id,
                video_path="data/strong.mp4",
                title="published",
                status="published",
                source_type="ingestion",
                source_id=strong.id,
            ),
            PublishJob(
                id="failed",
                account_id=accounts["wechat_channels"].id,
                video_path="data/strong.mp4",
                title="failed",
                status="failed",
                source_type="ingestion",
                source_id=strong.id,
            ),
            PublishJob(
                id="cancelled",
                account_id=accounts["wechat_channels"].id,
                video_path="data/strong.mp4",
                title="cancelled",
                status="cancelled",
                source_type="ingestion",
                source_id=strong.id,
            ),
        ]
    )
    session.commit()
    session.close()
    engine.dispose()
    get_data_dir.cache_clear()
    return path


def _rows(path: Path, table: str) -> list[dict]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        ]


def test_default_path_uses_data_dir_then_windows_roaming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "custom"
    monkeypatch.setenv("AINEWS_DATA_DIR", str(data))
    assert rebuild.default_database_path() == data / "ainews.db"
    monkeypatch.delenv("AINEWS_DATA_DIR")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert rebuild.default_database_path() == tmp_path / "Roaming" / "AINews" / "ainews.db"


def test_default_dry_run_is_byte_exact_read_only_and_creates_no_wal(queue_db: Path) -> None:
    before = queue_db.read_bytes()
    report = rebuild.inspect_database(queue_db, as_of=datetime(2026, 9, 13, 1, 0))
    assert queue_db.read_bytes() == before
    assert not Path(f"{queue_db}-wal").exists()
    assert not Path(f"{queue_db}-shm").exists()
    assert report["dry_run"] is True
    assert report["summary"]["scope_jobs"] == 4
    assert {item["platform"] for item in report["groups"]} == {
        "wechat_channels",
        "douyin",
        "kuaishou",
    }


def test_dry_run_imports_do_not_create_runtime_directories(queue_db: Path) -> None:
    before = sorted(path.relative_to(queue_db.parent) for path in queue_db.parent.rglob("*"))
    environment = {
        **os.environ,
        "AINEWS_DATA_DIR": str(queue_db.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(Path(rebuild.__file__).resolve()),
            "--db",
            str(queue_db),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    after = sorted(path.relative_to(queue_db.parent) for path in queue_db.parent.rglob("*"))
    assert after == before


def test_missing_database_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "ainews.db"
    with pytest.raises(FileNotFoundError):
        rebuild.inspect_database(missing)
    assert not missing.exists()
    assert not missing.parent.exists()


def test_missing_candidate_table_allows_dry_run_but_blocks_apply(
    queue_db: Path, tmp_path: Path
) -> None:
    with sqlite3.connect(queue_db) as connection:
        connection.execute("DROP TABLE auto_publish_candidates")
    before = queue_db.read_bytes()
    report = rebuild.inspect_database(queue_db, as_of=datetime(2026, 9, 13, 1, 0))
    assert report["schema_ready"] is False
    assert report["schema_warnings"] == ["missing_table:auto_publish_candidates"]
    assert "missing_table:auto_publish_candidates" in rebuild.render_human(report)
    assert all(
        group["candidate"]["id"]
        for group in report["groups"]
        if group["candidate"] is not None
    )
    with pytest.raises(rebuild.RebuildError, match="auto_publish_candidates"):
        rebuild.apply_rebuild(queue_db, tmp_path / "backup.json")
    assert queue_db.read_bytes() == before
    assert not (tmp_path / "backup.json").exists()


def test_diff_contains_scores_policy_schedule_and_staged_modes(queue_db: Path) -> None:
    report = rebuild.inspect_database(queue_db, as_of=datetime(2026, 9, 13, 1, 0))
    by_key = {(item["article_id"], item["platform"]): item for item in report["groups"]}
    strong = by_key[("article-strong", "wechat_channels")]
    assert strong["old_scores"] == {
        "industry_total": 12.0,
        "industry_grade": "D",
        "viral_total": 11.0,
        "viral_grade": "D",
    }
    assert set(strong["new_scores"]) == {
        "industry_total",
        "industry_grade",
        "viral_total",
        "viral_grade",
    }
    assert strong["policy"]["action"] in {"publish", "defer", "skip"}
    assert isinstance(strong["policy"]["priority"], float)
    assert strong["old_scheduled_at"] == "2026-09-14T01:00:00"
    assert "new_scheduled_at" in strong
    assert by_key[("article-weak", "douyin")]["mode"] == "legacy-preserve"
    assert by_key[("article-weak", "douyin")]["decision"] == "keep"
    assert by_key[("article-weak", "kuaishou")]["decision"] == "keep"
    assert by_key[("article-weak", "kuaishou")]["candidate"]["status"] == "pending"
    assert report["platform_modes"] == {
        "wechat_channels": "enforce",
        "douyin": "legacy-preserve",
        "kuaishou": "legacy-preserve",
    }
    assert report["budgets"]["douyin"] == 10
    assert report["budgets"]["kuaishou"] == 5


def test_pure_rescore_does_not_call_apply_or_enqueue(
    queue_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("side-effecting scoring/enqueue API was called")

    monkeypatch.setattr(
        "services.ingestion.score_service.apply_score_to_article", forbidden
    )
    monkeypatch.setattr(
        "services.publishing.auto_publish.create_ingestion_publish_job", forbidden
    )
    report = rebuild.inspect_database(queue_db, as_of=datetime(2026, 9, 13, 1, 0))
    strong = next(item for item in report["groups"] if item["article_id"] == "article-strong")
    inputs = strong["score_inputs"]
    assert inputs["keywords"] == ["AI", "OpenAI", "GPT-5", "大模型"]
    assert inputs["published_at"] is not None
    assert inputs["story_article_count"] == 2
    assert inputs["downloaded_image_count"] == 3


def test_apply_requires_explicit_backup(queue_db: Path) -> None:
    with pytest.raises(SystemExit):
        rebuild.main(["--db", str(queue_db), "--apply"])


def test_backup_is_complete_and_refuses_overwrite(queue_db: Path, tmp_path: Path) -> None:
    backup = tmp_path / "backup.json"
    manifest = rebuild.create_backup(
        queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0)
    )
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert saved == manifest
    assert saved["schema_version"] == rebuild.BACKUP_SCHEMA_VERSION
    assert saved["database"]["path"] == str(queue_db.resolve())
    assert "fingerprint" not in saved["database"]
    assert saved["database"]["snapshot_fingerprint"]
    assert saved["database"]["schema_fingerprint"]
    assert saved["database"]["identity"]
    assert set(saved["snapshot"]) >= {
        "jobs",
        "articles",
        "accounts",
        "story_inputs",
        "image_inputs",
        "hot_radar_inputs",
        "preexisting_candidates",
        "schema",
    }
    assert saved["required_runtime_settings"]["valid"] is True
    assert len(saved["publish_jobs"]) == 4
    assert set(saved["publish_jobs"][0]) == set(rebuild.PUBLISH_JOB_COLUMNS)
    assert len(saved["articles"]) == 2
    assert all("score_breakdown_json" in row for row in saved["articles"])
    assert saved["candidate_ids"] == sorted(saved["candidate_ids"])
    with pytest.raises(FileExistsError):
        rebuild.create_backup(queue_db, backup)


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE ingested_articles SET summary = 'changed' WHERE id = 'article-strong'",
        "UPDATE publisher_accounts SET status = 'inactive' WHERE id = 'account-douyin'",
        "UPDATE stories SET article_count = 9 WHERE id = 'story-1'",
        "UPDATE article_images SET download_status = 'failed' WHERE id = 'image-0'",
        """
        INSERT INTO auto_publish_candidates
            (id, article_id, platform, action, recommended_action, priority,
             reasons_json, policy_version, status, evaluated_at, created_at, updated_at)
        VALUES ('late-candidate', 'article-strong', 'wechat_channels', 'publish',
                'publish', 1, '[]', '1', 'pending', '2026-01-01',
                '2026-01-01', '2026-01-01')
        """,
    ],
)
def test_logical_snapshot_fingerprint_covers_all_affected_inputs(
    queue_db: Path, tmp_path: Path, mutation: str
) -> None:
    first = rebuild.create_backup(
        queue_db, tmp_path / "first.json", as_of=datetime(2026, 9, 13, 1, 0)
    )
    with sqlite3.connect(queue_db) as connection:
        connection.execute(mutation)
    second = rebuild.create_backup(
        queue_db, tmp_path / "second.json", as_of=datetime(2026, 9, 13, 1, 0)
    )
    assert (
        first["database"]["snapshot_fingerprint"]
        != second["database"]["snapshot_fingerprint"]
    )


def test_apply_rejects_complete_effective_config_change_without_mutation(
    queue_db: Path, tmp_path: Path
) -> None:
    initial = _valid_runtime_override()
    initial["view_count_tier1"] = 5000
    initial["view_count_tier2"] = 10000
    initial["unrecognized_nested_scoring_input"] = {"all": {"values": [1, 2]}}
    _write_runtime_override(queue_db, initial)
    backup = tmp_path / "backup.json"
    manifest = rebuild.create_backup(
        queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0)
    )
    assert manifest["snapshot"]["scoring_config"]["view_count_tier1"] == 5000
    assert manifest["snapshot"]["scoring_config"]["view_count_tier2"] == 10000
    before = {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    }
    override = _valid_runtime_override()
    override["view_count_tier1"] = 123
    override["view_count_tier2"] = 456
    override["unrecognized_nested_scoring_input"] = {"all": {"values": [1, 2, 3]}}
    _write_runtime_override(queue_db, override)

    with pytest.raises(rebuild.DatabaseChangedError, match="logical snapshot"):
        rebuild.apply_rebuild(queue_db, backup)

    assert {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    } == before


@pytest.mark.parametrize(
    ("article_updates", "expected_reason"),
    [
        ({"generated_video_path": None}, "generated_video_path_missing"),
        (
            {"generated_video_path": "data/videos/does-not-exist.mp4"},
            "generated_video_file_missing",
        ),
        ({"video_draft_json": "{not-json"}, "video_draft_malformed"),
    ],
)
def test_unsafe_legacy_media_keeps_existing_job_without_candidate(
    queue_db: Path,
    article_updates: dict[str, str | None],
    expected_reason: str,
) -> None:
    assignments = ", ".join(f"{column} = ?" for column in article_updates)
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            f"UPDATE ingested_articles SET {assignments} WHERE id = ?",
            (*article_updates.values(), "article-weak"),
        )

    report = rebuild.inspect_database(
        queue_db, as_of=datetime(2026, 9, 13, 1, 0)
    )
    legacy = [
        group
        for group in report["groups"]
        if group["article_id"] == "article-weak"
        and group["platform"] in {"douyin", "kuaishou"}
    ]
    assert len(legacy) == 2
    assert all(group["decision"] == "keep-existing-job" for group in legacy)
    assert all(group["candidate"] is None for group in legacy)
    assert all(expected_reason in group["errors"] for group in legacy)
    assert all(group["replacement_safe"] is False for group in legacy)
    rendered = rebuild.render_human(report)
    assert "keep-existing-job" in rendered
    assert expected_reason in rendered


def test_apply_leaves_unsafe_legacy_jobs_untouched(
    queue_db: Path, tmp_path: Path
) -> None:
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            """
            UPDATE ingested_articles
            SET generated_video_path = 'data/videos/missing.mp4'
            WHERE id = 'article-weak'
            """
        )
    original_jobs = {
        row["id"]: row for row in _rows(queue_db, "publish_jobs")
        if row["id"] in {"douyin-weak", "kuaishou-weak"}
    }

    rebuild.apply_rebuild(
        queue_db, tmp_path / "backup.json", as_of=datetime(2026, 9, 13, 1, 0)
    )

    jobs = {row["id"]: row for row in _rows(queue_db, "publish_jobs")}
    assert {job_id: jobs[job_id] for job_id in original_jobs} == original_jobs
    candidates = _rows(queue_db, "auto_publish_candidates")
    assert not any(
        row["article_id"] == "article-weak"
        and row["platform"] in {"douyin", "kuaishou"}
        for row in candidates
    )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("generated_video_path", "data/videos/replaced.mp4"),
        ("generated_cover_path", "data/publish/covers/replaced.png"),
        ("video_draft_json", '{"main_line1":"changed"}'),
    ],
)
def test_article_dispatch_input_change_after_backup_rejects_apply(
    queue_db: Path, tmp_path: Path, column: str, value: str
) -> None:
    backup = tmp_path / "backup.json"
    manifest = rebuild.create_backup(
        queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0)
    )
    article = next(
        row for row in manifest["snapshot"]["articles"]
        if row["id"] == "article-weak"
    )
    assert set(article) >= {
        "generated_video_path",
        "generated_cover_path",
        "video_draft_json",
    }
    before_jobs = _rows(queue_db, "publish_jobs")
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            f"UPDATE ingested_articles SET {column} = ? WHERE id = 'article-weak'",
            (value,),
        )

    with pytest.raises(rebuild.DatabaseChangedError, match="logical snapshot"):
        rebuild.apply_rebuild(queue_db, backup)
    assert _rows(queue_db, "publish_jobs") == before_jobs


def test_video_file_removed_after_backup_rejects_apply(
    queue_db: Path, tmp_path: Path
) -> None:
    backup = tmp_path / "backup.json"
    rebuild.create_backup(
        queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0)
    )
    before_jobs = _rows(queue_db, "publish_jobs")
    (queue_db.parent / "videos" / "article-weak.mp4").unlink()

    with pytest.raises(rebuild.DatabaseChangedError, match="logical snapshot"):
        rebuild.apply_rebuild(queue_db, backup)
    assert _rows(queue_db, "publish_jobs") == before_jobs


def test_valid_absolute_video_and_exact_restore_preserve_dispatch_inputs(
    queue_db: Path, tmp_path: Path
) -> None:
    video = queue_db.parent / "videos" / "absolute.mp4"
    video.write_bytes(b"absolute-video")
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            """
            UPDATE ingested_articles
            SET generated_video_path = ?,
                generated_cover_path = NULL,
                video_draft_json = ?
            WHERE id = 'article-weak'
            """,
            (str(video.resolve()), '{"main_line1":"usable draft"}'),
        )
    dispatch_inputs_before = {
        row["id"]: (
            row["generated_video_path"],
            row["generated_cover_path"],
            row["video_draft_json"],
        )
        for row in _rows(queue_db, "ingested_articles")
    }
    backup = tmp_path / "backup.json"

    report = rebuild.inspect_database(
        queue_db, as_of=datetime(2026, 9, 13, 1, 0)
    )
    assert all(
        group["replacement_safe"] is True
        for group in report["groups"]
        if group["article_id"] == "article-weak"
        and group["platform"] in {"douyin", "kuaishou"}
    )
    rebuild.apply_rebuild(
        queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0)
    )
    rebuild.restore_backup(queue_db, backup)

    dispatch_inputs_after = {
        row["id"]: (
            row["generated_video_path"],
            row["generated_cover_path"],
            row["video_draft_json"],
        )
        for row in _rows(queue_db, "ingested_articles")
    }
    assert dispatch_inputs_after == dispatch_inputs_before


def test_logical_snapshot_fingerprint_covers_stored_radar(
    queue_db: Path, tmp_path: Path
) -> None:
    first = rebuild.create_backup(
        queue_db, tmp_path / "first.json", as_of=datetime(2026, 9, 13, 1, 0)
    )
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            """
            INSERT INTO hot_radar_snapshots
                (id, source, board, fetched_at, item_count)
            VALUES ('snapshot-1', 'tophub', 'ai', '2026-09-13', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO hot_radar_article_matches
                (id, article_id, snapshot_id, board_hashid, board_id, rank,
                 effective_rank, confidence, match_method, hot_title, hot_url,
                 matched_at)
            VALUES ('match-1', 'article-strong', 'snapshot-1', 'board', 'board',
                    1, 1, 0.9, 'title', 'hot', 'https://hot', '2026-09-13')
            """
        )
    second = rebuild.create_backup(
        queue_db, tmp_path / "second.json", as_of=datetime(2026, 9, 13, 1, 0)
    )
    assert (
        first["database"]["snapshot_fingerprint"]
        != second["database"]["snapshot_fingerprint"]
    )


def test_logical_snapshot_includes_recent_story_peer_timestamps(
    queue_db: Path, tmp_path: Path
) -> None:
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            """
            INSERT INTO ingested_articles
                (id, source_id, canonical_url, title, keywords_json, tags_json, status,
                 story_id, created_at)
            VALUES ('story-peer', 'source-1', 'https://example.com/peer', 'peer',
                    '[]', '[]', 'fetched', 'story-1', '2026-09-13T00:30:00')
            """
        )
    first = rebuild.create_backup(
        queue_db, tmp_path / "first.json", as_of=datetime(2026, 9, 13, 1, 0)
    )
    assert first["snapshot"]["story_inputs"]["recent_article_peers"] == [
        {
            "id": "story-peer",
            "story_id": "story-1",
            "created_at": "2026-09-13T00:30:00",
        },
        {
            "id": "article-strong",
            "story_id": "story-1",
            "created_at": first["snapshot"]["story_inputs"]["recent_article_peers"][1][
                "created_at"
            ],
        },
    ]
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            "UPDATE ingested_articles SET created_at = ? WHERE id = ?",
            ("2026-09-10T00:00:00", "story-peer"),
        )
    second = rebuild.create_backup(
        queue_db, tmp_path / "second.json", as_of=datetime(2026, 9, 13, 1, 0)
    )
    assert (
        first["database"]["snapshot_fingerprint"]
        != second["database"]["snapshot_fingerprint"]
    )


def test_active_wal_input_change_is_detected_without_main_file_change(
    queue_db: Path, tmp_path: Path
) -> None:
    with sqlite3.connect(queue_db) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    backup = tmp_path / "backup.json"
    rebuild.create_backup(queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0))
    main_before = queue_db.read_bytes()
    writer = sqlite3.connect(queue_db)
    try:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(
            "UPDATE ingested_articles SET summary = ? WHERE id = ?",
            ("changed only in wal", "article-strong"),
        )
        writer.commit()
        assert queue_db.read_bytes() == main_before
        with pytest.raises(rebuild.DatabaseChangedError, match="logical snapshot"):
            rebuild.apply_rebuild(queue_db, backup)
    finally:
        writer.close()


def test_checkpoint_after_backup_does_not_cause_false_rejection(
    queue_db: Path, tmp_path: Path
) -> None:
    writer = sqlite3.connect(queue_db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute(
        "UPDATE ingested_articles SET summary = 'checkpointed' WHERE id = 'article-strong'"
    )
    writer.commit()
    backup = tmp_path / "backup.json"
    rebuild.create_backup(queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0))
    before_checkpoint = queue_db.read_bytes()
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    writer.close()
    assert queue_db.read_bytes() != before_checkpoint
    result = rebuild.apply_rebuild(queue_db, backup)
    assert result["applied"] is True


def test_incompatible_schema_rejected_before_backup_or_mutation(
    queue_db: Path, tmp_path: Path
) -> None:
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            "ALTER TABLE auto_publish_candidates RENAME COLUMN priority TO priority_old"
        )
    before = queue_db.read_bytes()
    backup = tmp_path / "backup.json"
    with pytest.raises(rebuild.IncompatibleSchemaError, match="priority"):
        rebuild.apply_rebuild(queue_db, backup)
    assert queue_db.read_bytes() == before
    assert not backup.exists()


def test_database_replacement_at_same_path_is_rejected(
    queue_db: Path, tmp_path: Path
) -> None:
    backup = tmp_path / "backup.json"
    rebuild.create_backup(queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0))
    replacement = tmp_path / "replacement.db"
    engine = create_engine(f"sqlite:///{replacement.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()
    queue_db.unlink()
    replacement.replace(queue_db)
    with pytest.raises(rebuild.DatabaseIdentityError):
        rebuild.apply_rebuild(queue_db, backup)


def test_backup_publish_loses_race_without_overwriting_winner(
    queue_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = tmp_path / "backup.json"
    original_publish = getattr(rebuild, "_publish_temp_exclusive", None)

    def race(source, target):
        Path(target).write_text("winner", encoding="utf-8")
        return original_publish(source, target)

    monkeypatch.setattr(rebuild, "_publish_temp_exclusive", race, raising=False)
    with pytest.raises(FileExistsError):
        rebuild.create_backup(queue_db, backup)
    assert backup.read_text(encoding="utf-8") == "winner"


def test_windows_publication_uses_write_through_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"complete")
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(rebuild.os, "name", "nt")
    monkeypatch.setattr(
        rebuild,
        "_move_windows_exclusive_write_through",
        lambda src, dst: calls.append((Path(src), Path(dst))),
        raising=False,
    )
    rebuild._publish_temp_exclusive(source, target)
    assert calls == [(source, target)]


def test_aware_and_naive_equivalent_instants_score_identically(queue_db: Path) -> None:
    utc = timezone.utc
    plus_eight = timezone(timedelta(hours=8))
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            "UPDATE ingested_articles SET published_at = ? WHERE id = ?",
            ("2026-09-12T23:00:00+00:00", "article-strong"),
        )
    first = rebuild.inspect_database(
        queue_db, as_of=datetime(2026, 9, 13, 1, 0, tzinfo=utc)
    )
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            "UPDATE ingested_articles SET published_at = ? WHERE id = ?",
            ("2026-09-13T07:00:00+08:00", "article-strong"),
        )
    second = rebuild.inspect_database(
        queue_db, as_of=datetime(2026, 9, 13, 9, 0, tzinfo=plus_eight)
    )
    first_group = next(
        group for group in first["groups"] if group["article_id"] == "article-strong"
    )
    second_group = next(
        group for group in second["groups"] if group["article_id"] == "article-strong"
    )
    assert first["evaluated_at"] == second["evaluated_at"] == "2026-09-13T01:00:00"
    assert first_group["new_scores"] == second_group["new_scores"]
    assert first_group["score_inputs"]["published_at"] == second_group["score_inputs"]["published_at"]


def test_disabled_runtime_policy_refuses_apply_without_backup_or_db_change(
    queue_db: Path, tmp_path: Path
) -> None:
    _write_runtime_override(
        queue_db,
        {"publish_policy": {"enabled": False}},
    )
    before = {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    }
    backup = tmp_path / "backup.json"
    with pytest.raises(rebuild.RuntimePolicyError, match="publish_policy.enabled"):
        rebuild.apply_rebuild(queue_db, backup)
    assert not backup.exists()
    assert {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    } == before


def test_malformed_runtime_budget_is_actionable_policy_error(
    queue_db: Path, tmp_path: Path
) -> None:
    override = _valid_runtime_override()
    override["publish_policy"]["platforms"]["douyin"]["daily_limit"] = "bad"
    _write_runtime_override(queue_db, override)
    with pytest.raises(rebuild.RuntimePolicyError, match="douyin.daily_limit"):
        rebuild.apply_rebuild(queue_db, tmp_path / "backup.json")
    assert not (tmp_path / "backup.json").exists()


def test_existing_current_policy_candidate_is_updated_and_restored_exactly(
    queue_db: Path, tmp_path: Path
) -> None:
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            """
            INSERT INTO auto_publish_candidates
                (id, article_id, platform, action, recommended_action, priority,
                 reasons_json, policy_version, status, evaluated_at, scheduled_date,
                 publish_job_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "existing-current-policy",
                "article-strong",
                "wechat_channels",
                "defer",
                "defer",
                1.5,
                '["original"]',
                "1",
                "deferred",
                "2026-01-01 00:00:00",
                None,
                None,
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
    before = _rows(queue_db, "auto_publish_candidates")
    report = rebuild.inspect_database(queue_db, as_of=datetime(2026, 9, 13, 1, 0))
    group = next(
        item
        for item in report["groups"]
        if item["article_id"] == "article-strong"
        and item["platform"] == "wechat_channels"
    )
    assert group["candidate"]["policy_version"] == "1"
    assert group["candidate"]["id"] == "existing-current-policy"

    backup = tmp_path / "backup.json"
    rebuild.apply_rebuild(queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0))
    assert len(_rows(queue_db, "auto_publish_candidates")) == 4
    manifest = json.loads(backup.read_text(encoding="utf-8"))
    assert manifest["preexisting_candidates"] == before
    rebuild.restore_backup(queue_db, backup)
    assert _rows(queue_db, "auto_publish_candidates") == before


def test_apply_scopes_jobs_updates_scores_and_only_queues_candidates(
    queue_db: Path, tmp_path: Path
) -> None:
    backup = tmp_path / "backup.json"
    result = rebuild.apply_rebuild(
        queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0)
    )
    assert result["applied"] is True
    jobs = {row["id"]: row for row in _rows(queue_db, "publish_jobs")}
    assert {jobs[job_id]["status"] for job_id in (
        "wechat-strong", "wechat-weak", "douyin-weak", "kuaishou-weak"
    )} == {"cancelled"}
    assert jobs["uploading"]["status"] == "uploading"
    assert jobs["manual"]["status"] == "pending"
    assert jobs["published"]["status"] == "published"
    assert jobs["failed"]["status"] == "failed"
    assert jobs["cancelled"]["status"] == "cancelled"
    candidates = _rows(queue_db, "auto_publish_candidates")
    assert len(candidates) == 4
    assert all(row["publish_job_id"] is None for row in candidates)
    assert all(row["scheduled_date"] is None for row in candidates)
    by_platform = {row["platform"]: row for row in candidates if row["article_id"] == "article-weak"}
    assert by_platform["douyin"]["status"] == "pending"
    assert by_platform["kuaishou"]["status"] == "pending"
    assert by_platform["kuaishou"]["action"] == "publish"
    articles = {row["id"]: row for row in _rows(queue_db, "ingested_articles")}
    assert articles["article-strong"]["score_total"] != 12.0


def test_valid_runtime_policy_candidates_dispatch_with_real_budgets(
    queue_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.publishing.candidate_queue import dispatch_daily_candidates
    from src.utils.paths import get_data_dir

    monkeypatch.setenv("AINEWS_DATA_DIR", str(queue_db.parent))
    get_data_dir.cache_clear()
    monkeypatch.setattr(
        "services.publishing.candidate_queue.eligible_video_platform_ids",
        lambda: ["wechat_channels", "douyin", "kuaishou"],
    )
    rebuild.apply_rebuild(
        queue_db,
        tmp_path / "backup.json",
        as_of=datetime(2026, 9, 13, 0, 0),
    )
    config = rebuild._load_scoring_config_read_only(queue_db)
    assert {
        platform: config["publish_policy"]["platforms"][platform]["daily_limit"]
        for platform in ("wechat_channels", "douyin", "kuaishou")
    } == {"wechat_channels": 8, "douyin": 10, "kuaishou": 5}

    engine = create_engine(f"sqlite:///{queue_db.as_posix()}")
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        result = dispatch_daily_candidates(
            session,
            now=datetime(2026, 9, 13, 0, 0),
            config=config,
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()
        get_data_dir.cache_clear()

    dispatched_platforms = [item["platform"] for item in result["dispatched"]]
    assert dispatched_platforms
    assert dispatched_platforms.count("wechat_channels") <= 8
    assert dispatched_platforms.count("douyin") <= 10
    assert dispatched_platforms.count("kuaishou") <= 5
    assert {"douyin", "kuaishou"} <= set(dispatched_platforms)


def test_mid_transaction_failure_rolls_back_every_change(
    queue_db: Path, tmp_path: Path
) -> None:
    before = {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    }

    def fail(phase: str) -> None:
        if phase == "after_job_cancellation":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        rebuild.apply_rebuild(
            queue_db,
            tmp_path / "backup.json",
            as_of=datetime(2026, 9, 13, 1, 0),
            failure_hook=fail,
        )
    assert {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    } == before


def test_repeat_apply_with_same_backup_is_idempotent(queue_db: Path, tmp_path: Path) -> None:
    backup = tmp_path / "backup.json"
    rebuild.apply_rebuild(queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0))
    once = {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    }
    result = rebuild.apply_rebuild(
        queue_db, backup, as_of=datetime(2026, 9, 13, 2, 0)
    )
    assert result["already_applied"] is True
    assert {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    } == once


def test_restore_is_exact_scoped_and_repeat_safe(queue_db: Path, tmp_path: Path) -> None:
    backup = tmp_path / "backup.json"
    before = {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    }
    rebuild.apply_rebuild(queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0))
    restored = rebuild.restore_backup(queue_db, backup)
    assert restored["restored"] is True
    assert {
        table: _rows(queue_db, table)
        for table in ("publish_jobs", "ingested_articles", "auto_publish_candidates")
    } == before
    again = rebuild.restore_backup(queue_db, backup)
    assert again["already_restored"] is True


def test_apply_rejects_scope_drift_and_restore_rejects_wrong_database(
    queue_db: Path, tmp_path: Path
) -> None:
    backup = tmp_path / "backup.json"
    rebuild.create_backup(queue_db, backup, as_of=datetime(2026, 9, 13, 1, 0))
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            "UPDATE publish_jobs SET scheduled_at = ? WHERE id = ?",
            ("2030-01-01 00:00:00", "wechat-strong"),
        )
    with pytest.raises(rebuild.DatabaseChangedError):
        rebuild.apply_rebuild(queue_db, backup)

    other = tmp_path / "other.db"
    other.write_bytes(queue_db.read_bytes())
    with pytest.raises(rebuild.DatabaseIdentityError):
        rebuild.restore_backup(other, backup)


def test_missing_article_or_account_is_deferred_without_losing_job(
    queue_db: Path, tmp_path: Path
) -> None:
    with sqlite3.connect(queue_db) as connection:
        connection.execute(
            """
            INSERT INTO publish_jobs
                (id, account_id, video_path, title, status, retry_count, source_type,
                 source_id, created_at, tags_json, comment_status, comment_retry_count)
            VALUES (?, ?, ?, ?, 'pending', 0, 'ingestion', ?, ?, '[]', 'none', 0)
            """,
            (
                "missing-article",
                "account-wechat_channels",
                "data/missing.mp4",
                "missing",
                "no-such-article",
                "2026-09-13 00:00:00",
            ),
        )
        connection.execute(
            "DELETE FROM publisher_accounts WHERE id = 'account-douyin'"
        )
    report = rebuild.inspect_database(queue_db, as_of=datetime(2026, 9, 13, 1, 0))
    invalid = [item for item in report["groups"] if item["valid"] is False]
    assert invalid
    assert all(item["decision"] == "defer" for item in invalid)
    rebuild.apply_rebuild(
        queue_db, tmp_path / "backup.json", as_of=datetime(2026, 9, 13, 1, 0)
    )
    jobs = {row["id"]: row for row in _rows(queue_db, "publish_jobs")}
    assert jobs["missing-article"]["status"] == "pending"
    assert jobs["douyin-weak"]["status"] == "pending"


def test_restore_cli_mode_is_mutually_exclusive_with_apply(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        rebuild.build_parser().parse_args(
            ["--apply", "--backup", str(tmp_path / "b.json"), "--restore", str(tmp_path / "b.json")]
        )
