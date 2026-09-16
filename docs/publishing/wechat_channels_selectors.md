# 微信视频号创作者中心选择器（Spike 产出）

> 探测日期：待填写  
> 登录 URL：https://channels.weixin.qq.com/login.html  
> 投稿 URL：https://channels.weixin.qq.com/platform/post/create

## 登录

- 登录 URL 必须使用**桌面 Chrome User-Agent**；若 UA 含 mobile/android/iphone 等关键字，`login.html` 会重定向到 `/mobile/mobile.html` 且无 QR DOM（`qr_helpers` 会在扫码前强制桌面 UA 并重试）
- QR 图片：嵌在 `#wx-oauth-container iframe`（`open.weixin.qq.com/connect/qrconnect`）内，优先 `img.js_qrcode_img.web_qrcode_img`（WeChat 会渲染多个隐藏副本，自动化取**第一个 visible** 节点）；加载失败时点 `.refresh-wrap` 重试；兜底截 `.qrcode-wrap`
- OAuth 加载失败时页面文案为「加载失败，点击重试」——此时应检查 `open.weixin.qq.com` 网络，而非仅更新选择器
- 登录成功判定：跳转离开 login 页或出现创作者中心元素

## 上传

- 文件 input：`input[type="file"]`（优先 `accept` 含 video/mp4 的 input）
- **上传完成检测**：等待「上传中/转码」消失，且出现标题/描述编辑区或视频预览后再填表
- 若点击发表时出现「请上传视频」，会自动等待并重试（最多 3 次）
- 标题输入：`textarea[placeholder*="标题"]`（待验证）
- 视频描述：`div.post-desc-box div.input-editor[data-placeholder="添加描述"]`（contenteditable）
- 描述内容按行填入：主标题第二行 → 副标题 → 副标题第二行 → 摘要 → `#标签`
- 声明原创：`.declare-original-checkbox label.ant-checkbox-wrapper` → 弹窗 `.original-proto-wrapper` 勾选协议 → 点击「声明原创」
- 发布按钮：`button:has-text("发表")` 或 `button:has-text("发布")`（待验证）
- **当前策略**：自动上传视频、填写标题/描述、声明原创后**自动点击发表**，并等待成功提示。
- 成功判定：`发表成功` / `发表完成` 等文案（含 `wujie-app` Shadow DOM）；或 URL 离开 `/platform/post/create`（如跳转到 `post/list`）

## 限制

- 标题最大字数：30（待 Spike 确认）
- 标签规则：待 Spike 确认

## 会话

- 观察有效期：待 Spike 观察

## Gate

**Gate: PENDING** — 运行 `python scripts/spike_wechat_channels_publish.py --login-only` 后完成一次真实上传，将 Gate 改为 PASS。

## 首评（First Comment，P2）

| Field | Value |
|-------|-------|
| probe_script | `scripts/probe_creator_first_comment.py --platform wechat_channels` |
| comment_hub_url | `https://channels.weixin.qq.com/platform/interaction/comment` |
| feed_selector | `.comment-feed-wrap`（优先选 0 评论作品） |
| activate_feed_api | `POST .../comment/update_feed_comment` `{ opType: 1, exportId }` |
| comment_list_api | `POST .../comment/comment_list` `{ exportId }` |
| write_tab | 点击「写评论」标签 |
| comment_input | `textarea.create-input[placeholder*="发表"]` |
| comment_submit | `.comment-create-wrap .tag-wrap.primary .tag-inner`（文案「发表」，非 button） |
| mode | **deferred**（发布完成后独立会话发评） |

流程：互动管理 → 评论 → 选中作品 →「写评论」→ 填写 `textarea.create-input` → 点击「发表」。

**Gate: PENDING** — 运行 `python scripts/probe_creator_first_comment.py --platform wechat_channels` 验证。
