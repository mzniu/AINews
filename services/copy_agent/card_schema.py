"""Pattern card v2: schema text, validation, and API previews."""
from __future__ import annotations

import json
from typing import Any

from services.ingestion.viral_scorer import MOTIVE_LABELS

VERDICT_FUNCTIONS: dict[str, str] = {
    "controversy_commentary": "争议短评",
    "data_reveal_take": "数据揭示型",
    "figure_focus_take": "人物焦点型",
    "industry_trend_take": "行业趋势型",
    "policy_watch": "政策观察型",
    "product_launch_take": "产品发布型",
    "myth_bust_take": "辟谣对照型",
    "comparison_frame": "对照框架型",
}

GENRES: dict[str, str] = {
    "short_news_commentary": "短视频资讯评论",
    "explainer": "科普解释",
    "reaction_take": "反应点评",
}

HOOK_ARCHETYPES: dict[str, str] = {
    "curiosity_gap": "信息缺口",
    "pain_point": "痛点共鸣",
    "contradiction": "反差冲突",
    "direct_claim": "直接断言",
    "story_open": "故事开场",
}

COPY_MIN_RUN = 12
EVIDENCE_EXCERPT_MAX = 80
BODY_MIN_LEN = 30
HOOK_BODY_CUES = ("钩", "开场", "前三", "开头", "悬念", "缺口", "口播", "对照")
FORBIDDEN_ITEM_MAX_LEN = 28
FORBIDDEN_COPY_MIN_RUN = 8
BODY_INSTRUCTION_CUES = (
    "先",
    "再",
    "不要",
    "避免",
    "须",
    "应",
    "开场",
    "口播",
    "标题",
    "副标题",
    "问句",
    "对照",
    "写法",
    "第一",
    "第二",
    "段",
    "秒",
)


def is_v2_card(card: dict) -> bool:
    return bool(isinstance(card.get("pattern"), dict) and isinstance(card.get("moves"), list))


def _move_reflected(move: dict, body: str) -> bool:
    body_lower = body.lower()
    move_id = str(move.get("id") or "").strip().lower()
    if len(move_id) >= 2 and move_id in body_lower:
        return True
    function = str(move.get("function") or "").strip()
    for size in (4, 3):
        for idx in range(max(0, len(function) - size + 1)):
            segment = function[idx : idx + size]
            if segment and segment in body:
                return True
    return False


def validate_body_blocking(card: dict, body: str, *, material: str = "") -> list[str]:
    text = (body or "").strip()
    if not text:
        return ["打法正文 body 为空"]
    material = (material or "").strip()
    if material and longest_shared_run(text, material) >= COPY_MIN_RUN:
        return ["打法正文与素材重复过多，应写「怎么写」的祈使句，不要写新闻摘要"]
    if not is_v2_card(card):
        return []
    if len(text) < BODY_MIN_LEN:
        return [f"打法正文过短（至少 {BODY_MIN_LEN} 字），需写清执行顺序与结构"]
    if not any(cue in text for cue in BODY_INSTRUCTION_CUES):
        return ["打法正文需用写法说明语气（先/再/开场/口播/不要等），不要只复述资讯"]
    moves = [item for item in (card.get("moves") or []) if isinstance(item, dict)]
    if moves:
        reflected = sum(1 for item in moves if _move_reflected(item, text))
        needed = min(len(moves), 2)
        if reflected < needed:
            return [
                f"打法正文未体现足够结构段（模式卡 {needed} 个 move，正文约体现 {reflected} 段）"
            ]
    excerpt = str(card.get("evidence_excerpt") or "").strip()
    if excerpt and text == excerpt:
        return ["打法正文不能与 evidence_excerpt 相同"]
    return []


