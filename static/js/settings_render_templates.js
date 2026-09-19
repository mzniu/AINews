(function () {
    let templates = [];
    let defaultId = '';
    let selectedId = '';
    let coverTimer = 0;
    let coverAbort = null;

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

    function renderList() {
        const list = $('renderTemplateList');
        if (!list) return;
        list.innerHTML = templates.map((item) => {
            const isDefault = item.id === defaultId;
            const active = item.id === selectedId ? ' scoring-weight-row-active' : '';
            return `<div class="scoring-weight-row${active}" data-template-id="${item.id}" style="cursor:pointer;">
                <div class="scoring-weight-head">
                    <strong>${item.label || item.id}</strong>
                    ${isDefault ? '<span class="badge">默认</span>' : ''}
                    <span class="hint">${item.layout_kind || ''} · ${(item.canvas && item.canvas.width) || '?'}×${(item.canvas && item.canvas.height) || '?'}</span>
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
            if (hint) hint.textContent = '改 YAML 后约 1 秒自动刷新封面。';
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

    async function fillEditor() {
        const item = selectedTemplate();
        if (!item) return;
        const canvas = item.canvas || {};
        $('renderTemplateMeta').textContent =
            `${item.label || item.id} · ${item.layout_kind} · ${canvas.width}×${canvas.height}` +
            ' · 封面与视频同尺寸，不写摘要';
        const editor = $('renderTemplateYaml');
        if (!editor) return;
        editor.value = '';
        try {
            const resp = await fetch(`/api/ingestion/render-templates/${encodeURIComponent(item.id)}`);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            editor.value = data.yaml || '';
            scheduleCoverPreview(0);
        } catch (err) {
            setStatus(err.message || String(err), 'error');
        }
    }

    async function loadRenderTemplateSettings() {
        setStatus('加载中…');
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
        setStatus('保存中…');
        try {
            const resp = await fetch(`/api/ingestion/render-templates/${encodeURIComponent(item.id)}/yaml`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ yaml: editor.value }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            if (data.yaml) editor.value = data.yaml;
            if (data.template) {
                templates = templates.map((row) => (row.id === data.template.id ? data.template : row));
            }
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
            if (hint) hint.textContent = '短视频预览约 3 秒；改 YAML 后封面仍会自动刷新。';
        } catch (err) {
            if (hint) hint.textContent = err.message || String(err);
            setStatus(err.message || String(err), 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    $('renderTemplateYaml')?.addEventListener('input', () => scheduleCoverPreview(1000));
    document.getElementById('saveRenderTemplateBtn')?.addEventListener('click', saveCurrent);
    document.getElementById('setDefaultRenderTemplateBtn')?.addEventListener('click', setDefault);
    document.getElementById('duplicateRenderTemplateBtn')?.addEventListener('click', duplicateCurrent);
    document.getElementById('previewRenderTemplateVideoBtn')?.addEventListener('click', previewVideoNow);

    window.loadRenderTemplateSettings = loadRenderTemplateSettings;
})();
