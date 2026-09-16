"""Analyze TopHub nodes for AINews suitability."""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
nodes = json.loads((ROOT / "data" / "_tophub_nodes.json").read_text(encoding="utf-8"))

AI_KW = re.compile(
    r"AI|人工智能|大模型|LLM|GPT|ChatGPT|OpenAI|DeepSeek|机器学习|智能体|Agent|芯片|算力|科技|数码|IT|互联网|创业|融资",
    re.I,
)
TECH_KW = re.compile(r"科技|数码|IT|互联网|36氪|虎嗅|量子位|机器之心|IT之家|极客|开发者|编程|开源|GitHub|Product Hunt", re.I)
SKIP_KW = re.compile(r"娱乐|明星|综艺|影视|电影|电视剧|游戏|体育|足球|篮球|彩票|情感|穿搭|美妆|美食|旅游|宠物|育儿|星座|小说|漫画|动漫|ACG|饭圈|八卦", re.I)

by_domain: dict[str, list] = defaultdict(list)
for n in nodes:
    by_domain[n.get("domain") or "unknown"].append(n)

# score each node
scored = []
for n in nodes:
    name = n.get("name") or ""
    display = n.get("display") or ""
    domain = n.get("domain") or ""
    text = f"{name} {display} {domain}"
    ai = bool(AI_KW.search(text))
    tech = bool(TECH_KW.search(text))
    skip = bool(SKIP_KW.search(text))
    tier = "D"
    reason = []
    if skip and not ai:
        tier = "D"
        reason.append("非科技向")
    elif ai:
        tier = "S"
        reason.append("AI/科技关键词")
    elif tech or domain in {
        "36kr.com",
        "huxiu.com",
        "ithome.com",
        "qbitai.com",
        "tech.sina.cn",
        "news.sina.cn",
        "toutiao.com",
        "thepaper.cn",
        "sspai.com",
        "guokr.com",
        "solidot.org",
        "readhub.cn",
        "juejin.cn",
        "csdn.net",
        "github.com",
        "producthunt.com",
        "infoq.cn",
        "pingwest.com",
        "leiphone.com",
    }:
        tier = "A"
        reason.append("科技/创投媒体")
    elif domain in {"zhihu.com", "weibo.com", "s.weibo.com", "baidu.com", "douyin.com", "toutiao.com"}:
        tier = "B"
        reason.append("泛热点，可筛AI")
    else:
        tier = "C"
        reason.append("泛榜/垂直其他")

    scored.append(
        {
            "hashid": n.get("hashid"),
            "name": name,
            "display": display,
            "domain": domain,
            "tier": tier,
            "reason": "; ".join(reason),
        }
    )

tier_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
scored.sort(key=lambda x: (tier_order[x["tier"]], x["name"], x["display"]))

summary = {
    "total": len(nodes),
    "unique_domains": len(by_domain),
    "tier_counts": {t: sum(1 for s in scored if s["tier"] == t) for t in "SABCD"},
}

recommended = [s for s in scored if s["tier"] in "SAB"]
out = ROOT / "data" / "_tophub_analysis.json"
out.write_text(
    json.dumps({"summary": summary, "recommended": recommended, "all": scored}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

md_lines = [
    "# TopHub 热榜节点评估",
    "",
    f"- 总节点数：**{summary['total']}**",
    f"- 独立域名：**{summary['unique_domains']}**",
    f"- 推荐等级统计：S={summary['tier_counts']['S']} A={summary['tier_counts']['A']} B={summary['tier_counts']['B']} C={summary['tier_counts']['C']} D={summary['tier_counts']['D']}",
    "",
    "## 推荐接入（S/A/B）",
    "",
    "| 等级 | hashid | 名称 | 榜单 | 域名 | 说明 |",
    "|------|--------|------|------|------|------|",
]
for s in recommended:
    md_lines.append(
        f"| {s['tier']} | `{s['hashid']}` | {s['name']} | {s['display']} | {s['domain']} | {s['reason']} |"
    )
(ROOT / "data" / "_tophub_report.md").write_text("\n".join(md_lines), encoding="utf-8")
print("done", summary["total"], "recommended", len(recommended))
