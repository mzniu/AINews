# Plan errata：UserCenter 集成（spec v1.1）

> 日期：2026-09-17  
> 主文档：[2026-09-04-desktop-cloud-subscription-design.md](./2026-09-04-desktop-cloud-subscription-design.md) **v1.1**

实施计划 [2026-09-04-desktop-cloud-subscription.md](../plans/2026-09-04-desktop-cloud-subscription.md) 中以下条目 **已过时**，以本 errata + spec v1.1 为准：

| 计划中的项 | 处置 |
|------------|------|
| `cloud/app/routers/auth.py`（注册 / 登录 / JWT 签发） | **删除**；身份由 UserCenter + 桌面 `desktop/src-tauri/src/auth/` 承担 |
| Cloud 侧 `users.password_hash`、bcrypt 注册流 | **删除**；改用 `usercenter_accounts` + JWT 校验中间件 |
| `static/auth.html` 调「云 API」登录 | 改为调 **UserCenter** `/v1/auth/*`（或由 Tauri 内嵌 UI 直接调 UserCenter） |
| Phase P3「轻量云 Auth」 | 收窄为 **JWT 中间件 + subscriptions + entitlements**；桌面登录视为已完成 |
| 新增 Cloud 任务 | 实现 `AINEWS_AUTH_*` 配置、lazy-create workspace、`GET /me`（租户上下文） |

无需重写整份 implementation plan；实施 agent 开工 Cloud 前先读 spec §5.1–§5.5 与本文件。