def validate_body_warnings(card: dict, body: str) -> list[str]:
    if not is_v2_card(card):
        return []
    text = (body or "").strip()
    if not text:
        return []
    warnings: list[str] = []
    if not any(cue in text for cue in HOOK_BODY_CUES):
        warnings.append("正文未明显描述开场或钩子，建议对照模式卡 hook 补一句")
    hook = card.get("hook") if isinstance(card.get("hook"), dict) else {}
    contract = str(hook.get("payoff_contract") or "").strip()
    if contract and longest_shared_run(contract, text) < 4:
        warnings.append("正文与 hook.payoff_contract 衔接偏弱，发布前建议人工核对")
    pattern = card.get("pattern") if isinstance(card.get("pattern"), dict) else {}
    purpose = str(pattern.get("purpose") or "").strip()
    if purpose and longest_shared_run(purpose, text) < 4:
        warnings.append("正文与 pattern.purpose 关键词重合较少，可能偏离模式目的")
    return warnings


ANALYSIS_MIN_LEN = 60


def validate_analysis(text: str, material: str) -> list[str]:
    body = (text or "").strip()
    issues: list[str] = []
    if len(body) < ANALYSIS_MIN_LEN:
        issues.append(f"analysis.md 过短（至少 {ANALYSIS_MIN_LEN} 字），需写清 move 与 frame 标注")
    lowered = body.lower()
    if "move" not in lowered and "结构" not in body and "帧" not in body and "frame" not in lowered:
        issues.append("analysis.md 需包含 move/结构 或 frame 标注")
    material = (material or "").strip()
    if material and body == material:
        issues.append("analysis.md 不能等于 material 全文")
    if material and longest_shared_run(body, material) >= COPY_MIN_RUN * 2:
        issues.append("analysis.md 与原文重复过多，请只写结构标注")
    return issues


def curate_schema_markdown() -> str:
    verdict_list = "、".join(f"`{k}`" for k in VERDICT_FUNCTIONS)
    motive_list = "、".join(f"`{k}`" for k in MOTIVE_LABELS)
    hook_list = "、".join(f"`{k}`" for k in HOOK_ARCHETYPES)
    genre_list = "、".join(f"`{k}`" for k in GENRES)
    return f"""# 拆卡输出规范（模式卡 v2）

两阶段拆卡：

1. **第一步**只写 `drafts/analysis.md`（实例 move / frame / 动机标注，禁止抄全文）。
2. **第二步**根据 `analysis.md` 写 `drafts/card.yaml` 与 `drafts/playbook.diff.yaml`（抽象模式卡 + 写法说明）。

可参考 `pattern_library.md` 中已有同类模式，但不得照抄名称以外的实例内容。

## 总则

1. **模式卡写抽象模式**，不要复述 `material.txt` 里的标题、公司名、原句。除 `evidence_excerpt` 外，任何字段不得连续复制原文 {COPY_MIN_RUN} 个及以上字符。
2. `evidence_excerpt` 只留最短实例锚点（≤{EVIDENCE_EXCERPT_MAX} 字），用于说明「从哪类样本抽象」，不要贴全文。
3. `verdict.kind` 必须是 `opinion`。
4. `verdict.function` 只能从下列英文键中选一个：{verdict_list}。禁止写完整标题句或网友口吻。
5. `transfer_rules.forbidden_transfers` 只写**规则类别**（每条 ≤28 字，如「无出处倍数升级」），**禁止**把素材标题、金句、数据句贴进去。
6. `playbook.diff.yaml` 的 `body` 必须是**写法说明**（先…再…不要…），**禁止**写成三条新闻摘要或通稿。

## card.yaml 结构（必填字段）

```yaml
pattern:
  name: "模式名称（抽象，禁止用素材标题）"
  genre: {genre_list} 中选一个
  purpose: "交际目的：这类稿要完成什么（一句话）"
moves:
  - id: hook
    function: "这一段的交际功能（抽象描述）"
  - id: develop
    function: "…"
  # 至少 2 个 move
hook:
  archetype: {hook_list} 中选一个
  opening_slots: ["主体", "数字", "冲突轴"]  # 槽位名，不是具体值
  payoff_contract: "前若干秒必须兑现什么（抽象）"
motives:
  primary: {motive_list} 中选一个
  secondary: 可选，同上
  arousal: high | low  # 情绪唤醒倾向
transfer_rules:
  forbidden_transfers: ["不宜照搬的类别"]
verdict:
  kind: opinion
  function: controversy_commentary  # 见上文键表
evidence_excerpt: "最短锚点"
```

可选：`frame`（问题/归因/评判/对策 四格，写抽象习惯）、`rhetoric.devices`、`instantiation.template`（带槽位的模板句，禁止具体专名）。

## playbook.diff.yaml

```yaml
body: |
  给写稿模型的「写法说明」：用祈使句描述顺序、钩子、口播节奏。
  可引用 move 名与槽位，禁止复制 material 原句。
```
"""


