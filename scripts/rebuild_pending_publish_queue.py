"""Safely rebuild pending ingestion publish jobs into policy candidates.

The default mode is a read-only inspection.  Mutating modes require an
explicit backup manifest and never dispatch publishing work.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import sqlite3
import sys
import tempfile
import types
from collections import Counter
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Iterator

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.industry.constants import DEFAULT_INDUSTRY_ID

BACKUP_SCHEMA_VERSION = 2
REBUILD_POLICY_VERSION = "pending-ingestion-rebuild-v1"
SUPPORTED_PLATFORMS = ("wechat_channels", "douyin", "kuaishou")
PLATFORM_MODES = {
    "wechat_channels": "enforce",
    "douyin": "legacy-preserve",
    "kuaishou": "legacy-preserve",
}
PLATFORM_BUDGETS = {"wechat_channels": 8, "douyin": 10, "kuaishou": 5}

PUBLISH_JOB_COLUMNS = (
    "id",
    "account_id",
    "video_path",
    "title",
    "description",
    "tags_json",
    "cover_path",
    "status",
    "platform_post_id",
    "platform_post_url",
    "metrics_match_status",
    "metrics_last_synced_at",
    "error_message",
    "retry_count",
    "source_type",
    "source_id",
    "created_at",
    "started_at",
    "finished_at",
    "published_at",
    "scheduled_at",
    "first_comment_text",
    "comment_status",
    "comment_posted_at",
    "comment_error_message",
    "comment_retry_count",
)
CANDIDATE_COLUMNS = (
    "id",
    "article_id",
    "platform",
    "action",
    "recommended_action",
    "priority",
    "reasons_json",
    "policy_version",
    "status",
    "evaluated_at",
    "scheduled_date",
    "publish_job_id",
    "created_at",
    "updated_at",
    "industry_id",
)
ARTICLE_SCORE_COLUMNS = (
    "id",
    "score_total",
    "score_grade",
    "score_breakdown_json",
    "score_comment",
    "scored_at",
)
ARTICLE_INPUT_COLUMNS = (
    "id",
    "source_id",
    "canonical_url",
    "title",
    "summary",
    "published_at",
    "content_text",
    "keywords_json",
    "view_count",
    "story_id",
    "created_at",
    "generated_video_path",
    "generated_cover_path",
    "video_draft_json",
    *ARTICLE_SCORE_COLUMNS[1:],
)
ACCOUNT_INPUT_COLUMNS = ("id", "platform", "status")
REQUIRED_SCHEMA: dict[str, tuple[str, ...]] = {
    "publish_jobs": PUBLISH_JOB_COLUMNS,
    "publisher_accounts": ACCOUNT_INPUT_COLUMNS,
    "ingested_articles": ARTICLE_INPUT_COLUMNS,
    "article_images": ("id", "article_id", "download_status"),
    "stories": ("id", "article_count"),
    "story_articles": ("id", "story_id", "article_id"),
    "hot_radar_article_matches": (
        "id",
        "article_id",
        "snapshot_id",
        "board_hashid",
        "board_id",
        "rank",
        "effective_rank",
        "confidence",
        "match_method",
        "heat_label",
        "heat_value",
        "hot_title",
        "hot_url",
        "inherited_from_article_id",
        "matched_at",
        "industry_id",
    ),
    "auto_publish_candidates": CANDIDATE_COLUMNS,
    "ingestion_sources": ("id", "slug", "adapter_class"),
}

FailureHook = Callable[[str], None]


class RebuildError(RuntimeError):
    """Base class for safe rebuild failures."""


class DatabaseChangedError(RebuildError):
    """Raised when the database changed after the backup was prepared."""


class DatabaseIdentityError(RebuildError):
    """Raised when a backup belongs to another database path."""


class IncompatibleSchemaError(RebuildError):
    """Raised when required queue rebuild schema is absent or incompatible."""


class RuntimePolicyError(RebuildError):
    """Raised when persisted rollout settings cannot dispatch rebuilt candidates."""


def default_database_path() -> Path:
    """Resolve the desktop database path without creating any path."""
    data_dir = os.getenv("AINEWS_DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir).expanduser() / "ainews.db"
    roaming = os.getenv("APPDATA", "").strip()
    root = Path(roaming).expanduser() if roaming else Path.home() / "AppData" / "Roaming"
    return root / "AINews" / "ainews.db"


def _resolved_database_path(db_path: str | Path) -> Path:
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"database does not exist: {path}")
    return path


def _readonly_connection(db_path: str | Path) -> sqlite3.Connection:
    path = _resolved_database_path(db_path)
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _writable_connection(db_path: str | Path) -> sqlite3.Connection:
    path = _resolved_database_path(db_path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _logical_fingerprint(value: Any) -> str:
    payload = _canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, Path)):
        return value.isoformat() if not isinstance(value, Path) else str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return value if isinstance(value, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _load_scoring_config_read_only(db_path: Path) -> dict[str, Any]:
    """Read base and runtime overrides without invoking migration-on-read loaders."""
    config = _deep_merge(
        _load_yaml(ROOT / "config" / "article_scoring.yaml"),
        _load_yaml(db_path.parent / "config" / "article_scoring.local.yaml"),
    )
    radar = _deep_merge(
        _load_yaml(ROOT / "config" / "hot_radar.yaml"),
        _load_yaml(db_path.parent / "config" / "hot_radar.local.yaml"),
    )
    if radar.get("enabled", True):
        config["hot_radar"] = radar
    else:
        weights = dict(config.get("weights") or {})
        weights["hot_radar"] = 0.0
        config["weights"] = weights
    return config


@contextmanager
def _suppress_runtime_directory_creation() -> Iterator[None]:
    """Prevent Config's import-time directory bootstrap in read-only tooling."""
    if "src.utils.paths" not in sys.modules and "src.utils" not in sys.modules:
        import src

        package = types.ModuleType("src.utils")
        package.__path__ = [str(ROOT / "src" / "utils")]
        package.__package__ = "src.utils"
        sys.modules["src.utils"] = package
        setattr(src, "utils", package)
    runtime_paths = importlib.import_module("src.utils.paths")

    original = runtime_paths.ensure_runtime_dirs
    runtime_paths.ensure_runtime_dirs = lambda: None
    try:
        yield
    finally:
        runtime_paths.ensure_runtime_dirs = original


def _staged_policy_config(config: dict[str, Any]) -> dict[str, Any]:
    staged = copy.deepcopy(config)
    policy = staged.setdefault("publish_policy", {})
    policy["enabled"] = True
    policy["shadow_mode"] = False
    platforms = policy.setdefault("platforms", {})
    for platform in SUPPORTED_PLATFORMS:
        settings = platforms.setdefault(platform, {})
        settings["enabled"] = True
        settings["daily_limit"] = PLATFORM_BUDGETS[platform]
    platforms["wechat_channels"]["shadow_mode"] = False
    platforms["douyin"]["shadow_mode"] = True
    platforms["kuaishou"]["shadow_mode"] = True
    platforms["kuaishou"]["paused"] = False
    platforms["kuaishou"]["pause_windows"] = []
    return staged


