# 抖音观众评论回复 — 调研结论

> 探测时间：2026-09-06 · 脚本：`scripts/probe_douyin_audience_comment.py` · 报告：`data/publish/probe_douyin_audience_comment_report.json`

## 结论摘要

| 项 | 结论 |
|----|------|
| 可行性 | **可行** — 创作者中心评论管理页可列出观众评论，UI 有「回复」按钮 |
| 作品列表 | 复用 `GET /janus/douyin/creator/pc/work_list`（已有 metrics adapter） |
| 评论列表 | 页内拦截 / `fetch`：`.../comment/read/aweme/v1/web/comment/list/select/` |
| 回复方式 | **UI 自动化**（点击「回复」→ 填写 →「发送」），与首评共用评论管理页 |
| 与 Open API | 不依赖开放平台 OAuth；使用创作者 Web 会话 Cookie |

## 页面与导航

| 字段 | 值 |
|------|-----|
| 作品管理 | `https://creator.douyin.com/creator-micro/content/manage` |
| 评论管理（按作品） | `https://creator.douyin.com/creator-micro/interactive/comment?item_id={aweme_id}` |
| 已验证导航 | 内容管理 → `interactive/comment?item_id=...`（与首评相同，见 `douyin_comment.py`） |

探测样例：`aweme_id=7673873560674290944`，评论数 362，页面可见观众评论行及「回复 / 删除 / 举报」。

## 评论列表 API

```
GET https://creator.douyin.com/web/api/third_party/aweme/api/comment/read/aweme/v1/web/comment/list/select/
  ?aweme_id={aweme_id}&cursor={cursor}&count=20
  &comment_select_options=0&sort_options=0
  &channel_id=618&app_id=2906&aid=2906&device_platform=webapp
```

响应字段（实测）：

- `status_code: 0`
- `comments[]`：`cid`, `text`, `create_time`, `user.nickname`, `reply_comment_total`
- `cursor`, `has_more`, `total`

评论 ID 使用 `cid`（字符串）。`platform_post_id` 使用数字 `aweme_id` / `video_id`。

## 回复 UI

- 每条观众评论行末有 **「回复」** 按钮（页面文本已确认）
- 顶栏有 **「发送」** 按钮；回复时需在点击「回复」后出现行内输入框
- 首评输入框 `div.input-d24X73`（placeholder「有爱评论…」）与回复输入框需区分，避免误填首评框

## 已回复检测

- 列表项 `reply_comment` 非空时，直接核对子回复作者昵称
- `reply_comment_total > 0` 但 `reply_comment` 为空（折叠「查看 N 条回复」）时，调用子列表 API：
  ```
  GET .../comment/read/aweme/v1/web/comment/list/reply/
    ?item_id={aweme_id}&comment_id={cid}&cursor=0&count=20
  ```
- 扫描阶段：`fetch_douyin_comments_for_post` 对折叠线程补拉 reply list，设置 `already_replied_by_author`
- 发送前：`reply_douyin_audience_comment_on_active_feed` 再次校验，避免重复回复

## 实现方案（与微信/快手 inline 对齐）

1. 新增 `services/publishing/adapters/douyin_audience_reply.py`
2. `scan_douyin_inline` 接入 `CommentReplyOrchestrator`
3. `SUPPORTED_PLATFORMS` 增加 `douyin`
4. `config/publishing_platforms.yaml` → `comment_reply.platforms` 增加 `douyin`
5. 复用：`merge_post_backlog`、`intent=inline`、`resolve_inline_reply_text`

## 风险

| 风险 | 缓解 |
|------|------|
| `a_bogus` / `msToken` 签名 | 在已加载评论页内 `fetch`（带 Cookie），避免裸请求 |
| 合成 `platform_post_id`（`dy_*`） | 跳过或用标题匹配作品列表 |
| 同页连回多条 | `reset_douyin_comment_reply_ui` + 重试点击「回复」 |