def _walk_strings(value: Any, path: str, out: list[tuple[str, str]]) -> None:
    if isinstance(value, str):
        out.append((path, value))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _walk_strings(item, f"{path}.{key}" if path else key, out)
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            _walk_strings(item, f"{path}[{idx}]", out)


def longest_shared_run(a: str, b: str) -> int:
    if not a or not b:
        return 0
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            run = 0
            while i + run < len(a) and j + run < len(b) and a[i + run] == b[j + run]:
                run += 1
            if run > best:
                best = run
    return best


def _forbidden_transfers(card: dict) -> list[str]:
    rules = card.get("transfer_rules")
    if isinstance(rules, dict):
        raw = rules.get("forbidden_transfers")
        if isinstance(raw, list):
            return [str(x) for x in raw if str(x).strip()]
    legacy = card.get("forbidden_transfers")
    if isinstance(legacy, list):
        return [str(x) for x in legacy if str(x).strip()]
    return []


def validate_card(card: dict, material: str) -> list[str]:
    issues: list[str] = []
    material = (material or "").strip()
    pattern = card.get("pattern") if isinstance(card.get("pattern"), dict) else {}
    name = str(pattern.get("name") or "").strip()
    if not name:
        issues.append("模式卡缺少 pattern.name（抽象模式名）")
    elif material and longest_shared_run(name, material) >= COPY_MIN_RUN:
        issues.append("pattern.name 与原文重复过多，请改成抽象模式名")

    genre = str(pattern.get("genre") or "").strip()
    if not genre:
        issues.append("模式卡缺少 pattern.genre")
    elif genre not in GENRES:
        issues.append(f"pattern.genre 不在允许列表内（当前：{genre}）")

    purpose = str(pattern.get("purpose") or "").strip()
    if not purpose:
        issues.append("模式卡缺少 pattern.purpose（交际目的）")

    moves = card.get("moves")
    if not isinstance(moves, list) or len(moves) < 2:
        issues.append("模式卡 moves 至少需要 2 项（每项含 id 与 function）")
    else:
        for idx, move in enumerate(moves):
            if not isinstance(move, dict):
                issues.append(f"moves[{idx}] 必须是对象")
                continue
            if not str(move.get("id") or "").strip():
                issues.append(f"moves[{idx}] 缺少 id")
            if not str(move.get("function") or "").strip():
                issues.append(f"moves[{idx}] 缺少 function")

    hook = card.get("hook")
    if not isinstance(hook, dict):
        issues.append("模式卡缺少 hook 对象")
    else:
        archetype = str(hook.get("archetype") or "").strip()
        if not archetype:
            issues.append("hook.archetype 必填")
        elif archetype not in HOOK_ARCHETYPES:
            issues.append(f"hook.archetype 不在允许列表内（当前：{archetype}）")

    motives = card.get("motives")
    if not isinstance(motives, dict):
        issues.append("模式卡缺少 motives 对象")
    else:
        primary = str(motives.get("primary") or "").strip()
        if not primary:
            issues.append("motives.primary 必填")
        elif primary not in MOTIVE_LABELS:
            issues.append(f"motives.primary 不在允许列表内（当前：{primary}）")

    verdict = card.get("verdict") if isinstance(card.get("verdict"), dict) else {}
    if verdict.get("kind") != "opinion":
        issues.append(f"模式卡 verdict.kind 必须是 opinion（当前：{verdict.get('kind') or '缺失'}）")
    fn = str(verdict.get("function") or "").strip()
    if not fn:
        issues.append("verdict.function 必填（使用规范中的英文键）")
    elif fn not in VERDICT_FUNCTIONS:
        issues.append(f"verdict.function 必须使用规范键，不能写成品句（当前：{fn[:40]}）")

    for idx, item in enumerate(_forbidden_transfers(card)):
        label = str(item).strip()
        if not label:
            continue
        if len(label) > FORBIDDEN_ITEM_MAX_LEN:
            issues.append(
                f"forbidden_transfers[{idx}] 应写短类别（≤{FORBIDDEN_ITEM_MAX_LEN} 字），不要写标题或原句"
            )
        if material and longest_shared_run(label, material) >= FORBIDDEN_COPY_MIN_RUN:
            issues.append(
                "forbidden_transfers 不宜复制素材原句，请改成类别（如「无出处倍数升级」「未证实因果」）"
            )
            break

    excerpt = str(card.get("evidence_excerpt") or "").strip()
    if not excerpt:
        issues.append("evidence_excerpt 必填（≤80 字实例锚点）")
    elif len(excerpt) > EVIDENCE_EXCERPT_MAX:
        issues.append(f"evidence_excerpt 超过 {EVIDENCE_EXCERPT_MAX} 字")
    elif material and excerpt == material:
        issues.append("evidence_excerpt 不能等于全文，请只留最短锚点")

    strings: list[tuple[str, str]] = []
    _walk_strings(card, "", strings)
    for path, text in strings:
        if path.endswith("evidence_excerpt") or path == "evidence_excerpt":
            continue
        chunk = (text or "").strip()
        if len(chunk) < COPY_MIN_RUN or not material:
            continue
        if longest_shared_run(chunk, material) >= COPY_MIN_RUN:
            issues.append(f"字段 {path} 与原文重复过多，请改成抽象表述")
            break

    return issues


