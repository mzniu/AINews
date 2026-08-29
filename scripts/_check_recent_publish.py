"""Inspect recent publish vs ingestion library visibility."""
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "ainews.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== publish_jobs schema ===")
for r in c.execute("PRAGMA table_info(publish_jobs)"):
    print(r["name"], r["type"])

print("\n=== Recent publish_jobs ===")
for r in c.execute(
    "SELECT id, status, source_id, source_type, title, created_at, finished_at, published_at FROM publish_jobs ORDER BY created_at DESC LIMIT 8"
):
    row = dict(r)
    print(row)

print("\n=== Recent ingested_articles (created_at DESC) ===")
for r in c.execute(
    """
    SELECT id, source_id, title, status, score_grade, score_total,
           published_at, created_at
    FROM ingested_articles
    ORDER BY created_at DESC LIMIT 12
    """
):
    print(dict(r))

print("\n=== Hot radar discovery jobs ===")
for r in c.execute(
    """
    SELECT id, status, source_id, created_at, finished_at, error_message,
           substr(payload_json, 1, 400) AS payload
    FROM ingestion_jobs
    WHERE job_type = 'hot_radar_discovery'
    ORDER BY created_at DESC LIMIT 12
    """
):
    d = dict(r)
    print(d["id"], d["status"], d["source_id"], d["created_at"], d.get("error_message"))
    try:
        p = json.loads(d.get("payload") or "{}")
        print("  url:", (p.get("url") or "")[:80])
        print("  result:", p.get("result"))
    except json.JSONDecodeError:
        pass

print("\n=== Articles linked to recent publish jobs ===")
for r in c.execute(
    "SELECT id, status, source_id, source_type, title, created_at FROM publish_jobs ORDER BY created_at DESC LIMIT 8"
):
    aid = r["source_id"] if r["source_type"] in (None, "ingestion", "ingested_article") else None
    if not aid:
        aid = r["source_id"]
    if not aid:
        print("job", r["id"], "no source_id")
        continue
    art = c.execute(
        "SELECT id, title, source_id, published_at, created_at, score_grade FROM ingested_articles WHERE id=?",
        (aid,),
    ).fetchone()
    if art:
        print("FOUND in library:", dict(art))
        # rank by published_at
        rank = c.execute(
            "SELECT COUNT(*) FROM ingested_articles WHERE published_at > ? OR (published_at = ? AND created_at > ?)",
            (art["published_at"], art["published_at"], art["created_at"]),
        ).fetchone()[0]
        print("  rank by published_at (0=first page):", rank)
    else:
        print("MISSING from ingested_articles:", aid, "publish job", r["id"], r["status"])
