# Xiaohongshu selectors (login + video publish)

| Field | Value |
|-------|-------|
| login_url | `https://creator.xiaohongshu.com/login` |
| creator_url | `https://creator.xiaohongshu.com/publish/publish` |
| success_url_excludes | `login`, `passport` |
| qr_switch_selector | `.login-box-container img` (default页为短信登录，需先切到扫码) |
| post_login_url | `https://creator.xiaohongshu.com/new/home` |
| required_session_cookies | `galaxy_creator_session_id`（创作者域，优先）/ `access-token-creator.xiaohongshu.com` / `web_session`（任一即可） |

## Login

1. 打开 `login_url`，点击右上角二维码图标切换到「APP扫一扫登录」
2. 用小红书 App 扫码
3. 登录成功后跳转离开 `/login`，并写入含 `web_session` 的 storage state

排障：关闭代理/VPN；使用 Chromium 非 headless；若仍失败可重试扫码。

## Video publish

| Step | Selector / action |
|------|-------------------|
| 切换视频 Tab | 文案 `上传视频` 或 `div.creator-tab` |
| 上传文件 | `input.upload-input` → fallback `input[type="file"]` |
| 等待处理完成 | `.cover-container .preview-new` / `.reupload` / 文案「上传成功」 |
| 标题 | `div.edit-container input[type="text"]` / `input[placeholder*="标题"]` |
| 正文/话题 | `#quillEditor.ql-editor` / `div[contenteditable="true"]` |
| 发布 | `xhs-publish-btn` 调用 `_onPublish()`；兼容 `.publish-page-publish-btn button.bg-red` |

## Gate

**PASS (code)** — 启用 `xiaohongshu.enabled: true` 与 `video_publish: true`。  
**手动 E2E** — 运行 `python scripts/spike_xiaohongshu_publish.py --login-only` 绑定账号后，用 `--video` 验证上传填表。