def validate_stored_quality(card: dict, body: str) -> list[str]:
    """UI re-check when source material is no longer available."""
    issues: list[str] = []
    if not is_v2_card(card):
        issues.append("旧版或残缺模式卡，建议用当前规范重新拆卡")
        return issues
    for idx, item in enumerate(_forbidden_transfers(card)):
        if len(str(item).strip()) > FORBIDDEN_ITEM_MAX_LEN:
            issues.append(f"不宜照搬第 {idx + 1} 条像标题摘抄，应改成规则类别")
    text = (body or "").strip()
    if text and not any(cue in text for cue in BODY_INSTRUCTION_CUES):
        issues.append("打法正文像资讯摘要，不是给模型的写法说明")
    return issues


def card_preview_from_yaml(card: dict) -> dict[str, Any]:
    pattern = card.get("pattern") if isinstance(card.get("pattern"), dict) else {}
    hook = card.get("hook") if isinstance(card.get("hook"), dict) else {}
    motives = card.get("motives") if isinstance(card.get("motives"), dict) else {}
    frame = card.get("frame") if isinstance(card.get("frame"), dict) else {}
    verdict = card.get("verdict") if isinstance(card.get("verdict"), dict) else {}
    fn = str(verdict.get("function") or "").strip()
    moves_out: list[dict[str, str]] = []
    for move in card.get("moves") or []:
        if not isinstance(move, dict):
            continue
        moves_out.append(
            {
                "id": str(move.get("id") or ""),
                "function": str(move.get("function") or ""),
            }
        )
    primary = str(motives.get("primary") or "").strip()
    return {
        "pattern_name": str(pattern.get("name") or ""),
        "genre": str(pattern.get("genre") or ""),
        "genre_label": GENRES.get(str(pattern.get("genre") or ""), ""),
        "purpose": str(pattern.get("purpose") or ""),
        "moves": moves_out,
        "hook": {
            "archetype": str(hook.get("archetype") or ""),
            "archetype_label": HOOK_ARCHETYPES.get(str(hook.get("archetype") or ""), ""),
            "opening_slots": hook.get("opening_slots") if isinstance(hook.get("opening_slots"), list) else [],
            "payoff_contract": str(hook.get("payoff_contract") or ""),
        },
        "motives": {
            "primary": primary,
            "primary_label": MOTIVE_LABELS.get(primary, primary),
            "secondary": str(motives.get("secondary") or ""),
            "arousal": str(motives.get("arousal") or ""),
        },
        "frame": frame,
        "verdict_kind": str(verdict.get("kind") or ""),
        "verdict_function": fn,
        "verdict_function_label": VERDICT_FUNCTIONS.get(fn, fn),
        "forbidden_transfers": _forbidden_transfers(card),
        "evidence_excerpt": str(card.get("evidence_excerpt") or ""),
    }


