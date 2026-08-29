import json
import sqlite3
from pathlib import Path

db = Path("data/ainews.db")
if not db.exists():
    print("no db")
    raise SystemExit(0)

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

print("=== discovery jobs (latest 15) ===")
rows = c.execute(
    """
    SELECT id, status, source_id, created_at, finished_at, error_message, payload_json
    FROM ingestion_jobs
    WHERE job_type = 'hot_radar_discovery'
    ORDER BY created_at DESC
    LIMIT 15
    """
).fetchall()
print("count", len(rows))
for row in rows:
    payload = {}
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        pass
    print(
        row["id"][:8],
        row["status"],
        row["source_id"],
        payload.get("title", "")[:40],
        payload.get("url", "")[:60],
        "result=",
        payload.get("result"),
    )

print("\n=== crawl runs for discovery jobs ===")
for row in rows[:5]:
        run = c.execute(
            "SELECT id, status, stats_json FROM crawl_runs WHERE job_id = ?",
            (row["id"],),
        ).fetchone()
        print(row["id"][:8], dict(run) if run else None)
        if run:
            art = c.execute(
                "SELECT id, title, source_id, canonical_url FROM ingested_articles WHERE crawl_run_id = ?",
                (run["id"],),
            ).fetchone()
            print("  article", dict(art) if art else None)

print("\n=== recent articles by source ===")
for row in c.execute(
    """
    SELECT source_id, COUNT(*) AS n, MAX(created_at) AS latest
    FROM ingested_articles
    GROUP BY source_id
    ORDER BY latest DESC
    """
):
    print(dict(row))

print("\n=== newest 10 articles ===")
for row in c.execute(
    "SELECT id, source_id, title, canonical_url, created_at FROM ingested_articles ORDER BY created_at DESC LIMIT 10"
):
    print(dict(row))