def _required_runtime_settings(config: dict[str, Any]) -> dict[str, Any]:
    policy = config.get("publish_policy") or {}
    platforms = policy.get("platforms") or {}
    errors: list[str] = []

    def require(condition: bool, setting: str, expected: Any, actual: Any) -> None:
        if not condition:
            errors.append(f"{setting} must be {expected!r}; found {actual!r}")

    require(
        policy.get("enabled") is True,
        "publish_policy.enabled",
        True,
        policy.get("enabled"),
    )
    require(
        policy.get("shadow_mode") is False,
        "publish_policy.shadow_mode",
        False,
        policy.get("shadow_mode"),
    )
    for platform in SUPPORTED_PLATFORMS:
        settings = platforms.get(platform) or {}
        require(
            settings.get("enabled") is True,
            f"publish_policy.platforms.{platform}.enabled",
            True,
            settings.get("enabled"),
        )
        expected_shadow = platform != "wechat_channels"
        require(
            settings.get("shadow_mode") is expected_shadow,
            f"publish_policy.platforms.{platform}.shadow_mode",
            expected_shadow,
            settings.get("shadow_mode"),
        )
        raw_limit = settings.get("daily_limit")
        try:
            normalized_limit = int(raw_limit)
        except (TypeError, ValueError):
            normalized_limit = -1
        require(
            normalized_limit == PLATFORM_BUDGETS[platform],
            f"publish_policy.platforms.{platform}.daily_limit",
            PLATFORM_BUDGETS[platform],
            raw_limit,
        )
    kuaishou = platforms.get("kuaishou") or {}
    require(
        kuaishou.get("paused", False) is False,
        "publish_policy.platforms.kuaishou.paused",
        False,
        kuaishou.get("paused"),
    )
    require(
        not (kuaishou.get("pause_windows") or kuaishou.get("pause_window")),
        "publish_policy.platforms.kuaishou.pause_windows",
        [],
        kuaishou.get("pause_windows") or kuaishou.get("pause_window"),
    )
    return {
        "valid": not errors,
        "errors": errors,
        "required": {
            "enabled": True,
            "global_shadow_mode": False,
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
        },
        "actual": {
            "enabled": policy.get("enabled"),
            "global_shadow_mode": policy.get("shadow_mode"),
            "policy_version": policy.get("policy_version"),
            "platforms": {
                platform: {
                    key: (platforms.get(platform) or {}).get(key)
                    for key in (
                        "enabled",
                        "shadow_mode",
                        "daily_limit",
                        "paused",
                        "pause_windows",
                    )
                }
                for platform in SUPPORTED_PLATFORMS
            },
        },
    }


def _require_runtime_settings(settings: dict[str, Any]) -> None:
    if not settings["valid"]:
        raise RuntimePolicyError(
            "persist Task 8 staged publish_policy before --apply: "
            + "; ".join(settings["errors"])
        )


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _schema_snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for table in sorted(REQUIRED_SCHEMA):
        sql_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if sql_row is None:
            tables[table] = {"missing": True, "columns": []}
            continue
        columns = [
            {
                "cid": int(row["cid"]),
                "name": str(row["name"]),
                "type": str(row["type"] or ""),
                "notnull": int(row["notnull"]),
                "default": row["dflt_value"],
                "pk": int(row["pk"]),
            }
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        tables[table] = {
            "missing": False,
            "sql": str(sql_row["sql"] or ""),
            "columns": columns,
        }
    return {
        "tables": tables,
        "metadata": {
            "application_id": int(connection.execute("PRAGMA application_id").fetchone()[0]),
            "user_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
            "encoding": str(connection.execute("PRAGMA encoding").fetchone()[0]),
            "page_size": int(connection.execute("PRAGMA page_size").fetchone()[0]),
        },
    }


def _schema_problems(schema: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for table, required_columns in REQUIRED_SCHEMA.items():
        table_schema = schema["tables"].get(table) or {"missing": True}
        if table_schema.get("missing"):
            problems.append(f"missing_table:{table}")
            continue
        actual = {
            str(column["name"]) for column in table_schema.get("columns") or []
        }
        for column in required_columns:
            if column not in actual:
                problems.append(f"missing_column:{table}.{column}")
    return problems


def _validate_schema(
    connection: sqlite3.Connection,
    *,
    allow_missing_candidate_table: bool,
) -> tuple[dict[str, Any], list[str]]:
    schema = _schema_snapshot(connection)
    problems = _schema_problems(schema)
    allowed = {"missing_table:auto_publish_candidates"} if allow_missing_candidate_table else set()
    fatal = [problem for problem in problems if problem not in allowed]
    if fatal:
        raise IncompatibleSchemaError(
            "incompatible rebuild schema: " + ", ".join(fatal)
        )
    return schema, problems


def _database_anchor(connection: sqlite3.Connection) -> dict[str, Any]:
    sources = _select_dicts(
        connection,
        """
        SELECT id, slug, adapter_class
        FROM ingestion_sources
        ORDER BY id
        """,
    )
    earliest_article = connection.execute(
        """
        SELECT id, source_id, canonical_url, created_at
        FROM ingested_articles
        ORDER BY created_at, id
        LIMIT 1
        """
    ).fetchone()
    return {
        "sources": sources,
        "earliest_article": dict(earliest_article) if earliest_article is not None else None,
    }


def _database_identity(
    connection: sqlite3.Connection,
    path: Path,
    schema: dict[str, Any],
) -> str:
    identity = {
        "path": os.path.normcase(str(path.resolve())),
        "schema_fingerprint": _logical_fingerprint(schema),
        "metadata": schema["metadata"],
        "logical_anchor": _database_anchor(connection),
    }
    return _logical_fingerprint(identity)


def _select_dicts(
    connection: sqlite3.Connection,
    query: str,
    parameters: Iterable[Any] = (),
) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, tuple(parameters)).fetchall()]


