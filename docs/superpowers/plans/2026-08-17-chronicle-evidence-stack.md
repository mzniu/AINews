# 小牛聊AI证据卡 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增内置成片模板 `chronicle_evidence_stack`（小牛聊AI证据卡）：品牌顶栏 → 白卡证据 → 卡下大标题（左侧青竖条）→ 浅青灰摘要；档案模板与系统默认均不变。

**Architecture:** 沿用 `layout_kind: chronicle_frame`。新模板只改 YAML 排版数字；`render_chronicle_frame` 增加 `title_placement` / `title_rule` / `summary_color` 开关。未知 `title_placement` 按 `above_card` 处理。不新增 layout_kind、不改 LLM 字段、不改 `card_motion` 逻辑。

**Tech Stack:** PyYAML, Pillow, pytest。设置页列表走现有 `list_render_templates()`，无需改前端。

**Spec:** `docs/superpowers/specs/2026-08-17-chronicle-evidence-stack-design.md`（已批准）

## Global Constraints

- 新模板 id 必须是 `chronicle_evidence_stack`，label 必须是 `小牛聊AI证据卡`，`builtin: true`，`layout_kind: chronicle_frame`
- `chronicle_archive_tech_blue` 的 YAML 与默认观感不得改（标题仍在卡上；`card_top_percent: 35`，`card_bottom_percent: 71`，`summary_y_percent: 70.2`）
- `default_template_id` 保持 `flash_news_portrait`；本轮不把证据卡设成系统默认
- 封面继续 `include_summary=False`；卡下标题仍要画
- 运镜继续读现有 `video.card_motion`，不改 `hero_motion_at` / `pick_card_motion_effect` / `resolve_card_motion`
- 不新增 LLM 字段；仍用 `main_line1` / `main_line2` / `sub_title` / `sub_title2` / `summary`
- 不做黄高亮 / 红字编号 / 邮件批注；不自动重渲旧片
- 未知 `title_placement` 视为 `above_card`，不抛错
- 用户未要求则不 git commit（仓库规则优先于本计划里的 commit 步）

## File map

| 文件 | 职责 |
|------|------|
| `config/render_templates.yaml` | 追加第三条内置模板；档案项原样不动 |
| `services/ingestion/chronicle_render.py` | 读 `layout.title_placement` / `title_top_percent` / `title_rule`；摘要 fill 优先 `typography.summary_color` |
| `tests/test_render_templates.py` | 仓库 YAML 能加载证据卡；默认模板仍是快讯竖屏 |
| `tests/test_chronicle_render.py` | 证据卡构图、竖条、摘要色、封面无摘要；档案标题仍在卡上 |
| `docs/superpowers/specs/2026-08-17-chronicle-evidence-stack-design.md` | 状态改为已批准 |

不改：`render_templates.py`（无 schema 白名单）、设置页 JS、封面/视频入口、口播生成。

---

### Task 1: Builtin YAML

**Files:**
- Modify: `config/render_templates.yaml`（在 `chronicle_archive_tech_blue` 之后追加一项；不要改已有两项）
- Modify: `tests/test_render_templates.py`（仓库内置加载测试）
- Modify: `docs/superpowers/specs/2026-08-17-chronicle-evidence-stack-design.md`（状态行）

**Interfaces:**
- Consumes: 现有 `get_render_template(id)` / `list_render_templates()` / `get_default_template_id()`
- Produces: 可解析的模板 dict，`id == "chronicle_evidence_stack"`，含下面 YAML 字段。后续任务用 `get_render_template("chronicle_evidence_stack")` 取完整 spec。

- [ ] **Step 1: Write the failing loader test**

在 `tests/test_render_templates.py` 把 `test_repo_builtin_yaml_loads_two_templates` 改名为 `test_repo_builtin_yaml_loads_three_templates`，并追加证据卡断言。默认模板断言必须保留：

