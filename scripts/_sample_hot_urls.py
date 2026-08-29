import sqlite3
from pathlib import Path

db = Path("data/ainews.db")
if not db.exists():
    print("no db")
    raise SystemExit(0)
c = sqlite3.connect(db)
for pattern in ("%aibase%", "%readhub%", "%ifeng%", "%sina%"):
    rows = c.execute(
        "select url, title from hot_radar_items where url like ? limit 3",
        (pattern,),
    ).fetchall()
    print(pattern, rows)
