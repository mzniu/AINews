# 背景音乐目录

将 MP3 放在此目录；成片与「视频制作」页会从 `/api/list-music-files` 读取列表。

## 案例曲目

| 文件 | 说明 |
|------|------|
| `Memories.mp3` | **内置案例**：抒情、适合纪年/资讯类竖屏，约 6.2 MB；已纳入 Git，新环境克隆后可直接选用 |

## 其他曲目

- 格式：MP3（推荐）
- 可自行添加更多 `*.mp3`（默认被 `.gitignore` 忽略，仅保留本机/安装包内使用）
- 未指定时流水线从本目录**随机**选一首（见 `config/render_templates.yaml` 的 `random_bgm`）

## 使用方式

1. **主页 / GitHub 成片**：背景音乐下拉框选择 `Memories` 或刷新列表后选用
2. **自动出片**：`random_bgm: true` 时随机抽取目录内 MP3
3. **手动路径**：`static/music/Memories.mp3`
