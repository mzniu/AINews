# Kuaishou selectors (login + video publish)

| Field | Value |
|-------|-------|
| login_url | `https://cp.kuaishou.com/` |
| creator_url | `https://cp.kuaishou.com/article/publish/video` |
| success_url_excludes | `login`, `passport` |
| qr_switch_selector | `text=扫码登录`（默认密码登录，需先切到扫码） |
| post_login_url | `https://cp.kuaishou.com/profile` |
| required_session_cookies | `kwssectoken`（创作者域，优先）/ `userId` / `passToken` / `kuaishou.server.web_st`（任一即可） |

## Login

1. 打开 `login_url`，未登录会跳转 `passport.kuaishou.com`
2. 点击「扫码登录」Tab，用快手 App 扫码
3. 登录成功后离开 `passport`/`login` 域名，并写入含创作者会话 Cookie 的 storage state

## Video publish

| Step | Selector / action |
|------|-------------------|
| 上传文件 | 优先 `input[type="file"]` 直传；若需点击按钮则用 `expect_file_chooser` 避免系统文件框卡住 |
| 离开上传窗 | 上传完成后点击「下一步」/「继续编辑」/「去编辑」等，直到出现标题或 `#work-description-edit` |
| 关闭新手引导 | `[data-action="skip"]` / `[aria-label="Skip"]`（`role="alertdialog"` 的 1/4 作品信息提示） |
| 标题 | `textarea[placeholder*="填写标题"]` |
| 描述/话题 | `#work-description-edit`（`contenteditable`）；**最多 4 个话题**，超出会被截断 |
| 发布 | `button:has-text("发布")` → 自动点击并等待成功 |

## Gate

**PASS (code)** — 启用 `kuaishou.enabled: true` 与 `video_publish: true`。  
**手动 E2E** — 运行 `python scripts/spike_kuaishou_publish.py --login-only` 绑定账号后，用 `--video` 验证上传填表。

## 首评（First Comment，P2）

| Field | Value |
|-------|-------|
| probe_script | `scripts/probe_creator_first_comment.py --platform kuaishou` |
| list_url | `https://cp.kuaishou.com/article/manage/video` |
| comment_hub_url | `https://cp.kuaishou.com/article/comment` |
| video_feed | `.comment-home-video`（按标题匹配） |
| comment_input | `.author-comment-input__row__input` |
| comment_submit | `.author-comment-input__row__btn`（文案「发布」） |
| mode | **deferred**（发布完成后独立会话发评） |
| report | `data/publish/probe_kuaishou_first_comment_report.json` |

## 观众评论回复（Audience Reply，P1）

| Field | Value |
|-------|-------|
| adapter | `services/publishing/adapters/kuaishou_audience_reply.py` |
| scan | 评论中心选作品 → 拦截 `*/comment/list*` API，DOM 兜底 |
| reply | 点击评论「回复」→ `textarea` / `contenteditable` → 「发送」 |
| audience_comment_item | `.comment-item` / `.comment-list-item` |
| stable_id | API `commentId` 或 `sha1(photo_id+author+content)` |

**Gate: PENDING** — 运行 probe dry-run + `--post` 验证后改为 PASS。