def _in_scope_jobs(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    columns = ", ".join(f"j.{column}" for column in PUBLISH_JOB_COLUMNS)
    return _select_dicts(
        connection,
        f"""
        SELECT {columns},
               a.platform AS account_platform,
               a.status AS account_status,
               a.id AS resolved_account_id
        FROM publish_jobs AS j
        LEFT JOIN publisher_accounts AS a ON a.id = j.account_id
        WHERE j.status = 'pending' AND j.source_type = 'ingestion'
        ORDER BY j.source_id, a.platform, j.id
        """,
    )


def _job_original(row: dict[str, Any]) -> dict[str, Any]:
    return {column: row.get(column) for column in PUBLISH_JOB_COLUMNS}


def _article_row(
    connection: sqlite3.Connection, article_id: str | None
) -> dict[str, Any] | None:
    if not article_id:
        return None
    row = connection.execute(
        "SELECT * FROM ingested_articles WHERE id = ?", (article_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def _parse_json_list(value: Any) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_json_dict(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return _utc_naive(parsed)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _story_article_count(
    connection: sqlite3.Connection, article: dict[str, Any]
) -> int:
    story_id = article.get("story_id")
    if not story_id:
        return 1
    story = connection.execute(
        "SELECT article_count FROM stories WHERE id = ?", (story_id,)
    ).fetchone()
    if story is not None and int(story["article_count"] or 0) > 0:
        return int(story["article_count"])
    count = connection.execute(
        "SELECT COUNT(*) FROM story_articles WHERE story_id = ?", (story_id,)
    ).fetchone()[0]
    return int(count or 1)


def _recent_story_count(
    connection: sqlite3.Connection,
    article: dict[str, Any],
    *,
    as_of: datetime,
) -> int:
    story_id = article.get("story_id")
    if not story_id:
        return 0
    return int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM ingested_articles
            WHERE story_id = ? AND id != ?
              AND datetime(created_at) >= datetime(?, '-24 hours')
              AND datetime(created_at) <= datetime(?)
            """,
            (story_id, article["id"], as_of.isoformat(), as_of.isoformat()),
        ).fetchone()[0]
        or 0
    )


def _downloaded_image_count(
    connection: sqlite3.Connection, article_id: str
) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(*) FROM article_images
            WHERE article_id = ? AND download_status = 'ok'
            """,
            (article_id,),
        ).fetchone()[0]
        or 0
    )


def _persisted_hot_radar(
    connection: sqlite3.Connection, article_id: str
) -> tuple[Any | None, dict[str, Any] | None]:
    if not _table_exists(connection, "hot_radar_article_matches"):
        return None, None
    row = connection.execute(
        """
        SELECT *
        FROM hot_radar_article_matches
        WHERE article_id = ?
        ORDER BY confidence DESC, effective_rank ASC, id ASC
        LIMIT 1
        """,
        (article_id,),
    ).fetchone()
    if row is None:
        return None, None
    raw = dict(row)
    payload = {
        "rank": raw.get("rank"),
        "effective_rank": raw.get("effective_rank") or raw.get("rank"),
        "confidence": raw.get("confidence"),
        "heat_label": raw.get("heat_label"),
        "heat_value": raw.get("heat_value"),
        "hot_title": raw.get("hot_title"),
        "hot_url": raw.get("hot_url"),
        "match_method": raw.get("match_method"),
        "board": raw.get("board_hashid"),
        "board_id": raw.get("board_id"),
        "source": "tophub",
        "inherited_from_article_id": raw.get("inherited_from_article_id"),
    }
    return SimpleNamespace(**payload), payload


@contextmanager
def _scoring_clock(as_of: datetime) -> Iterator[None]:
    from services.ingestion import article_scorer

    original = article_scorer.datetime

    class FixedDateTime(datetime):
        @classmethod
        def utcnow(cls) -> datetime:
            return _utc_naive(as_of)

    article_scorer.datetime = FixedDateTime
    try:
        yield
    finally:
        article_scorer.datetime = original


def _prominence_score(industry_result: Any) -> float:
    for dimension in industry_result.dimensions:
        if dimension.key == "prominence":
            return float(dimension.score)
    return 0.0


def _pure_rescore(
    connection: sqlite3.Connection,
    article: dict[str, Any],
    *,
    config: dict[str, Any],
    as_of: datetime,
) -> dict[str, Any]:
    with _suppress_runtime_directory_creation():
        from services.ingestion.article_scorer import score_article
        from services.ingestion.publish_tier import compute_publish_tier
        from services.ingestion.viral_scorer import score_viral_potential

    story_count = _story_article_count(connection, article)
    image_count = _downloaded_image_count(connection, article["id"])
    keywords = [str(value) for value in _parse_json_list(article.get("keywords_json"))]
    published_at = _parse_datetime(article.get("published_at"))
    hot_match, hot_payload = _persisted_hot_radar(connection, article["id"])
    with _scoring_clock(as_of):
        industry = score_article(
            title=article.get("title") or "",
            summary=article.get("summary"),
            content_text=article.get("content_text"),
            keywords=keywords,
            published_at=published_at,
            view_count=article.get("view_count"),
            story_article_count=story_count,
            image_count=image_count,
            hot_radar_match=hot_match,
            config=config,
        )
    viral = score_viral_potential(
        title=article.get("title") or "",
        summary=article.get("summary"),
        content_text=article.get("content_text"),
        prominence_score=_prominence_score(industry),
        story_article_count=story_count,
        hot_radar_match=hot_match,
        config=config,
    )
    industry_payload = industry.to_dict()
    viral_payload = viral.to_dict()
    tier = compute_publish_tier(
        industry_grade=industry.grade,
        industry_total=industry.total,
        viral_grade=viral.grade,
        hook_gate_passed=viral.hook_gate.passed,
        config=config,
    )
    breakdown: dict[str, Any] = {
        "profile": industry_payload.get("profile"),
        "industry": industry_payload,
        "viral": viral_payload,
        "rule": {"total": round(industry.total, 1), "grade": industry.grade},
        "final": {
            "industry_total": round(industry.total, 1),
            "industry_grade": industry.grade,
            "viral_total": round(viral.total, 1),
            "viral_grade": viral.grade,
            "publish_tier": tier,
            "total": round(industry.total, 1),
            "grade": industry.grade,
            "adjusted_by": "rule",
        },
        "total": round(industry.total, 1),
        "grade": industry.grade,
        "dimensions": industry_payload.get("dimensions", []),
        "bonuses": industry_payload.get("bonuses", []),
        "penalties": industry_payload.get("penalties", []),
        "recommendation": industry_payload.get("recommendation"),
    }
    if hot_payload is not None:
        breakdown["hot_radar"] = hot_payload
    return {
        "score_inputs": {
            "keywords": keywords,
            "published_at": (
                published_at.isoformat() if published_at is not None else None
            ),
            "story_article_count": story_count,
            "downloaded_image_count": image_count,
            "hot_radar": hot_payload,
        },
        "industry": industry_payload,
        "viral": viral_payload,
        "breakdown": breakdown,
        "article_fields": {
            "score_total": float(industry.total),
            "score_grade": industry.grade,
            "score_breakdown_json": json.dumps(
                breakdown, ensure_ascii=False, sort_keys=True
            ),
            "score_comment": None,
            "scored_at": as_of.isoformat(),
        },
    }


def _old_scores(article: dict[str, Any]) -> dict[str, Any]:
    breakdown = _parse_json_dict(article.get("score_breakdown_json"))
    industry = breakdown.get("industry") or {}
    viral = breakdown.get("viral") or {}
    final = breakdown.get("final") or {}
    return {
        "industry_total": (
            industry.get("total")
            if industry.get("total") is not None
            else article.get("score_total")
        ),
        "industry_grade": (
            industry.get("grade")
            or final.get("industry_grade")
            or article.get("score_grade")
        ),
        "viral_total": (
            viral.get("total")
            if viral.get("total") is not None
            else final.get("viral_total")
        ),
        "viral_grade": viral.get("grade") or final.get("viral_grade"),
    }


def candidate_id_for(article_id: str, platform: str, policy_version: str) -> str:
    value = f"{REBUILD_POLICY_VERSION}\0{policy_version}\0{article_id}\0{platform}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _candidate_policy_version(config: dict[str, Any]) -> str:
    base = (config.get("publish_policy") or {}).get(
        "policy_version", config.get("policy_version", 1)
    )
    return str(base)


def _candidate_id(
    connection: sqlite3.Connection,
    *,
    article_id: str,
    platform: str,
    policy_version: str,
) -> str:
    if not _table_exists(connection, "auto_publish_candidates"):
        return candidate_id_for(article_id, platform, policy_version)
    existing = connection.execute(
        """
        SELECT id
        FROM auto_publish_candidates
        WHERE article_id = ? AND platform = ? AND policy_version = ?
        ORDER BY id
        LIMIT 1
        """,
        (article_id, platform, policy_version),
    ).fetchone()
    if existing is not None:
        return str(existing["id"])
    return candidate_id_for(article_id, platform, policy_version)


def _policy_decision(
    *,
    platform: str,
    rescore: dict[str, Any],
    recent_story_count: int,
    config: dict[str, Any],
) -> Any:
    from services.publishing.publish_policy import decide_platform_publish

    return decide_platform_publish(
        platform,
        industry_grade=rescore["industry"]["grade"],
        industry_total=rescore["industry"]["total"],
        viral_grade=rescore["viral"]["grade"],
        viral_total=rescore["viral"]["total"],
        motives=rescore["viral"].get("motives") or [],
        platform_fit=rescore["viral"].get("platform_fit") or [],
        story_recent_count=recent_story_count,
        config=config,
    )


def _iso(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    return parsed.isoformat() if parsed is not None else None


def _resolve_dispatch_asset(
    raw: Any,
    *,
    data_dir: Path,
    allowed_subdir: tuple[str, ...],
) -> tuple[Path | None, str | None]:
    text = str(raw or "").strip()
    if not text:
        return None, "missing"
    normalized = text.replace("\\", "/")
    source = Path(normalized)
    if source.is_absolute():
        candidate = source.expanduser().resolve()
    else:
        cleaned = normalized.lstrip("/")
        parts = Path(cleaned).parts
        if parts and parts[0].lower() == "data":
            parts = parts[1:]
        candidate = (data_dir / Path(*parts)).resolve()
    allowed = data_dir.joinpath(*allowed_subdir).resolve()
    if candidate != allowed and allowed not in candidate.parents:
        return candidate, "outside_data_dir"
    if not candidate.is_file():
        return candidate, "file_missing"
    return candidate, None


def _legacy_replacement_errors(article: dict[str, Any], db_path: Path) -> list[str]:
    data_dir = db_path.parent.resolve()
    errors: list[str] = []
    video, video_problem = _resolve_dispatch_asset(
        article.get("generated_video_path"),
        data_dir=data_dir,
        allowed_subdir=("videos",),
    )
    if video_problem == "missing":
        errors.append("generated_video_path_missing")
    elif video_problem == "outside_data_dir":
        errors.append("generated_video_path_outside_data_dir")
    elif video_problem == "file_missing":
        errors.append("generated_video_file_missing")
    elif video is not None and video.suffix.lower() != ".mp4":
        errors.append("generated_video_not_mp4")

    cover_raw = article.get("generated_cover_path")
    if str(cover_raw or "").strip():
        _, cover_problem = _resolve_dispatch_asset(
            cover_raw,
            data_dir=data_dir,
            allowed_subdir=("publish", "covers"),
        )
        if cover_problem == "outside_data_dir":
            errors.append("generated_cover_path_outside_data_dir")
        elif cover_problem == "file_missing":
            errors.append("generated_cover_file_missing")

    draft_raw = article.get("video_draft_json")
    if not str(draft_raw or "").strip():
        errors.append("video_draft_missing")
    else:
        try:
            draft = json.loads(str(draft_raw))
        except (TypeError, json.JSONDecodeError):
            errors.append("video_draft_malformed")
        else:
            if not isinstance(draft, dict):
                errors.append("video_draft_malformed")
            elif not str(draft.get("main_line1") or "").strip():
                errors.append("video_draft_unusable:main_line1_missing")
    return errors


def _group_jobs(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        platform = str(row.get("account_platform") or "<missing-account>")
        key = (str(row.get("source_id") or ""), platform)
        grouped.setdefault(key, []).append(row)
    return [
        sorted(group, key=lambda item: str(item["id"]))
        for _, group in sorted(grouped.items())
    ]


def _inspect_connection(
    connection: sqlite3.Connection,
    *,
    db_path: Path,
    config: dict[str, Any],
    as_of: datetime,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if schema is None:
        schema, schema_warnings = _validate_schema(
            connection, allow_missing_candidate_table=True
        )
    else:
        schema_warnings = _schema_problems(schema)
    staged = _staged_policy_config(config)
    policy_version = _candidate_policy_version(staged)
    jobs = _in_scope_jobs(connection)
    groups: list[dict[str, Any]] = []
    score_cache: dict[str, dict[str, Any]] = {}

    for grouped_jobs in _group_jobs(jobs):
        first = grouped_jobs[0]
        article_id = str(first.get("source_id") or "")
        platform = str(first.get("account_platform") or "<missing-account>")
        article = _article_row(connection, article_id)
        account_valid = all(
            row.get("resolved_account_id")
            and row.get("account_status") == "active"
            and row.get("account_platform") == platform
            for row in grouped_jobs
        )
        platform_valid = platform in SUPPORTED_PLATFORMS
        errors: list[str] = []
        if article is None:
            errors.append("article_missing")
        if not account_valid:
            errors.append("account_missing_or_inactive")
        if not platform_valid:
            errors.append(f"platform_unsupported:{platform}")
        valid = not errors
        mode = PLATFORM_MODES.get(platform, "unsupported")
        replacement_errors = (
            _legacy_replacement_errors(article, db_path)
            if valid and article is not None and mode == "legacy-preserve"
            else []
        )
        errors.extend(replacement_errors)
        replacement_safe = valid and not replacement_errors

        if article is not None:
            rescore = score_cache.setdefault(
                article_id,
                _pure_rescore(
                    connection,
                    article,
                    config=staged,
                    as_of=as_of,
                ),
            )
            old_scores = _old_scores(article)
            new_scores = {
                "industry_total": rescore["industry"]["total"],
                "industry_grade": rescore["industry"]["grade"],
                "viral_total": rescore["viral"]["total"],
                "viral_grade": rescore["viral"]["grade"],
            }
        else:
            rescore = None
            old_scores = {
                "industry_total": None,
                "industry_grade": None,
                "viral_total": None,
                "viral_grade": None,
            }
            new_scores = dict(old_scores)

        policy_payload: dict[str, Any]
        candidate: dict[str, Any] | None
        if replacement_safe and rescore is not None and article is not None:
            policy = _policy_decision(
                platform=platform,
                rescore=rescore,
                recent_story_count=_recent_story_count(
                    connection, article, as_of=as_of
                ),
                config=staged,
            )
            reasons = list(policy.reasons)
            if mode == "legacy-preserve":
                decision = "keep"
                candidate_action = "publish"
                candidate_status = "pending"
                reasons.append(f"migration.{platform}.legacy_preserve")
            elif policy.action == "publish":
                decision = "rebuild"
                candidate_action = "publish"
                candidate_status = "pending"
            elif policy.action == "defer":
                decision = "defer"
                candidate_action = "defer"
                candidate_status = "deferred"
            else:
                decision = "cancel"
                candidate_action = "skip"
                candidate_status = "skipped"
            candidate_id = _candidate_id(
                connection,
                article_id=article_id,
                platform=platform,
                policy_version=policy_version,
            )
            candidate = {
                "id": candidate_id,
                "article_id": article_id,
                "platform": platform,
                "action": candidate_action,
                "recommended_action": policy.recommended_action,
                "priority": float(policy.priority),
                "reasons_json": json.dumps(reasons, ensure_ascii=False),
                "policy_version": policy_version,
                "status": candidate_status,
                "evaluated_at": as_of.isoformat(),
                "scheduled_date": None,
                "publish_job_id": None,
                "created_at": as_of.isoformat(),
                "updated_at": as_of.isoformat(),
                "industry_id": str(
                    article.get("industry_id") or DEFAULT_INDUSTRY_ID
                ),
            }
            policy_payload = {
                "action": policy.action,
                "recommended_action": policy.recommended_action,
                "priority": float(policy.priority),
                "reasons": reasons,
                "version": str(policy.policy_version),
                "shadow_mode": bool(policy.shadow_mode),
            }
        else:
            decision = "keep-existing-job" if valid and replacement_errors else "defer"
            candidate = None
            policy_payload = {
                "action": "defer",
                "recommended_action": "defer",
                "priority": 0.0,
                "reasons": list(errors),
                "version": str(
                    (staged.get("publish_policy") or {}).get("policy_version", 1)
                ),
                "shadow_mode": False,
            }

        schedules = sorted(
            value
            for value in (_iso(row.get("scheduled_at")) for row in grouped_jobs)
            if value is not None
        )
        groups.append(
            {
                "article_id": article_id,
                "platform": platform,
                "job_ids": [str(row["id"]) for row in grouped_jobs],
                "mode": mode,
                "valid": valid,
                "replacement_safe": replacement_safe,
                "errors": errors,
                "decision": decision,
                "old_scores": old_scores,
                "new_scores": new_scores,
                "score_inputs": rescore["score_inputs"] if rescore else {},
                "new_breakdown": rescore["breakdown"] if rescore else None,
                "new_article_fields": rescore["article_fields"] if rescore else None,
                "policy": policy_payload,
                "candidate": candidate,
                "old_scheduled_at": schedules[0] if schedules else None,
                "old_scheduled_times": schedules,
                "new_scheduled_at": None,
            }
        )

    decisions = Counter(group["decision"] for group in groups)
    candidate_statuses = Counter(
        group["candidate"]["status"]
        for group in groups
        if group["candidate"] is not None
    )
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "dry_run": True,
        "database": str(db_path),
        "evaluated_at": as_of.isoformat(),
        "policy_version": policy_version,
        "schema_ready": not schema_warnings,
        "schema_warnings": schema_warnings,
        "schema_fingerprint": _logical_fingerprint(schema),
        "database_identity": _database_identity(connection, db_path, schema),
        "required_runtime_settings": _required_runtime_settings(config),
        "platform_modes": dict(PLATFORM_MODES),
        "budgets": dict(PLATFORM_BUDGETS),
        "groups": groups,
        "summary": {
            "scope_jobs": len(jobs),
            "groups": len(groups),
            "valid_groups": sum(group["valid"] for group in groups),
            "invalid_groups": sum(not group["valid"] for group in groups),
            "decisions": dict(sorted(decisions.items())),
            "candidate_statuses": dict(sorted(candidate_statuses.items())),
        },
    }


def inspect_database(
    db_path: str | Path,
    *,
    as_of: datetime | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the complete rebuild diff using a SQLite ``mode=ro`` connection."""
    path = _resolved_database_path(db_path)
    active_config = copy.deepcopy(config) if config is not None else _load_scoring_config_read_only(path)
    evaluated_at = _utc_naive(as_of or datetime.utcnow()).replace(microsecond=0)
    with closing(_readonly_connection(path)) as connection:
        connection.execute("BEGIN")
        try:
            schema, _ = _validate_schema(
                connection, allow_missing_candidate_table=True
            )
            return _inspect_connection(
                connection,
                db_path=path,
                config=active_config,
                as_of=evaluated_at,
                schema=schema,
            )
        finally:
            connection.rollback()


def _rows_by_ids(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    ids: list[str],
) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    selected = ", ".join(columns)
    return _select_dicts(
        connection,
        f"SELECT {selected} FROM {table} WHERE id IN ({placeholders}) ORDER BY id",
        ids,
    )


def _snapshot_scoring_config(config: dict[str, Any]) -> dict[str, Any]:
    """Capture the complete effective config consumed by scoring and policy."""
    return copy.deepcopy(_staged_policy_config(config))


def _logical_snapshot(
    connection: sqlite3.Connection,
    report: dict[str, Any],
    *,
    schema: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    jobs = [_job_original(row) for row in _in_scope_jobs(connection)]
    article_ids = sorted(
        {
            str(group["article_id"])
            for group in report["groups"]
            if group.get("article_id")
        }
    )
    articles = _rows_by_ids(
        connection,
        "ingested_articles",
        ARTICLE_INPUT_COLUMNS,
        article_ids,
    )
    account_ids = sorted(
        {
            str(job["account_id"])
            for job in jobs
            if job.get("account_id")
        }
    )
    accounts = _rows_by_ids(
        connection,
        "publisher_accounts",
        ACCOUNT_INPUT_COLUMNS,
        account_ids,
    )
    story_ids = sorted(
        {
            str(article["story_id"])
            for article in articles
            if article.get("story_id")
        }
    )
    stories = _rows_by_ids(
        connection,
        "stories",
        ("id", "article_count"),
        story_ids,
    )
    if story_ids:
        story_placeholders = ",".join("?" for _ in story_ids)
        story_members = _select_dicts(
            connection,
            f"""
            SELECT id, story_id, article_id
            FROM story_articles
            WHERE story_id IN ({story_placeholders})
            ORDER BY story_id, article_id, id
            """,
            story_ids,
        )
        recent_article_peers = _select_dicts(
            connection,
            f"""
            SELECT id, story_id, created_at
            FROM ingested_articles
            WHERE story_id IN ({story_placeholders})
            ORDER BY datetime(created_at), id
            """,
            story_ids,
        )
    else:
        story_members = []
        recent_article_peers = []
    if article_ids:
        article_placeholders = ",".join("?" for _ in article_ids)
        images = _select_dicts(
            connection,
            f"""
            SELECT id, article_id, download_status
            FROM article_images
            WHERE article_id IN ({article_placeholders})
            ORDER BY article_id, id
            """,
            article_ids,
        )
        radar = _select_dicts(
            connection,
            f"""
            SELECT {", ".join(REQUIRED_SCHEMA["hot_radar_article_matches"])}
            FROM hot_radar_article_matches
            WHERE article_id IN ({article_placeholders})
            ORDER BY article_id, confidence DESC, effective_rank, id
            """,
            article_ids,
        )
    else:
        images = []
        radar = []
    candidate_ids = sorted(
        group["candidate"]["id"]
        for group in report["groups"]
        if group.get("candidate") is not None
    )
    candidates = (
        _rows_by_ids(
            connection,
            "auto_publish_candidates",
            CANDIDATE_COLUMNS,
            candidate_ids,
        )
        if _table_exists(connection, "auto_publish_candidates")
        else []
    )
    return {
        "jobs": jobs,
        "articles": articles,
        "accounts": accounts,
        "story_inputs": {
            "stories": stories,
            "members": story_members,
            "recent_article_peers": recent_article_peers,
        },
        "image_inputs": images,
        "hot_radar_inputs": radar,
        "replacement_prerequisites": [
            {
                "article_id": group["article_id"],
                "platform": group["platform"],
                "job_ids": group["job_ids"],
                "replacement_safe": group["replacement_safe"],
                "errors": group["errors"],
            }
            for group in report["groups"]
        ],
        "preexisting_candidates": candidates,
        "schema": schema,
        "scoring_config": _snapshot_scoring_config(config),
    }


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n"
    ).encode("utf-8")


def _sync_directory_if_supported(path: Path) -> None:
    if os.name == "nt":
        return
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _move_windows_exclusive_write_through(source: Path, target: Path) -> None:
    """Atomically publish on Windows without replacement and flush metadata."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file_ex = kernel32.MoveFileExW
    move_file_ex.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    move_file_ex.restype = wintypes.BOOL
    movefile_write_through = 0x00000008
    if move_file_ex(str(source), str(target), movefile_write_through):
        return
    error = ctypes.get_last_error()
    if error in {80, 183}:  # ERROR_FILE_EXISTS / ERROR_ALREADY_EXISTS
        raise FileExistsError(error, os.strerror(error), str(target))
    raise ctypes.WinError(error)


def _publish_temp_exclusive(source: Path, target: Path) -> None:
    if os.name == "nt":
        _move_windows_exclusive_write_through(source, target)
        return
    os.link(source, target)
    _sync_directory_if_supported(target.parent)


def _publish_backup_exclusive(path: Path, payload: dict[str, Any]) -> None:
    """Publish a complete fsynced file atomically without replacing a winner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        _publish_temp_exclusive(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Replace a non-backup JSON report atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory_if_supported(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _manifest_from_report(
    connection: sqlite3.Connection,
    path: Path,
    report: dict[str, Any],
    *,
    schema: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    snapshot = _logical_snapshot(
        connection,
        report,
        schema=schema,
        config=config,
    )
    scope_jobs = snapshot["jobs"]
    article_ids = sorted(
        {
            group["article_id"]
            for group in report["groups"]
            if group["valid"] and group["new_article_fields"] is not None
        }
    )
    candidates = [
        group["candidate"]
        for group in report["groups"]
        if group["valid"] and group["candidate"] is not None
    ]
    candidate_ids = sorted(candidate["id"] for candidate in candidates)
    original_articles = _rows_by_ids(
        connection,
        "ingested_articles",
        ARTICLE_SCORE_COLUMNS,
        article_ids,
    )
    preexisting = snapshot["preexisting_candidates"]
    preexisting_by_id = {row["id"]: row for row in preexisting}
    expected_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        expected = dict(candidate)
        if candidate["id"] in preexisting_by_id:
            expected["created_at"] = preexisting_by_id[candidate["id"]]["created_at"]
        expected_candidates.append(expected)
    expected_articles = [
        {"id": article_id, **next(
            group["new_article_fields"]
            for group in report["groups"]
            if group["article_id"] == article_id
            and group["valid"]
            and group["new_article_fields"] is not None
        )}
        for article_id in article_ids
    ]
    changed_job_ids = sorted(
        job_id
        for group in report["groups"]
        if group["replacement_safe"]
        for job_id in group["job_ids"]
    )
    unchanged_job_ids = sorted(
        job_id
        for group in report["groups"]
        if not group["replacement_safe"]
        for job_id in group["job_ids"]
    )
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "kind": "ainews.pending_ingestion_publish_queue_backup",
        "created_at": report["evaluated_at"],
        "database": {
            "path": str(path),
            "snapshot_fingerprint": _logical_fingerprint(snapshot),
            "schema_fingerprint": _logical_fingerprint(schema),
            "identity": _database_identity(connection, path, schema),
            "metadata": schema["metadata"],
        },
        "snapshot": snapshot,
        "required_runtime_settings": report["required_runtime_settings"],
        "policy_version": report["policy_version"],
        "publish_job_columns": list(PUBLISH_JOB_COLUMNS),
        "candidate_columns": list(CANDIDATE_COLUMNS),
        "article_score_columns": list(ARTICLE_SCORE_COLUMNS),
        "publish_jobs": scope_jobs,
        "articles": original_articles,
        "preexisting_candidates": preexisting,
        "candidate_ids": candidate_ids,
        "apply_state": {
            "changed_job_ids": changed_job_ids,
            "unchanged_job_ids": unchanged_job_ids,
            "finished_at": report["evaluated_at"],
            "error_message": f"requeued by {report['policy_version']}",
            "articles": expected_articles,
            "candidates": expected_candidates,
        },
        "plan": report,
    }


def create_backup(
    db_path: str | Path,
    backup_path: str | Path,
    *,
    as_of: datetime | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a complete, fsynced pre-apply manifest without changing the DB."""
    path = _resolved_database_path(db_path)
    destination = Path(backup_path).expanduser().resolve()
    evaluated_at = _utc_naive(as_of or datetime.utcnow()).replace(microsecond=0)
    with closing(_readonly_connection(path)) as connection:
        connection.execute("BEGIN")
        try:
            schema, problems = _validate_schema(
                connection, allow_missing_candidate_table=False
            )
            if problems:
                raise IncompatibleSchemaError(
                    "incompatible rebuild schema: " + ", ".join(problems)
                )
            active_config = (
                copy.deepcopy(config)
                if config is not None
                else _load_scoring_config_read_only(path)
            )
            report = _inspect_connection(
                connection,
                db_path=path,
                config=active_config,
                as_of=evaluated_at,
                schema=schema,
            )
            manifest = _manifest_from_report(
                connection,
                path,
                report,
                schema=schema,
                config=active_config,
            )
            _publish_backup_exclusive(destination, manifest)
        finally:
            connection.rollback()
    return manifest


def _load_manifest(backup_path: str | Path) -> dict[str, Any]:
    path = Path(backup_path).expanduser().resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise RebuildError("unsupported backup schema")
    if value.get("kind") != "ainews.pending_ingestion_publish_queue_backup":
        raise RebuildError("not a pending queue backup")
    return value


def _validate_identity(
    path: Path,
    manifest: dict[str, Any],
    connection: sqlite3.Connection,
    schema: dict[str, Any],
) -> None:
    expected = str(Path(manifest["database"]["path"]).resolve())
    if str(path) != expected:
        raise DatabaseIdentityError(
            f"backup database path is {expected}, not {path}"
        )
    schema_fingerprint = _logical_fingerprint(schema)
    if schema_fingerprint != manifest["database"]["schema_fingerprint"]:
        raise IncompatibleSchemaError("database schema differs from backup schema")
    identity = _database_identity(connection, path, schema)
    if identity != manifest["database"]["identity"]:
        raise DatabaseIdentityError("database logical identity differs from backup")


def _row_matches(
    actual: sqlite3.Row | None,
    expected: dict[str, Any],
    columns: Iterable[str],
) -> bool:
    if actual is None:
        return False
    return all(actual[column] == expected.get(column) for column in columns)


def _original_state(
    connection: sqlite3.Connection, manifest: dict[str, Any]
) -> bool:
    for expected in manifest["publish_jobs"]:
        row = connection.execute(
            "SELECT * FROM publish_jobs WHERE id = ?", (expected["id"],)
        ).fetchone()
        if not _row_matches(row, expected, PUBLISH_JOB_COLUMNS):
            return False
    for expected in manifest["articles"]:
        row = connection.execute(
            "SELECT * FROM ingested_articles WHERE id = ?", (expected["id"],)
        ).fetchone()
        if not _row_matches(row, expected, ARTICLE_SCORE_COLUMNS):
            return False
    preexisting = {
        row["id"]: row for row in manifest.get("preexisting_candidates", [])
    }
    for candidate_id in manifest.get("candidate_ids", []):
        actual = connection.execute(
            "SELECT * FROM auto_publish_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if candidate_id in preexisting:
            if not _row_matches(actual, preexisting[candidate_id], CANDIDATE_COLUMNS):
                return False
        elif actual is not None:
            return False
    return True


def _applied_state(
    connection: sqlite3.Connection, manifest: dict[str, Any]
) -> bool:
    state = manifest["apply_state"]
    for job_id in state["changed_job_ids"]:
        row = connection.execute(
            "SELECT status, finished_at, error_message FROM publish_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if (
            row is None
            or row["status"] != "cancelled"
            or row["finished_at"] != state["finished_at"]
            or row["error_message"] != state["error_message"]
        ):
            return False
    originals = {row["id"]: row for row in manifest["publish_jobs"]}
    for job_id in state["unchanged_job_ids"]:
        row = connection.execute(
            "SELECT * FROM publish_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not _row_matches(row, originals[job_id], PUBLISH_JOB_COLUMNS):
            return False
    for expected in state["articles"]:
        row = connection.execute(
            "SELECT * FROM ingested_articles WHERE id = ?", (expected["id"],)
        ).fetchone()
        if not _row_matches(row, expected, ARTICLE_SCORE_COLUMNS):
            return False
    for expected in state["candidates"]:
        row = connection.execute(
            "SELECT * FROM auto_publish_candidates WHERE id = ?", (expected["id"],)
        ).fetchone()
        if not _row_matches(row, expected, CANDIDATE_COLUMNS):
            return False
    return True


def _verify_preapply(
    connection: sqlite3.Connection,
    path: Path,
    manifest: dict[str, Any],
    *,
    schema: dict[str, Any],
    config: dict[str, Any],
) -> None:
    as_of = _parse_datetime(manifest["created_at"])
    if as_of is None:
        raise RebuildError("backup created_at is invalid")
    report = _inspect_connection(
        connection,
        db_path=path,
        config=config,
        as_of=as_of,
        schema=schema,
    )
    snapshot = _logical_snapshot(
        connection,
        report,
        schema=schema,
        config=config,
    )
    if (
        _logical_fingerprint(snapshot)
        != manifest["database"]["snapshot_fingerprint"]
    ):
        raise DatabaseChangedError("database logical snapshot changed after backup")


def _update_row(
    connection: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
    columns: Iterable[str],
) -> None:
    fields = [column for column in columns if column != "id"]
    assignments = ", ".join(f"{field} = ?" for field in fields)
    connection.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?",
        tuple(row.get(field) for field in fields) + (row["id"],),
    )


def _insert_row(
    connection: sqlite3.Connection,
    table: str,
    row: dict[str, Any],
    columns: tuple[str, ...],
) -> None:
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(row.get(column) for column in columns),
    )


def _upsert_candidate(
    connection: sqlite3.Connection, candidate: dict[str, Any]
) -> None:
    existing = connection.execute(
        "SELECT id FROM auto_publish_candidates WHERE id = ?", (candidate["id"],)
    ).fetchone()
    if existing is None:
        _insert_row(
            connection,
            "auto_publish_candidates",
            candidate,
            CANDIDATE_COLUMNS,
        )
    else:
        _update_row(
            connection,
            "auto_publish_candidates",
            candidate,
            CANDIDATE_COLUMNS,
        )


def _call_failure_hook(hook: FailureHook | None, phase: str) -> None:
    if hook is not None:
        hook(phase)


def apply_rebuild(
    db_path: str | Path,
    backup_path: str | Path,
    *,
    as_of: datetime | None = None,
    failure_hook: FailureHook | None = None,
) -> dict[str, Any]:
    """Atomically cancel valid legacy jobs and upsert non-dispatched candidates."""
    path = _resolved_database_path(db_path)
    backup = Path(backup_path).expanduser().resolve()
    with closing(_writable_connection(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            schema, _ = _validate_schema(
                connection, allow_missing_candidate_table=False
            )
            active_config = _load_scoring_config_read_only(path)
            runtime_settings = _required_runtime_settings(active_config)
            if backup.exists():
                manifest = _load_manifest(backup)
                _validate_identity(path, manifest, connection, schema)
                if _applied_state(connection, manifest):
                    connection.rollback()
                    return {
                        "applied": False,
                        "already_applied": True,
                        "summary": manifest["plan"]["summary"],
                    }
                _require_runtime_settings(runtime_settings)
                _verify_preapply(
                    connection,
                    path,
                    manifest,
                    schema=schema,
                    config=active_config,
                )
            else:
                _require_runtime_settings(runtime_settings)
                evaluated_at = _utc_naive(
                    as_of or datetime.utcnow()
                ).replace(microsecond=0)
                report = _inspect_connection(
                    connection,
                    db_path=path,
                    config=active_config,
                    as_of=evaluated_at,
                    schema=schema,
                )
                manifest = _manifest_from_report(
                    connection,
                    path,
                    report,
                    schema=schema,
                    config=active_config,
                )
                _publish_backup_exclusive(backup, manifest)
                _call_failure_hook(failure_hook, "after_backup_publish")
            state = manifest["apply_state"]
            for article in state["articles"]:
                _update_row(
                    connection,
                    "ingested_articles",
                    article,
                    ARTICLE_SCORE_COLUMNS,
                )
            _call_failure_hook(failure_hook, "after_article_scores")
            for job_id in state["changed_job_ids"]:
                connection.execute(
                    """
                    UPDATE publish_jobs
                    SET status = 'cancelled', finished_at = ?, error_message = ?
                    WHERE id = ? AND status = 'pending' AND source_type = 'ingestion'
                    """,
                    (state["finished_at"], state["error_message"], job_id),
                )
                if connection.execute("SELECT changes()").fetchone()[0] != 1:
                    raise DatabaseChangedError(f"job scope changed during apply: {job_id}")
            _call_failure_hook(failure_hook, "after_job_cancellation")
            for candidate in state["candidates"]:
                _upsert_candidate(connection, candidate)
            _call_failure_hook(failure_hook, "after_candidate_upsert")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return {
        "applied": True,
        "already_applied": False,
        "backup": str(backup),
        "summary": manifest["plan"]["summary"],
    }


def restore_backup(
    db_path: str | Path,
    backup_path: str | Path,
    *,
    failure_hook: FailureHook | None = None,
) -> dict[str, Any]:
    """Restore exactly the rows captured by one backup in one transaction."""
    path = _resolved_database_path(db_path)
    backup = Path(backup_path).expanduser().resolve()
    manifest = _load_manifest(backup)
    with closing(_writable_connection(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            schema, _ = _validate_schema(
                connection, allow_missing_candidate_table=False
            )
            _validate_identity(path, manifest, connection, schema)
            if _original_state(connection, manifest):
                connection.rollback()
                return {"restored": False, "already_restored": True}
            if not _applied_state(connection, manifest):
                raise DatabaseChangedError(
                    "affected rows do not match the backup's applied state"
                )
            candidate_ids = manifest.get("candidate_ids", [])
            if candidate_ids:
                placeholders = ",".join("?" for _ in candidate_ids)
                connection.execute(
                    f"DELETE FROM auto_publish_candidates WHERE id IN ({placeholders})",
                    tuple(candidate_ids),
                )
            for candidate in manifest.get("preexisting_candidates", []):
                _insert_row(
                    connection,
                    "auto_publish_candidates",
                    candidate,
                    CANDIDATE_COLUMNS,
                )
            _call_failure_hook(failure_hook, "after_candidate_restore")
            for job in manifest["publish_jobs"]:
                _update_row(connection, "publish_jobs", job, PUBLISH_JOB_COLUMNS)
            for article in manifest["articles"]:
                _update_row(
                    connection,
                    "ingested_articles",
                    article,
                    ARTICLE_SCORE_COLUMNS,
                )
            _call_failure_hook(failure_hook, "after_row_restore")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return {"restored": True, "already_restored": False}


def render_human(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        f"Database: {report.get('database', '<restore>')}",
        f"Mode: {'dry-run (read-only)' if report.get('dry_run') else 'result'}",
        (
            "Scope: "
            f"{summary.get('scope_jobs', 0)} jobs / "
            f"{summary.get('groups', 0)} article-platform groups"
        ),
    ]
    if report.get("schema_warnings"):
        lines.append(
            "Schema warnings: " + ", ".join(report["schema_warnings"])
        )
    decisions = summary.get("decisions") or {}
    if decisions:
        lines.append(
            "Decisions: "
            + ", ".join(f"{key}={value}" for key, value in sorted(decisions.items()))
        )
    for group in report.get("groups") or []:
        old = group["old_scores"]
        new = group["new_scores"]
        error_suffix = (
            f"; blockers={','.join(group['errors'])}"
            if group.get("errors")
            else ""
        )
        lines.append(
            f"- {group['article_id']} / {group['platform']}: {group['decision']} "
            f"industry {old['industry_grade']}/{old['industry_total']} -> "
            f"{new['industry_grade']}/{new['industry_total']}; "
            f"viral {old['viral_grade']}/{old['viral_total']} -> "
            f"{new['viral_grade']}/{new['viral_total']}; "
            f"priority={group['policy']['priority']}{error_suffix}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_database_path())
    parser.add_argument("--json-out", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--restore", type=Path, metavar="BACKUP")
    parser.add_argument("--backup", type=Path, metavar="PATH")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.apply and args.backup is None:
        parser.error("--apply requires an explicit --backup PATH")
    if not args.apply and args.backup is not None:
        parser.error("--backup is only valid with --apply")
    try:
        if args.restore is not None:
            result = restore_backup(args.db, args.restore)
            output: dict[str, Any] = {"database": str(args.db.resolve()), **result}
        elif args.apply:
            result = apply_rebuild(
                args.db,
                args.backup,
            )
            output = {"database": str(args.db.resolve()), **result}
        else:
            output = inspect_database(args.db)
    except (OSError, sqlite3.DatabaseError, ValueError, RebuildError) as exc:
        parser.error(str(exc))

    if output.get("groups") is not None:
        print(render_human(output))
    else:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    if args.json_out is not None:
        _atomic_json_write(args.json_out.expanduser().resolve(), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
