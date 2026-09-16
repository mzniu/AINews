# Douyin login selectors (Phase 2A spike)

| Field | Value |
|-------|-------|
| login_url | `https://creator.douyin.com/` |
| creator_url | `https://creator.douyin.com/creator-micro/content/upload` |
| success_url_excludes | `login`, `passport` |
| qr_selector | `null`（全页截图即可，QR 无需单独定位） |
| nickname_selector | `null`（暂用生成 UID；后续可补 DOM 昵称） |
| notes | 登录成功后需先进入创作者首页再导出 storage_state，否则缺少 `sessionid` 等 Cookie |
| post_login_url | `https://creator.douyin.com/creator-micro/home` |
| required_session_cookies | `sessionid`, `sessionid_ss`, `sid_guard` |

## 上传

| Field | Value |
|-------|-------|
| upload_url | `https://creator.douyin.com/creator-micro/content/upload` |
| file_input | `input[type="file"][accept*="video"]` 或通用 `input[type="file"]` |
| title_input | `input[placeholder*="标题"]` / `input[placeholder*="作品"]` |
| description_input | `textarea[placeholder*="简介"]` / `[contenteditable="true"]` |
| topic_input | `input[placeholder*="话题"]`（可选，标签也可写入简介） |
| ai_cover_container | `div[class*="recommendCoverContainer"]`（外层可能为 `recommendContainer`） |
| ai_cover_item | 容器内 `div[class*="recommendCover"]`（含 AI 标记 `div[class*="ai-"]`） |
| cover_checking | `[class*="coverChecking"]` 消失后再选封面 |
| publish_button | `button[class*="primary"][class*="fixed"]` 文本为「发布」 |
| strategy | 自动上传 → 等待转码 → 打开封面区 → **等待 AI 封面** → 选中 AI 封面 → 填写文案 → 自动点击发布 |

## Gate

**PASS** — 2026-08-06 登录 Spike PASS；发布流程按视频号同款半自动策略实现（待首次真实上传 E2E 验证 DOM）。

## 首评（First Comment）Spike

| Field | Value |
|-------|-------|
| probe_script | `scripts/probe_douyin_first_comment.py` |
| work_list_api | `GET /janus/douyin/creator/pc/work_list`（页内 `fetch`，见 metrics adapter） |
| manage_url | `https://creator.douyin.com/creator-micro/content/manage` |
| **confirmed_nav** | 内容管理 → 点击目标作品行 **评论数** → `.../interactive/comment?item_id={aweme_id}&enter_from=content_manage_v2` |
| public_video_url | `https://www.douyin.com/video/{aweme_id}`（备选；创作者会话下未走通时再用） |
| detail_url_candidates | `.../content/manage/detail?item_id={aweme_id}` 等（仅列表壳，须行内钻取） |
| comment_manage_url | `https://creator.douyin.com/creator-micro/interactive/comment?item_id={aweme_id}` |
| navigation_order | ① 作品管理行内点击 **评论数**（已验证）→ ② 公开视频页 → ③ 详情 URL + 行内钻取 → ④ 评论管理直达 |
| readiness_check | 仅以真实评论输入框为准（`placeholder` 含评论/说点/留下）；**勿**用页面「评论」列头误判 |
| anti_patterns | 勿点 `[class*="item"]` 等泛选择器（会误触侧栏跳到 `/home`）；导航后须校验 URL 非 `/creator-micro/home` |
| comment_input_candidates | `div.input-d24X73`、`[placeholder*="有爱评论"]`、`[contenteditable][data-placeholder*="说"]` 等 |
| comment_input_confirmed | `DIV.input-d24X73`，placeholder=`有爱评论，说点好听的~` |
| comment_submit_candidates | `button:has-text("发送")` |
| report | `data/publish/probe_douyin_first_comment_report.json` |
| screenshots | `data/publish/screenshots/probe_first_comment_*.png` |

### 运行方式

```bash
# 干跑（默认）：定位最近一条作品 + 评论框，不发送
python scripts/probe_douyin_first_comment.py

# 发布后模拟：先等 15s 再轮询作品列表（最多 60s）
python scripts/probe_douyin_first_comment.py --delay-sec 15 --wait-max-sec 60

# 匹配标题 / 指定作品
python scripts/probe_douyin_first_comment.py --title "关键词"
python scripts/probe_douyin_first_comment.py --video-id 7123456789012345678

# 真实发送测试评论（会出现在作品下，慎用）
python scripts/probe_douyin_first_comment.py --post --comment "你觉得这个数靠谱吗？"
```

### Spike 验收

| 结果 | 条件 |
|------|------|
| **PASS (dry-run)** | `work_list` 有作品 + 进入详情/互动页 + 找到评论输入框 |
| **PASS (--post)** | 上述 + 点击发送且页面可见评论文本 |
| **FAIL** | 会话过期 / 找不到作品 / 无法导航 / 无评论框 |

### Spike 结果

| 日期 | 账号 | video_id | gate | navigation | comment_input | elapsed_sec |
|------|------|----------|------|------------|---------------|-------------|
| 2026-08-29 | active douyin | `7673873560674290944` | **PASS_DRY_RUN** | `manage_row_comment_stat` → `interactive/comment?item_id=...` | `DIV.input-d24X73` / `有爱评论，说点好听的~` | ~21 |
| 2026-08-29 | active douyin | `7673873560674290944` | **PASS_POST** | 同上 | 同上；发送成功 | ~28 |

> 状态：**Spike 完全通过**（dry-run + `--post`）— P0 可冻结 selector 并实现 `post_douyin_first_comment`。