def card_from_json(card_json: str | None) -> dict:
    if not card_json:
        return {}
    try:
        loaded = json.loads(card_json)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def ranking_preview_from_card(preview: dict[str, Any]) -> dict[str, Any]:
    moves = preview.get("moves") if isinstance(preview.get("moves"), list) else []
    move_functions = [
        str(m.get("function") or "")
        for m in moves
        if isinstance(m, dict) and str(m.get("function") or "").strip()
    ][:6]
    hook = preview.get("hook") if isinstance(preview.get("hook"), dict) else {}
    motives = preview.get("motives") if isinstance(preview.get("motives"), dict) else {}
    return {
        "pattern_name": str(preview.get("pattern_name") or ""),
        "genre_label": str(preview.get("genre_label") or ""),
        "purpose": str(preview.get("purpose") or ""),
        "move_functions": move_functions,
        "hook_archetype_label": str(hook.get("archetype_label") or hook.get("archetype") or ""),
        "motives_primary_label": str(
            motives.get("primary_label") or motives.get("primary") or ""
        ),
        "verdict_function_label": str(preview.get("verdict_function_label") or ""),
    }


def card_preview_from_stored(
    *,
    card_json: str | None,
    verdict_kind: str,
    verdict_function: str,
    forbidden_transfers_json: str,
    evidence_excerpt: str,
    include_evidence: bool = True,
) -> dict[str, Any]:
    if card_json:
        try:
            loaded = json.loads(card_json)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict) and loaded:
            preview = card_preview_from_yaml(loaded)
            if not preview.get("forbidden_transfers"):
                try:
                    extra = json.loads(forbidden_transfers_json or "[]")
                except json.JSONDecodeError:
                    extra = []
                if isinstance(extra, list) and extra:
                    preview["forbidden_transfers"] = [str(x) for x in extra]
            if not include_evidence:
                preview.pop("evidence_excerpt", None)
                preview.pop("forbidden_transfers", None)
            return preview
    try:
        forbidden = json.loads(forbidden_transfers_json or "[]")
    except json.JSONDecodeError:
        forbidden = []
    if not isinstance(forbidden, list):
        forbidden = []
    fn = (verdict_function or "").strip()
    out: dict[str, Any] = {
        "pattern_name": "",
        "genre": "",
        "genre_label": "",
        "purpose": "",
        "moves": [],
        "hook": {},
        "motives": {},
        "frame": {},
        "verdict_kind": verdict_kind or "",
        "verdict_function": fn,
        "verdict_function_label": VERDICT_FUNCTIONS.get(fn, fn),
        "forbidden_transfers": [str(x) for x in forbidden],
        "evidence_excerpt": evidence_excerpt or "",
        "legacy_card": True,
    }
    if not include_evidence:
        out.pop("evidence_excerpt", None)
        out.pop("forbidden_transfers", None)
    return out