```python
def test_repo_builtin_yaml_loads_three_templates():
    listed = list_render_templates()
    ids = {item["id"] for item in listed["templates"]}
    assert "flash_news_portrait" in ids
    assert "chronicle_archive_tech_blue" in ids
    assert "chronicle_evidence_stack" in ids
    assert listed["default_template_id"] == "flash_news_portrait"
    flash = get_render_template("flash_news_portrait")
    assert flash["canvas"] == {"width": 1080, "height": 1920, "fps": 24}
    chronicle = get_render_template("chronicle_archive_tech_blue")
    assert chronicle["cover"]["crop"] == "none"
    assert chronicle["cover"]["height"] == 1920
    assert chronicle["chrome"]["brand"] == "小牛聊AI"
    assert chronicle["chrome"]["mark_glyph"] == "牛"
    typo = chronicle["typography"]
    assert typo["subtitle_font_size"] == 47
    assert typo["title_font_size"] == 64
    assert typo["footer_font_size"] >= 40
    layout = chronicle.get("layout") or {}
    assert layout["card_top_percent"] == 35
    assert layout["card_bottom_percent"] == 71
    assert layout.get("title_placement") in (None, "above_card")
    assert typo["summary_y_percent"] == 70.2
    motion = (chronicle.get("video") or {}).get("card_motion") or {}
    assert motion["enabled"] is True
    assert motion["random"] is True
    assert float(motion["end_scale"]) >= 1.22
    assert "zoom_in" in motion["effects"]
    assert "pan_left" in motion["effects"]

    evidence = get_render_template("chronicle_evidence_stack")
    assert evidence["label"] == "小牛聊AI证据卡"
    assert evidence["builtin"] is True
    assert evidence["layout_kind"] == "chronicle_frame"
    elayout = evidence["layout"]
    assert elayout["title_placement"] == "below_card"
    assert elayout["card_top_percent"] == 18
    assert elayout["card_bottom_percent"] == 52
    assert elayout["card_left_percent"] == 8
    assert elayout["card_right_percent"] == 92
    assert elayout["card_inset_px"] == 16
    assert elayout["title_top_percent"] == 55
    assert elayout["title_rule"] is True
    assert elayout["title_rule_width_px"] == 4
    etypo = evidence["typography"]
    assert etypo["summary_y_percent"] == 75.0
    assert etypo["summary_color"] == "#9EC9D8"
    assert etypo["footer_y_percent"] == 85.2
    emotion = (evidence.get("video") or {}).get("card_motion") or {}
    assert emotion["enabled"] is True
    assert float(emotion["end_scale"]) >= 1.22
    assert evidence["chrome"]["brand"] == "小牛聊AI"
    assert evidence["palette"]["accent"] == "#3DDCFF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_render_templates.py::test_repo_builtin_yaml_loads_three_templates -v`

Expected: FAIL — `assert "chronicle_evidence_stack" in ids` 为 False，或 `unknown_render_template`。

- [ ] **Step 3: Add the builtin template and mark the spec approved**

把 spec 文件第一段状态从 `待用户确认后实施` 改为 `已批准实施`。

在 `config/render_templates.yaml` 的 `chronicle_archive_tech_blue` 整块之后追加（palette / chrome / video.card_motion 从档案模板复制，不要改档案那一项）：

