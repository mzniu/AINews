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
| ai_cover_container | `div[class*="recommendCoverContainer"]` |
| ai_cover_item | 容器内第一个 `div[class*="recommendCover"]`（含 AI 标记 `div[class*="ai-"]`） |
| publish_button | `button[class*="primary"][class*="fixed"]` 文本为「发布」 |
| strategy | 自动上传 → 等待转码 → 尝试选推荐封面（可选）→ 填写文案 → 自动点击发布 |

## Gate

**PASS** — 2026-08-06 登录 Spike PASS；发布流程按视频号同款半自动策略实现（待首次真实上传 E2E 验证 DOM）。
