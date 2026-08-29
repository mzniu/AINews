import json
from pathlib import Path

nodes = json.loads(Path("data/_tophub_nodes.json").read_text(encoding="utf-8"))
keywords = [
    "量子位", "机器之心", "IT之家", "新浪", "AIbase", "Readhub", "Solidot", "雷锋",
    "虎嗅", "36氪", "Product Hunt", "OpenAI", "TechCrunch", "VentureBeat", "少数派",
    "澎湃", "腾讯", "网易", "凤凰", "AI HOT", "AI榜", "人工智能", "AI频道", "AI日报",
    "AI资讯", "AITNT", "AI TNT", "新智界", "机器之能", "Leiphone", "雷锋网",
]
lines = []
for kw in keywords:
    hits = [
        n
        for n in nodes
        if kw.lower() in (n.get("name", "") + n.get("display", "")).lower()
        or kw in (n.get("name", "") + n.get("display", ""))
    ]
    if hits:
        lines.append(f"== {kw} ({len(hits)}) ==")
        for n in hits[:12]:
            lines.append(
                f"  {n.get('hashid')} | {n.get('name')} | {n.get('display')} | {n.get('domain')}"
            )
Path("data/_tophub_curated.txt").write_text("\n".join(lines), encoding="utf-8")
print("lines", len(lines))
