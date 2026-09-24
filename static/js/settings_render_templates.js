(function () {
    let templates = [];
    let defaultId = '';
    let selectedId = '';
    let currentSpec = null;
    let currentSchema = { groups: [], fields: [] };
    let coverTimer = 0;
    let coverAbort = null;
    let syncing = false;

    const $ = (id) => document.getElementById(id);

    function setStatus(text, type = '') {
        const bar = $('renderTemplateStatusBar');
        if (!bar) return;
        bar.textContent = text;
        bar.className = 'status-bar' + (type ? ` ${type}` : '');
    }

    function selectedTemplate() {
        return templates.find((item) => item.id === selectedId) || templates[0];
    }

    function getPath(obj, path) {
        if (!obj || !path) return undefined;
        return path.split('.').reduce((acc, key) => (acc == null ? acc : acc[key]), obj);
    }

    function setPath(obj, path, value) {
        const keys = path.split('.');
        let cursor = obj;
        for (let i = 0; i < keys.length - 1; i += 1) {
            const key = keys[i];
            if (cursor[key] == null || typeof cursor[key] !== 'object' || Array.isArray(cursor[key])) {
                cursor[key] = {};
            }
            cursor = cursor[key];
        }
        cursor[keys[keys.length - 1]] = value;
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function stripEolComment(line) {
        let inSingle = false;
        let inDouble = false;
        for (let i = 0; i < line.length; i += 1) {
            const ch = line[i];
            if (ch === "'" && !inDouble) inSingle = !inSingle;
            else if (ch === '"' && !inSingle) inDouble = !inDouble;
            else if (ch === '#' && !inSingle && !inDouble) {
                return line.slice(0, i).trimEnd();
            }
        }
        return line;
    }

    function splitFlowList(inner) {
        const parts = [];
        let buf = '';
        let inSingle = false;
        let inDouble = false;
        for (let i = 0; i < inner.length; i += 1) {
            const ch = inner[i];
            if (ch === "'" && !inDouble) inSingle = !inSingle;
            else if (ch === '"' && !inSingle) inDouble = !inDouble;
            else if (ch === ',' && !inSingle && !inDouble) {
                parts.push(buf.trim());
                buf = '';
                continue;
            }
            buf += ch;
        }
        if (buf.trim()) parts.push(buf.trim());
        return parts;
    }

    function parseScalar(raw) {
        const text = String(raw ?? '').trim();
        if (text === '') return '';
        if (text === 'true') return true;
        if (text === 'false') return false;
        if (text === 'null') return null;
        if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
            return text.slice(1, -1);
        }
        if (text.startsWith('[') && text.endsWith(']')) {
            const inner = text.slice(1, -1).trim();
            if (!inner) return [];
            return splitFlowList(inner).map(parseScalar);
        }
        if (/^-?\d+$/.test(text)) return Number(text);
        if (/^-?\d+\.\d+$/.test(text)) return Number(text);
        return text;
    }

    function parseYaml(text) {
        const lines = String(text || '').replace(/\t/g, '  ').split(/\r?\n/);
        const root = {};
        const stack = [{ indent: -1, container: root }];
        lines.forEach((rawLine) => {
            const withoutComment = stripEolComment(rawLine);
            if (!withoutComment.trim()) return;
            const indent = withoutComment.match(/^ */)[0].length;
            const trimmed = withoutComment.trim();
            while (stack.length > 1 && indent <= stack[stack.length - 1].indent) {
                stack.pop();
            }
            const parent = stack[stack.length - 1].container;
            const colon = trimmed.indexOf(':');
            if (colon < 0) return;
            const keyRaw = trimmed.slice(0, colon).trim();
            const rest = trimmed.slice(colon + 1).trim();
            const key = /^-?\d+$/.test(keyRaw) ? Number(keyRaw) : keyRaw;
            if (rest === '') {
                const nested = {};
                parent[key] = nested;
                stack.push({ indent, container: nested });
            } else {
                parent[key] = parseScalar(rest);
            }
        });
        return root;
    }

    function yamlScalar(value) {
        if (value === true) return 'true';
        if (value === false) return 'false';
        if (value === null || value === undefined) return 'null';
        if (typeof value === 'number') return String(value);
        const text = String(value);
        if (text === '') return '""';
        if (/[:#\[\]\{\},&*!|>'"%@`]/.test(text) || /^\s|\s$/.test(text) || /^-/.test(text)) {
            return JSON.stringify(text);
        }
        return text;
    }

    function dumpAnnotated(data, fields) {
        const labels = {};
        (fields || []).forEach((item) => {
            if (item && item.path && item.label) labels[item.path] = item.label;
        });
        const lines = [];
        function emit(obj, indent, prefix) {
            const pad = '  '.repeat(indent);
            Object.keys(obj || {}).forEach((key) => {
                const value = obj[key];
                const path = prefix ? `${prefix}.${key}` : String(key);
                const comment = labels[path] ? `  # ${labels[path]}` : '';
                if (value && typeof value === 'object' && !Array.isArray(value)) {
                    lines.push(`${pad}${key}:${comment}`);
                    emit(value, indent + 1, path);
                    return;
                }
                if (Array.isArray(value)) {
                    const flow = value.map((item) => yamlScalar(item)).join(', ');
                    lines.push(`${pad}${key}: [${flow}]${comment}`);
                    return;
                }
                lines.push(`${pad}${key}: ${yamlScalar(value)}${comment}`);
            });
        }
        emit(data, 0, '');
        return `${lines.join('\n')}\n`;
    }

    function currentYaml() {
        return dumpAnnotated(currentSpec || {}, currentSchema.fields || []);
    }

    function syncYamlFromSpec() {
        const editor = $('renderTemplateYaml');
        if (!editor || !currentSpec) return;
        editor.value = currentYaml();
    }

    function renderList() {
        const list = $('renderTemplateList');
        if (!list) return;
        list.innerHTML = templates.map((item) => {
            const isDefault = item.id === defaultId;
            const active = item.id === selectedId ? ' scoring-weight-row-active' : '';
            return `<div class="scoring-weight-row${active}" data-template-id="${item.id}" style="cursor:pointer;">
                <div class="scoring-weight-head">
                    <strong>${escapeHtml(item.label || item.id)}</strong>
                    ${isDefault ? '<span class="badge">默认</span>' : ''}
                    <span class="hint">${escapeHtml(item.layout_kind || '')} · ${(item.canvas && item.canvas.width) || '?'}×${(item.canvas && item.canvas.height) || '?'}</span>
                </div>
            </div>`;
        }).join('');
        list.querySelectorAll('[data-template-id]').forEach((row) => {
            row.addEventListener('click', () => {
                selectedId = row.getAttribute('data-template-id');
                fillEditor();
                renderList();
            });
        });
    }

    function widgetControl(field, value) {
        const path = escapeHtml(field.path);
        const widget = field.widget || 'text';
        if (widget === 'bool') {
            return `<label class="field-label"><input type="checkbox" data-path="${path}" data-widget="bool"${value ? ' checked' : ''}> 启用</label>`;
        }
        if (widget === 'enum') {
            const options = (field.options || []).map((opt) => {
                const selected = String(value ?? '') === String(opt) ? ' selected' : '';
                return `<option value="${escapeHtml(opt)}"${selected}>${escapeHtml(opt)}</option>`;
            }).join('');
            return `<select class="form-control" data-path="${path}" data-widget="enum">${options}</select>`;
        }
        if (widget === 'color') {
            const hex = /^#[0-9A-Fa-f]{6}$/.test(String(value || '')) ? String(value) : '#000000';
            return `<div class="render-template-color-row">
                <input type="color" data-path="${path}" data-widget="color" value="${escapeHtml(hex)}">
                <input class="form-control" type="text" data-path="${path}" data-widget="color-text" value="${escapeHtml(value ?? '')}" placeholder="#000000">
            </div>`;
        }
        if (widget === 'list') {
            let text = '';
            if (Array.isArray(value)) text = value.join('\n');
            else if (value && typeof value === 'object') text = JSON.stringify(value, null, 2);
            else if (value != null && value !== '') text = String(value);
            return `<textarea class="form-control" rows="4" data-path="${path}" data-widget="list">${escapeHtml(text)}</textarea>`;
        }
        if (widget === 'number' || widget === 'percent') {
            const extra = widget === 'percent' ? ' <span class="hint">%</span>' : '';
            const shown = value == null ? '' : value;
            return `<input class="form-control" type="number" step="any" data-path="${path}" data-widget="${widget}" value="${escapeHtml(shown)}">${extra}`;
        }
        const shown = value == null ? '' : value;
        return `<input class="form-control" type="text" data-path="${path}" data-widget="${widget}" value="${escapeHtml(shown)}">`;
    }

    function renderForm() {
        const root = $('renderTemplateForm');
        if (!root) return;
        const fields = currentSchema.fields || [];
        const groups = currentSchema.groups || [];
        const grouped = new Map();
        groups.forEach((group) => grouped.set(group.id, []));
        fields.forEach((field) => {
            const gid = field.group || 'identity';
            if (!grouped.has(gid)) grouped.set(gid, []);
            grouped.get(gid).push(field);
        });
        const html = groups.map((group) => {
            const items = grouped.get(group.id) || [];
            if (!items.length) return '';
            const body = items.map((field) => {
                const value = getPath(currentSpec, field.path);
                return `<div class="render-template-field">
                    <label class="field-label">${escapeHtml(field.label || field.path)}</label>
                    ${widgetControl(field, value)}
                    ${field.help ? `<p class="hint">${escapeHtml(field.help)}</p>` : ''}
                </div>`;
            }).join('');
            return `<details class="render-template-group" open>
                <summary>${escapeHtml(group.label || group.id)}</summary>
                ${body}
            </details>`;
        }).join('');
        root.innerHTML = html || '<p class="hint">当前布局没有可编辑字段。</p>';
    }

    function coerceFieldValue(field, raw, checked) {
        const widget = (field && field.widget) || 'text';
        if (widget === 'bool') return Boolean(checked);
        if (widget === 'number' || widget === 'percent') {
            if (raw === '' || raw == null) return null;
            const num = Number(raw);
            return Number.isFinite(num) ? num : raw;
        }
        if (widget === 'list') {
            const text = String(raw || '').trim();
            if (!text) return [];
            if (text.startsWith('{') || text.startsWith('[')) {
                try {
                    return JSON.parse(text);
                } catch (err) {
                    return text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
                }
            }
            return text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        }
        return raw;
    }

    function fieldByPath(path) {
        return (currentSchema.fields || []).find((item) => item.path === path);
    }

    function applyControl(target) {
        const path = target.getAttribute('data-path');
        if (!path || !currentSpec) return;
        const field = fieldByPath(path);
        const widget = target.getAttribute('data-widget');
        let value;
        if (widget === 'bool') value = coerceFieldValue(field, target.value, target.checked);
        else if (widget === 'color' || widget === 'color-text') value = target.value;
        else value = coerceFieldValue(field, target.value, target.checked);
        if (value === null && (widget === 'number' || widget === 'percent')) return;
        setPath(currentSpec, path, value);
        if (widget === 'color' || widget === 'color-text') {
            const form = $('renderTemplateForm');
            form?.querySelectorAll(`[data-path="${path}"]`).forEach((el) => {
                if (el === target) return;
                if (el.getAttribute('data-widget') === 'color' && /^#[0-9A-Fa-f]{6}$/.test(String(value || ''))) {
                    el.value = value;
                }
                if (el.getAttribute('data-widget') === 'color-text') el.value = value;
            });
        }
        syncYamlFromSpec();
        scheduleCoverPreview(1000);
    }

    function showCover(url) {
        const img = $('renderTemplatePreviewImg');
        const video = $('renderTemplatePreviewVideo');
        if (video) {
            video.pause();
            video.removeAttribute('src');
            video.hidden = true;
        }
        if (img && url) {
            img.src = url;
            img.hidden = false;
        }
    }

    async function previewCoverNow() {
        const editor = $('renderTemplateYaml');
        const hint = $('renderTemplatePreviewHint');
        if (!editor || !editor.value.trim()) return;
        if (coverAbort) coverAbort.abort();
        coverAbort = new AbortController();
        if (hint) hint.textContent = '正在渲染封面…';
        try {
            const resp = await fetch('/api/ingestion/render-templates/preview-cover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ yaml: editor.value }),
                signal: coverAbort.signal,
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            showCover(data.image_url);
            if (hint) hint.textContent = '改表单或 YAML 后约 1 秒自动刷新封面。';
        } catch (err) {
            if (err && err.name === 'AbortError') return;
            if (hint) hint.textContent = err.message || String(err);
        }
    }

    function scheduleCoverPreview(delayMs) {
        window.clearTimeout(coverTimer);
        coverTimer = window.setTimeout(() => {
            previewCoverNow();
        }, delayMs);
    }

    function applyYamlToForm() {
        const editor = $('renderTemplateYaml');
        if (!editor || !editor.value.trim()) return;
        try {
            const parsed = parseYaml(editor.value);
            if (!parsed || typeof parsed !== 'object') return;
            currentSpec = parsed;
            syncing = true;
            renderForm();
            syncing = false;
        } catch (err) {
            const hint = $('renderTemplatePreviewHint');
            if (hint) hint.textContent = err.message || String(err);
        }
    }

    async function fillEditor() {
        const item = selectedTemplate();
        if (!item) return;
        const canvas = item.canvas || {};
        $('renderTemplateMeta').textContent =
            `${item.label || item.id} · ${item.layout_kind} · ${canvas.width}×${canvas.height}` +
            ' · 封面与视频同尺寸，不写摘要 · layout_kind 只读';
        const editor = $('renderTemplateYaml');
        try {
            const resp = await fetch(`/api/ingestion/render-templates/${encodeURIComponent(item.id)}`);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            currentSpec = data.template || {};
            currentSchema = data.schema || { groups: [], fields: [] };
            renderForm();
            if (editor) editor.value = data.yaml || currentYaml();
            scheduleCoverPreview(0);
        } catch (err) {
            setStatus(err.message || String(err), 'error');
        }
    }

    async function refreshRenderTemplateEngineBanner() {
        const banner = $('renderTemplateEngineBanner');
        if (!banner) return;
        try {
            const resp = await fetch('/api/runtime/video-renderer');
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            const active = data.active === 'remotion' ? 'Remotion' : 'Python';
            banner.hidden = false;
            banner.className = 'status-bar ok';
            banner.innerHTML =
                `当前出片引擎：<strong>${active}</strong>（首选 ${data.preferred}）` +
                ' — <a href="/settings.html#video-renderer">在「成片引擎」中修改</a>';
        } catch (_err) {
            banner.hidden = true;
        }
    }

    async function loadRenderTemplateSettings() {
        setStatus('加载中…');
        refreshRenderTemplateEngineBanner();
        try {
            const resp = await fetch('/api/ingestion/render-templates');
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            templates = data.templates || [];
            defaultId = data.default_template_id || '';
            selectedId = selectedId && templates.some((t) => t.id === selectedId) ? selectedId : defaultId;
            renderList();
            await fillEditor();
            setStatus(data.has_local_override ? '已加载（含本地覆盖）' : '已加载', 'ok');
        } catch (err) {
            setStatus(err.message || String(err), 'error');
        }
    }

    async function saveCurrent() {
        const item = selectedTemplate();
        const editor = $('renderTemplateYaml');
        if (!item || !editor) return;
        if (currentSpec) syncYamlFromSpec();
        setStatus('保存中…');
        try {
            const resp = await fetch(`/api/ingestion/render-templates/${encodeURIComponent(item.id)}/yaml`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ yaml: editor.value }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            if (data.template) {
                currentSpec = data.template;
                templates = templates.map((row) => (row.id === data.template.id ? data.template : row));
            }
            if (data.yaml) editor.value = data.yaml;
            renderForm();
            renderList();
            scheduleCoverPreview(0);
            setStatus('已保存', 'ok');
        } catch (err) {
            setStatus(err.message || String(err), 'error');
        }
    }

    async function setDefault() {
        const item = selectedTemplate();
        if (!item) return;
        setStatus('设置默认…');
        try {
            const resp = await fetch('/api/ingestion/render-templates/default', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ template_id: item.id }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            await loadRenderTemplateSettings();
            setStatus('已设为默认，之后自动出片将使用此模板', 'ok');
        } catch (err) {
            setStatus(err.message || String(err), 'error');
        }
    }

    async function duplicateCurrent() {
        const item = selectedTemplate();
        if (!item) return;
        const newId = `${item.id}_${Date.now().toString(36)}`;
        setStatus('复制中…');
        try {
            const resp = await fetch(`/api/ingestion/render-templates/${encodeURIComponent(item.id)}/duplicate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_id: newId, label: `${item.label || item.id} 副本` }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            selectedId = data.template && data.template.id;
            await loadRenderTemplateSettings();
            setStatus('已复制', 'ok');
        } catch (err) {
            setStatus(err.message || String(err), 'error');
        }
    }

    async function previewVideoNow() {
        const editor = $('renderTemplateYaml');
        const btn = $('previewRenderTemplateVideoBtn');
        const hint = $('renderTemplatePreviewHint');
        const img = $('renderTemplatePreviewImg');
        const video = $('renderTemplatePreviewVideo');
        if (!editor || !video) return;
        if (currentSpec) syncYamlFromSpec();
        if (btn) btn.disabled = true;
        if (hint) hint.textContent = '正在渲染短视频…';
        try {
            const resp = await fetch('/api/ingestion/render-templates/preview-video', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ yaml: editor.value }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            if (img) img.hidden = true;
            video.src = data.video_url;
            video.hidden = false;
            video.play().catch(() => {});
            if (hint) hint.textContent = '短视频预览约 3 秒；改表单后封面仍会自动刷新。';
        } catch (err) {
            if (hint) hint.textContent = err.message || String(err);
            setStatus(err.message || String(err), 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    $('renderTemplateForm')?.addEventListener('input', (event) => {
        if (syncing) return;
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.getAttribute('data-path')) return;
        applyControl(target);
    });
    $('renderTemplateForm')?.addEventListener('change', (event) => {
        if (syncing) return;
        const target = event.target;
        if (!(target instanceof HTMLElement) || !target.getAttribute('data-path')) return;
        applyControl(target);
    });
    $('renderTemplateYaml')?.addEventListener('input', () => {
        window.clearTimeout(coverTimer);
        coverTimer = window.setTimeout(() => {
            applyYamlToForm();
            previewCoverNow();
        }, 1000);
    });
    document.getElementById('saveRenderTemplateBtn')?.addEventListener('click', saveCurrent);
    document.getElementById('setDefaultRenderTemplateBtn')?.addEventListener('click', setDefault);
    document.getElementById('duplicateRenderTemplateBtn')?.addEventListener('click', duplicateCurrent);
    document.getElementById('previewRenderTemplateVideoBtn')?.addEventListener('click', previewVideoNow);

    window.loadRenderTemplateSettings = loadRenderTemplateSettings;
    window.refreshRenderTemplateEngineBanner = refreshRenderTemplateEngineBanner;
})();
