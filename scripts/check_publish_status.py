import sqlite3
from pathlib import Path

db = Path.home() / "AppData/Roaming/AINews/ainews.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== PSI / 5800 jobs ===")
cur.execute(
    """
    SELECT j.id, j.status, j.comment_status, j.title, j.error_message,
           j.scheduled_at, j.started_at, j.finished_at, j.published_at,
           j.retry_count, a.platform, a.nickname, a.status AS account_status
    FROM publish_jobs j
    JOIN publisher_accounts a ON a.id = j.account_id
    WHERE j.title LIKE '%PSI%' OR j.title LIKE '%5800%' OR j.title LIKE '%盖茨%'
    ORDER BY j.created_at
    """
)
for r in cur.fetchall():
    print(dict(r))

print("\n=== overdue pending (scheduled before now) ===")
cur.execute(
    """
    SELECT j.id, j.status, j.title, j.scheduled_at, j.started_at, a.platform
    FROM publish_jobs j
    JOIN publisher_accounts a ON a.id = j.account_id
    WHERE j.status IN ('pending', 'uploading', 'processing')
      AND j.scheduled_at IS NOT NULL
      AND j.scheduled_at <= datetime('now')
    ORDER BY j.scheduled_at ASC
    LIMIT 20
    """
)
for r in cur.fetchall():
    print(dict(r))

print("\n=== active uploading ===")
cur.execute(
    """
    SELECT j.id, j.title, j.status, j.started_at, j.error_message, a.platform
    FROM publish_jobs j
    JOIN publisher_accounts a ON a.id = j.account_id
    WHERE j.status IN ('uploading', 'processing')
    """
)
for r in cur.fetchall():
    print(dict(r))

job_id = "bad1e8abf934491a892e18f4027c7279"
print(f"\n=== logs for {job_id} ===")
cur.execute(
    "SELECT level, message, created_at FROM publish_logs WHERE job_id=? ORDER BY created_at DESC LIMIT 15",
    (job_id,),
)
for r in cur.fetchall():
    print(r["created_at"], r["level"], r["message"][:250])

conn.close()