```yaml
  - id: chronicle_evidence_stack
    label: 小牛聊AI证据卡
    builtin: true
    layout_kind: chronicle_frame
    canvas:
      width: 1080
      height: 1920
      fps: 24
    background_image: static/imgs/templates/chronicle_tech_blue/bg.png
    palette:
      bg: "#070B10"
      bg_glow: "#165A82"
      accent: "#3DDCFF"
      accent_dim: "#1A6A8A"
      text: "#F4F7FA"
      text_muted: "#8B96A8"
      card: "#FFFFFF"
      card_tab: "#070B10"
      frame: "#1A6A8A"
    chrome:
      brand: 小牛聊AI
      mark_glyph: 牛
      mark_path: static/imgs/templates/chronicle_tech_blue/mark_niu.png
      eyebrow: AI CHRONICLE / ARCHIVE RECORD
      brand_sub: 粉碎AI信息差 / 消除AI焦虑
      footer_left: AI 快讯
      card_keyword_fallback: 快讯
      footer_strip_prefixes:
        - 小牛说：
    typography:
      title_font_size: 64
      subtitle_font_size: 47
      brand_sub_font_size: 28
      footer_font_size: 40
      summary_y_percent: 75.0
      footer_y_percent: 85.2
      top_pad_percent: 5
      title_highlight_color: "#FFEC30"
      main_line1_color: "#F4F7FA"
      main_line2_color: "#F4F7FA"
      subtitle2_color: "#3DDCFF"
      title_y_percent: 12
      summary_color: "#9EC9D8"
    layout:
      title_placement: below_card
      card_top_percent: 18
      card_bottom_percent: 52
      card_left_percent: 8
      card_right_percent: 92
      card_inset_px: 16
      title_top_percent: 55
      title_rule: true
      title_rule_width_px: 4
    video:
      show_summary: false
      max_selected_images: 4
      random_bgm: true
      bgm_dir: static/music
      prepend_cover_intro: true
      cover_intro_frames: 1
      card_ken_burns: true
      ken_burns_end_scale: 1.22
      card_motion:
        enabled: true
        random: true
        end_scale: 1.22
        pan_percent: 70
        effects:
          - zoom_in
          - zoom_out
          - pan_left
          - pan_right
          - pan_up
          - pan_down
          - zoom_in_left
          - zoom_in_right
          - zoom_in_up
          - zoom_in_down
      clip_durations_by_count:
        1: [7.0]
        2: [3.5, 3.5]
        3: [2.5, 3.0, 3.0]
      clip_sec_when_at_least:
        count: 4
        sec: 2.0
      fallback_clip_sec: 2.5
    cover:
      enabled: true
      width: 1080
      height: 1920
      crop: none
      card_images: 1
```

确认文件顶部仍是：

```yaml
default_template_id: flash_news_portrait
```

档案模板的 `layout` 不要写入 `title_placement`（缺省即卡上标题）。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_render_templates.py::test_repo_builtin_yaml_loads_three_templates -v`

Expected: PASS

- [ ] **Step 5: Commit**

Skip unless the user asks. If asked:

```bash
git add config/render_templates.yaml tests/test_render_templates.py docs/superpowers/specs/2026-08-17-chronicle-evidence-stack-design.md
git commit -m "$(cat <<'EOF'
feat: add chronicle evidence-stack builtin template

EOF
)"
```

Windows PowerShell 没有 HEREDOC 时用：

```powershell
git commit -m "feat: add chronicle evidence-stack builtin template"
```

---

### Task 2: Title placement + title rule

**Files:**
- Modify: `services/ingestion/chronicle_render.py`（抽出标题绘制；按 placement 决定画在卡前还是卡后）
- Test: `tests/test_chronicle_render.py`

**Interfaces:**
- Consumes: Task 1 的 `get_render_template("chronicle_evidence_stack")`；现有 `render_chronicle_frame(...)`
- Produces: 私有辅助函数（不要改公开签名）

```python
def _title_placement(layout: dict[str, Any]) -> str:
    ...  # "below_card" or "above_card"

def _title_top_y(height: int, layout: dict[str, Any], typo: dict[str, Any]) -> int:
    ...

def _draw_title_block(
    draw: ImageDraw.ImageDraw,
    *,
    draft: dict[str, Any],
    title_x: int,
    title_top: int,
    title_max_w: int,
    title_font: ImageFont.ImageFont,
    subtitle_font: ImageFont.ImageFont,
    sub_size: int,
    text_color: tuple[int, int, int],
    title_hi: tuple[int, int, int],
    hook_color: tuple[int, int, int],
    title_keywords: list[str],
) -> int:
    ...  # returns y just below the last drawn title line
