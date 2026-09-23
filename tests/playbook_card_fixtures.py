"""Valid pattern card v2 YAML for curate tests."""


def minimal_card_yaml(anchor: str = "三天") -> str:
    return f"""pattern:
  name: 对照节奏短评
  genre: short_news_commentary
  purpose: 用可核对对照制造争议并促完播
moves:
  - id: hook
    function: 点出主体与可核对数字
  - id: stance
    function: 问句收束留下可反驳点
hook:
  archetype: curiosity_gap
  opening_slots: [主体, 数字, 冲突]
  payoff_contract: 开场秒内点出核心对照
motives:
  primary: emotional_arousal
  arousal: high
transfer_rules:
  forbidden_transfers: []
verdict:
  kind: opinion
  function: controversy_commentary
evidence_excerpt: {anchor}
"""


MINIMAL_PLAYBOOK_BODY = """开场三秒内点出主体与可核对数字，制造信息缺口。
中段只用素材可核对事实，对照前置、不升级比较级。
结尾用问句收束，留下可反驳的争议点。"""


def minimal_diff_yaml(body: str | None = None) -> str:
    text = body if body is not None else MINIMAL_PLAYBOOK_BODY
    return "body: |\n  " + text.replace("\n", "\n  ") + "\n"


MINIMAL_ANALYSIS = """## Move 标注
- hook: 对照与可核对数字前置，形成信息缺口
- develop: 只用素材里可核对的事实收紧冲突
- stance: 问句收束，留下可反驳点

## Frame
- 放大：数字与对照关系
- 省略：未证实的因果链

## 动机推断
- primary: emotional_arousal
"""


def write_curate_draft_files(workspace, *, extra_body_line: str | None = None) -> None:
    drafts = workspace / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "analysis.md").write_text(MINIMAL_ANALYSIS, encoding="utf-8")
    (drafts / "card.yaml").write_text(minimal_card_yaml(), encoding="utf-8")
    body = MINIMAL_PLAYBOOK_BODY
    if extra_body_line:
        body = body + "\n" + extra_body_line
    (drafts / "playbook.diff.yaml").write_text(minimal_diff_yaml(body), encoding="utf-8")
