"""Fetch all TopHubData nodes for evaluation."""
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KEY = os.environ.get("TOPHUB_ACCESS_KEY", "")
if not KEY:
    raise SystemExit("Set TOPHUB_ACCESS_KEY")
BASE = "https://api.tophubdata.com"
HEADERS = {"Authorization": KEY}


def fetch_nodes(page: int = 1):
    r = requests.get(f"{BASE}/nodes", params={"p": page}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_node_detail(hashid: str):
    r = requests.get(f"{BASE}/nodes/{hashid}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    all_nodes = []
    page = 1
    while True:
        payload = fetch_nodes(page)
        data = payload.get("data") or []
        if not data:
            break
        all_nodes.extend(data)
        print(f"page {page}: {len(data)} nodes", file=sys.stderr)
        if len(data) < 20:
            break
        page += 1
        if page > 50:
            break

    out_path = ROOT / "data" / "_tophub_nodes.json"
    out_path.write_text(json.dumps(all_nodes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"total nodes: {len(all_nodes)}")
    print(f"saved: {out_path}")

    # print compact list
    for n in all_nodes:
        print(
            f"{n.get('hashid','?'):14} | {n.get('name','?'):12} | {n.get('display','?'):20} | domain={n.get('domain','')}"
        )


if __name__ == "__main__":
    main()