```

- [ ] **Step 1: Write the failing compositor tests**

在 `tests/test_chronicle_render.py` 追加（沿用文件里已有的 `_template` / `_red_image` / ImageDraw spy 写法）：

```python
def _evidence_template():
    return get_render_template("chronicle_evidence_stack")


def test_archive_title_stays_above_card(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    card_top = int(canvas_h * float((template.get("layout") or {}).get("card_top_percent", 35)) / 100.0)
    render_chronicle_frame(
        draft={"main_line1": "突发！档案标题"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    title_y = next(xy[1] for xy, text in drawn if "档案标题" in text)
    assert title_y < card_top


def test_evidence_title_sits_below_card(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _evidence_template()
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    card_bottom = int(
        canvas_h * float((template.get("layout") or {}).get("card_bottom_percent", 52)) / 100.0
    )
    title_top = int(
        canvas_h * float((template.get("layout") or {}).get("title_top_percent", 55)) / 100.0
    )
    render_chronicle_frame(
        draft={"main_line1": "突发！证据标题"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    title_y = next(xy[1] for xy, text in drawn if "证据标题" in text)
    assert title_y >= card_bottom
    assert title_y == title_top


def test_unknown_title_placement_keeps_archive_order(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _template()
    template.setdefault("layout", {})["title_placement"] = "sideways"
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    card_top = int(canvas_h * float(template["layout"].get("card_top_percent", 35)) / 100.0)
    render_chronicle_frame(
        draft={"main_line1": "突发！未知排版"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    title_y = next(xy[1] for xy, text in drawn if "未知排版" in text)
    assert title_y < card_top


def test_evidence_title_rule_uses_accent(tmp_path):
    img = _red_image(tmp_path / "shot.jpg")
    template = _evidence_template()
    canvas_w = int((template.get("canvas") or {}).get("width") or 1080)
    canvas_h = int((template.get("canvas") or {}).get("height") or 1920)
    title_top = int(canvas_h * float(template["layout"]["title_top_percent"]) / 100.0)
    rule_x = int(canvas_w * 0.045)
    frame = render_chronicle_frame(
        draft={"main_line1": "突发！证据标题"},
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=False,
    )
    sample = frame.getpixel((rule_x + 1, title_top + 20))
    assert sample[2] > sample[0] + 40
    assert sample[1] > 150
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_chronicle_render.py::test_archive_title_stays_above_card tests/test_chronicle_render.py::test_evidence_title_sits_below_card tests/test_chronicle_render.py::test_unknown_title_placement_keeps_archive_order tests/test_chronicle_render.py::test_evidence_title_rule_uses_accent -v`

Expected: `test_archive_title_stays_above_card` 可能已 PASS（现有画序就是卡上标题）。`test_evidence_title_sits_below_card` FAIL，因为 compositor 仍把标题画在约 16% 处，小于卡底 52%。`test_evidence_title_rule_uses_accent` FAIL，标题区左侧还是淡青细线或背景网格，不是 `#3DDCFF` 实心条。

- [ ] **Step 3: Implement placement + rule in the compositor**

在 `services/ingestion/chronicle_render.py` 的 `_layout_section` 附近加入：

```python
DEFAULT_TITLE_PLACEMENT = "above_card"


def _title_placement(layout: dict[str, Any] | None = None) -> str:
    value = str((layout or {}).get("title_placement") or DEFAULT_TITLE_PLACEMENT).strip().lower()
    if value == "below_card":
        return "below_card"
    return DEFAULT_TITLE_PLACEMENT


def _title_top_y(height: int, layout: dict[str, Any], typo: dict[str, Any]) -> int:
    if layout.get("title_top_percent") is not None:
        return _pct(float(layout["title_top_percent"]) / 100.0, height)
    return _pct(0.11 + _layout_top_pad(typo), height)
```

把 `render_chronicle_frame` 里绘制 `main_line1` / `main_line2` / `sub_title` / `sub_title2` 的循环抽成 `_draw_title_block`，返回最后一行下方的 y（给竖条定高度）。`sub_title2` 画完后要把该行字高算进返回值，否则竖条盖不住钩子行：

```python
def _draw_title_block(
    draw: ImageDraw.ImageDraw,
    *,
    draft: dict[str, Any],
    title_x: int,
    title_top: int,
    title_max_w: int,
    title_font: ImageFont.ImageFont,
    subtitle_font: ImageFont.ImageFont,
    sub_size: int,
    text_color: tuple[int, int, int],
    title_hi: tuple[int, int, int],
    hook_color: tuple[int, int, int],
    title_keywords: list[str],
) -> int:
    y = title_top
    for line in _wrap_line(str(draft.get("main_line1") or ""), title_font, title_max_w, draw)[:2]:
        _draw_highlighted_line(
            draw, title_x, y, line, title_font, text_color, title_hi, title_keywords
        )
        y += (draw.textbbox((0, 0), line, font=title_font)[3] - draw.textbbox((0, 0), line, font=title_font)[1]) + 8
    if draft.get("main_line2"):
        for line in _wrap_line(str(draft.get("main_line2")), subtitle_font, title_max_w, draw)[:1]:
            _draw_highlighted_line(
                draw, title_x, y, line, subtitle_font, text_color, title_hi, title_keywords
            )
            y += sub_size + 6
    if draft.get("sub_title"):
        for line in _wrap_line(str(draft.get("sub_title")), subtitle_font, title_max_w, draw)[:1]:
            draw.text((title_x, y), line, font=subtitle_font, fill=text_color)
            y += sub_size + 4
    if draft.get("sub_title2"):
        for line in _wrap_line(str(draft.get("sub_title2")), subtitle_font, title_max_w, draw)[:1]:
            draw.text((title_x, y), line, font=subtitle_font, fill=hook_color)
            bbox = draw.textbbox((0, 0), line, font=subtitle_font)
            y += (bbox[3] - bbox[1]) + 4
    return y
```

改 `render_chronicle_frame` 的画序（品牌 chrome 仍最先画）。删除现在无条件的「标题区淡青竖线 + 立刻画标题」；改成：

```python
    layout = _layout_section(template)
    placement = _title_placement(layout)
    title_top = _title_top_y(height, layout, typo)
    rule_x = _pct(0.045, width)
    title_x = rule_x + 18
    title_max_w = width - title_x - inset - 20
    title_blob = " ".join(str(draft.get(key) or "") for key in ("main_line1", "main_line2"))
    title_keywords = finalize_highlight_keywords(
        merge_summary_highlight_keywords(
            list(draft.get("highlight_keywords") or []),
            str(draft.get("tags") or ""),
        ),
        title_blob,
    )
    title_kwargs = dict(
        draft=draft,
        title_x=title_x,
        title_top=title_top,
        title_max_w=title_max_w,
        title_font=title_font,
        subtitle_font=subtitle_font,
        sub_size=sub_size,
        text_color=text_color,
        title_hi=title_hi,
        hook_color=hook_color,
        title_keywords=title_keywords,
    )

    if placement == "above_card":
        draw.line((rule_x, title_top, rule_x, title_top + _pct(0.14, height)), fill=accent_dim, width=2)
        _draw_title_block(draw, **title_kwargs)

    left, top, right, bottom = _card_box(width, height, template)
    draw.rounded_rectangle((left, top, right, bottom), radius=12, fill=card_color)
    # ... existing include_hero paste unchanged ...

    if placement == "below_card":
        title_bottom = _draw_title_block(draw, **title_kwargs)
        if bool(layout.get("title_rule")) and title_bottom > title_top:
            rule_w = max(1, int(layout.get("title_rule_width_px") or 4))
            draw.rectangle((rule_x, title_top, rule_x + rule_w, title_bottom), fill=accent)
```

要点：

- `above_card` 必须保留原来的 `accent_dim` 细竖线（档案回归依赖现有 chrome）。
- `below_card` **不要**在品牌和白卡之间画那条 14% 高的淡青线；竖条只出现在卡下标题旁，颜色用 `accent`（`#3DDCFF`）。
- 白卡 / hero 逻辑、`include_hero`、圆角半径不要改。
- `render_chronicle_cover` / `render_chronicle_video` 不要改签名；封面已经走同一 `render_chronicle_frame`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chronicle_render.py::test_archive_title_stays_above_card tests/test_chronicle_render.py::test_evidence_title_sits_below_card tests/test_chronicle_render.py::test_unknown_title_placement_keeps_archive_order tests/test_chronicle_render.py::test_evidence_title_rule_uses_accent tests/test_chronicle_render.py::test_chronicle_title_highlights_keyword tests/test_chronicle_render.py::test_chronicle_header_has_extra_top_space -v`

Expected: PASS

- [ ] **Step 5: Commit**

Skip unless the user asks. If asked: `feat: draw chronicle titles below the evidence card`

---

### Task 3: Summary color + cover skip

**Files:**
- Modify: `services/ingestion/chronicle_render.py`（摘要 fill）
- Test: `tests/test_chronicle_render.py`

**Interfaces:**
- Consumes: `typography.summary_color`（Task 1 YAML）；现有 `include_summary` 开关
- Produces: 视频帧摘要用 `#9EC9D8`；缺省时仍用 `palette.text`。封面不画摘要正文。

- [ ] **Step 1: Write the failing tests**

```python
def test_evidence_summary_uses_summary_color(tmp_path, monkeypatch):
    painted: list[tuple[object, str, object]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        painted.append((xy, str(text), kwargs.get("fill")))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _evidence_template()
    render_chronicle_frame(
        draft={
            "main_line1": "突发！证据标题",
            "summary": "小牛说：这是评论腔摘要",
        },
        image=Image.open(img).convert("RGB"),
        template=template,
        include_footer=True,
    )
    hits = [(text, fill) for _xy, text, fill in painted if "这是评论腔摘要" in text]
    assert hits
    assert hits[0][1] == (158, 201, 216)


def test_archive_summary_stays_white_without_summary_color(tmp_path, monkeypatch):
    painted: list[tuple[str, object]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        painted.append((str(text), kwargs.get("fill")))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    render_chronicle_frame(
        draft={"main_line1": "突发！档案标题", "summary": "小牛说：这是摘要正文"},
        image=Image.open(img).convert("RGB"),
        template=_template(),
        include_footer=True,
    )
    hits = [(text, fill) for text, fill in painted if "这是摘要正文" in text]
    assert hits
    assert hits[0][1] == (244, 247, 250)


def test_evidence_cover_skips_summary_keeps_title(tmp_path, monkeypatch):
    drawn: list[tuple[object, str]] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def spy(self, xy, text, **kwargs):
        drawn.append((xy, str(text)))
        return original(self, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    img = _red_image(tmp_path / "shot.jpg")
    template = _evidence_template()
    result = render_chronicle_cover(
        article_id="art_evidence_cover",
        draft={
            "main_line1": "突发！证据封面标题",
            "summary": "小牛说：这是不应出现的摘要",
        },
        image_path=str(img),
        template=template,
        output_dir=tmp_path,
    )
    assert result["success"] is True
    labels = [text for _, text in drawn]
    assert any("证据封面标题" in text for text in labels)
    assert not any("这是不应出现的摘要" in text for text in labels)
    footer_left = str((template.get("chrome") or {}).get("footer_left") or "AI 快讯")
    assert footer_left in labels
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_chronicle_render.py::test_evidence_summary_uses_summary_color tests/test_chronicle_render.py::test_archive_summary_stays_white_without_summary_color tests/test_chronicle_render.py::test_evidence_cover_skips_summary_keeps_title -v`

Expected: `test_evidence_summary_uses_summary_color` FAIL（fill 仍是 `(244, 247, 250)`）。封面测试在 Task 2 完成后应已 PASS（`include_summary=False` 已存在）；若 FAIL 再查 `render_chronicle_cover` 是否误传 `include_summary=True`。

- [ ] **Step 3: Prefer typography.summary_color**

在 `render_chronicle_frame` 的摘要绘制处，把 `_draw_highlighted_line` 的 base fill 从 `text_color` 改为：

```python
            summary_fill = _hex_rgb(typo.get("summary_color"), text_color)
            footer_hi = _hex_rgb(typo.get("footer_highlight_color"), accent)
            ...
                _draw_highlighted_line(
                    draw, fx, fy, line, footer_font, summary_fill, footer_hi, footer_keywords
                )
```

`_hex_rgb` 已存在；`#9EC9D8` → `(158, 201, 216)`。档案模板没有 `summary_color`，fallback 仍是白字。

不要改 `render_chronicle_cover` 的 `include_summary=False`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chronicle_render.py::test_evidence_summary_uses_summary_color tests/test_chronicle_render.py::test_archive_summary_stays_white_without_summary_color tests/test_chronicle_render.py::test_evidence_cover_skips_summary_keeps_title tests/test_chronicle_render.py::test_chronicle_summary_highlights_keyword tests/test_chronicle_render.py::test_chronicle_cover_skips_summary_keeps_chrome -v`

Expected: PASS。档案摘要高亮测试仍按 `xy[1] >= height * 0.70` 找 `DeepSeek`，证据卡不跑这条。

- [ ] **Step 5: Commit**

Skip unless the user asks. If asked: `feat: color chronicle evidence summaries separately from titles`

---

### Task 4: Regression

**Files:**
- Test only（不应再改产品代码，除非上一步漏了档案回归）

**Interfaces:**
- Consumes: Task 1–3 的 YAML + compositor
- Produces: 现有档案 / 模板加载测试全绿

- [ ] **Step 1: Run the focused suites**

Run: `python -m pytest tests/test_chronicle_render.py tests/test_render_templates.py tests/test_render_templates_api.py tests/test_media_pipeline_trigger.py -v`

Expected: 全部 PASS。`test_media_pipeline_trigger.py` 里默认 id 集合不必加入证据卡（自动出片仍用系统默认）。`test_render_templates_api.py` 用的是临时 YAML fixture，不必改。

若 `test_chronicle_card_contains_hero_image_not_gold` 或 `test_chronicle_layout_reads_card_and_summary_percents` 失败：先确认没有改档案 YAML 的 `card_top_percent` / `summary_y_percent`。

- [ ] **Step 2: Manual check (optional, not a code gate)**

设置页刷新后应出现「小牛聊AI证据卡」。不要把它设成默认，除非用户当场要求。资讯库「重新出片」选该模板可当次验证：品牌 → 白卡偏上 → 标题在卡下带青竖条 → 浅青灰摘要 →「AI 快讯」。

- [ ] **Step 3: Commit**

Skip unless the user asks.

---

## Self-review

| Spec 条款 | 对应任务 |
|-----------|----------|
| 新模板 id/label、复制 palette/chrome/card_motion | Task 1 |
| `title_placement: below_card`，卡 18%–52%，标题 55% | Task 1 YAML + Task 2 |
| 顶部只留品牌（卡上不再画标题/引语） | Task 2 `below_card` 跳过卡前标题 |
| `title_rule` 用 `accent` `#3DDCFF`，宽 4px | Task 2 |
| `summary_color: "#9EC9D8"`，封面不画摘要 | Task 3 |
| 不改档案模板、不改系统默认 | Task 1 断言 + Task 4 |
| 未知 placement → `above_card` | Task 2 |
| 不新增 layout_kind / LLM 字段 / 运镜逻辑 | 文件地图（不改那些模块） |
