# 背景图选择器 + 预览缩略图 设计

## 背景

主页 `index.html` 的视频生成路径（`generateVideoDirectly` 与一键生成）当前不发送 `background_image_path`，永远走后端默认 `static/imgs/bg.png`，用户无法切换底图。GitHub 页 `github_video_maker.html` 已有 `<select id="github-background-select">` 列表（调用 `/api/list-background-images`）和上传按钮，但**无预览缩略图**，选图全凭文件名想象。

## 目标

- 主页：新增背景图下拉 + 旁边小预览缩略图，选中项透传到视频生成请求
- GitHub 页：在现有下拉旁加同款小预览缩略图
- 两页体验一致：选图即所见

## 非目标（YAGNI）

- 主页不上传按钮（GitHub 页已有上传入口，`static/imgs/backgrounds/` 两边共享）
- 不做网格视图、拖拽排序、收藏、localStorage 记忆
- 不改后端 API 结构（`/api/list-background-images` 与 `_resolve_background_image_path` 已就绪）
- 关键帧请求 `/api/generate-image` 不传 `background_image_path`（关键帧不渲染成片背景，与现状一致）

## UX

### 主页 index.html

在「🎬 生成视频」按钮所在的 `action-buttons` 行追加，与 BGM 选择器并排：

```
[🎬 生成视频]  [🎵 BGM 下拉]  [🖼️ 背景图下拉] [小预览图 60×107]
```

- `<select id="bgSelect">`：`class="ai-edit-input"`，与 `#bgmSelect` 同款样式（padding 10px 15px、border 2px solid var(--border-soft)、border-radius var(--radius-md)、font-size var(--fs-md)、min-width 200px、max-width 240px、text-overflow ellipsis）
- `<img id="bgPreview" alt="背景图预览">`：宽 60px、高 107px（9:16 与成片一致），border-radius var(--radius-sm)、border 1px solid var(--border-soft)、object-fit cover（非 9:16 图会裁切，但能直观看到成片取景）
- select `change` 时 `bgPreview.src = '/' + bgSelect.value`（前导 `/` 避免相对 URL 在子路径页面失效）
- 默认选 `static/imgs/bg.png`

### GitHub 页 github_video_maker.html

现有 `#github-background-select`（step4-options 内）旁加 `<img id="github-bg-preview" alt="背景图预览">`，同款 60×107 尺寸与样式。

## 数据流与后端

### 后端（无改动）

- `/api/list-background-images`（`api/routes/main_routes.py:88`）已返回 `{success, count, files: [{path, name}]}`，含 `static/imgs/bg.png` + `static/imgs/backgrounds/*`
- `/api/create-animated-video`（`api/routes/video_routes.py`）已支持 `background_image_path`，`_resolve_background_image_path` 白名单 `static/` 路径，越界或不存在回退默认 `bg.png`

### 主页前端串联（static/js/index/main.js）

新增 `loadBackgroundImageList()` 函数（仿 GitHub 页 `static/js/github_video_maker.js:1093` 同名函数）：

```js
async function loadBackgroundImageList() {
    const sel = document.getElementById('bgSelect');
    const preview = document.getElementById('bgPreview');
    if (!sel) return;
    const current = sel.value;
    try {
        const response = await fetch('/api/list-background-images');
        const data = await response.json();
        if (data.success && Array.isArray(data.files) && data.files.length) {
            sel.innerHTML = '';
            data.files.forEach((f) => {
                const opt = document.createElement('option');
                opt.value = f.path;
                opt.textContent = f.name || f.path.split('/').pop();
                sel.appendChild(opt);
            });
            if (current && [...sel.options].some((o) => o.value === current)) {
                sel.value = current;
            }
        }
    } catch (e) {
        console.error('加载背景图列表失败:', e);
    } finally {
        // 无论成功失败都初始化预览，避免空白
        if (preview) preview.src = '/' + (sel.value || 'static/imgs/bg.png');
    }
}

// 页面初始化时调用一次
loadBackgroundImageList();
// 用 onchange 而非 addEventListener 避免重复绑定（本函数可能被多次调用）
sel.onchange = () => {
    const preview = document.getElementById('bgPreview');
    if (preview) preview.src = '/' + sel.value;
};
```

`generateVideoDirectly()`（main.js 约 2467 行 fetch body）请求体追加：
```js
background_image_path: document.getElementById('bgSelect')?.value || 'static/imgs/bg.png',
```

一键生成路径（main.js 约 2984 行 fetch body）请求体追加同款字段。

### GitHub 页前端串联（static/js/github_video_maker.js）

`loadBackgroundImageList()`（1093 行）填充后追加预览初始化与 change 监听，使用 `onchange` 避免监听器累积（此函数在 init 与 upload 后都会被调用）：
```js
const preview = document.getElementById('github-bg-preview');
if (preview) preview.src = '/' + (sel.value || 'static/imgs/bg.png');
sel.onchange = () => {
    const p = document.getElementById('github-bg-preview');
    if (p) p.src = '/' + sel.value;
};
```

**上传后预览同步**（关键 bugfix）：现有上传 handler 在 `github_video_maker.js:1222-1224` 调 `loadBackgroundImageList()` 后用 `s.value = data.path` 设置选中项——但程序化赋值 `.value` **不触发 change 事件**，导致预览图停留在旧图。修改为：
```js
await loadBackgroundImageList();
const s = document.getElementById('github-background-select');
if (s) {
    s.value = data.path;
    s.dispatchEvent(new Event('change'));  // 触发 onchange 回调更新预览
}
```

`generateActualVideo()`（619 行）已在请求体传 `background_image_path: backgroundPath`（658 行），无需改。

## 错误处理与回退

- 主页首次加载若 `/api/list-background-images` 失败或返回空：`bgSelect` 保留 HTML 里写死的 `<option value="static/imgs/bg.png">默认背景</option>`，`finally` 块把预览图指向它
- `bgPreview` `onerror` 隐藏自己（`this.style.display='none'`），不报错
- `_resolve_background_image_path` 已对越界路径做白名单校验，前端传任何值都安全

## 测试

- 语法：本特性无 Python 改动，仅 JS 用 `node --check static/js/index/main.js` 与 `node --check static/js/github_video_maker.js` 校验
- 浏览器冒烟测试（启动 `web_server.py` 后）：
  1. 主页加载后 `bgSelect` 至少有 1 项（`static/imgs/bg.png`），预览图可见
  2. 主页切换选项，预览图同步变化
  3. 主页生成视频，确认成片背景与选中项一致
  4. GitHub 页 step4 加载后，预览图同步当前选中项
  5. GitHub 页切换选项，预览同步
  6. **GitHub 页上传新背景图，预览自动切到新上传的图**（验证 `dispatchEvent` 修复）

## 受影响文件

| 文件 | 改动 |
|---|---|
| `static/index.html` | 新增 `bgSelect` + `bgPreview` 标记 |
| `static/js/index/main.js` | 新增 `loadBackgroundImageList()`、初始化调用、change 监听、`generateVideoDirectly` 与一键生成请求体加 `background_image_path` |
| `static/github_video_maker.html` | 现有 `github-background-select` 旁加 `github-bg-preview` img |
| `static/js/github_video_maker.js` | `loadBackgroundImageList` 末尾初始化预览 + change 监听 |
