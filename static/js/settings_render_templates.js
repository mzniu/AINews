(function () {
    let templates = [];
    let defaultId = '';
    let selectedId = '';

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

    function fillEditor() {
        const item = selectedTemplate();
        if (!item) return;
        const canvas = item.canvas || {};
        const chrome = item.chrome || {};
        const palette = item.palette || {};
        $('renderTemplateMeta').textContent =
            `${item.label || item.id} · ${item.layout_kind} · ${canvas.width}×${canvas.height}` +
            ' · 封面与视频同尺寸，不写摘要';
        $('renderTemplateBrand').value = chrome.brand || '';
        $('renderTemplateGlyph').value = chrome.mark_glyph || '';
        $('renderTemplateAccent').value = palette.accent || '';
        $('renderTemplateBrand').disabled = item.layout_kind !== 'chronicle_frame';
        $('renderTemplateGlyph').disabled = item.layout_kind !== 'chronicle_frame';
        $('renderTemplateAccent').disabled = item.layout_kind !== 'chronicle_frame';
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
            fillEditor();
            setStatus(data.has_local_override ? '已加载（含本地覆盖）' : '已加载', 'ok');
        } catch (err) {
            setStatus(err.message || String(err), 'error');
        }
    }

    async function saveCurrent() {
        const item = selectedTemplate();
        if (!item) return;
        setStatus('保存中…');
        try {
            const patch = {};
            if (item.layout_kind === 'chronicle_frame') {
                patch.chrome = {
                    ...(item.chrome || {}),
                    brand: $('renderTemplateBrand').value.trim() || '小牛聊AI',
                    mark_glyph: $('renderTemplateGlyph').value.trim() || '牛',
                };
                patch.palette = {
                    ...(item.palette || {}),
                    accent: $('renderTemplateAccent').value.trim() || '#3DDCFF',
                };
            }
            const resp = await fetch(`/api/ingestion/render-templates/${encodeURIComponent(item.id)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(patch),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            await loadRenderTemplateSettings();
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

    document.getElementById('saveRenderTemplateBtn')?.addEventListener('click', saveCurrent);
    document.getElementById('setDefaultRenderTemplateBtn')?.addEventListener('click', setDefault);
    document.getElementById('duplicateRenderTemplateBtn')?.addEventListener('click', duplicateCurrent);

    window.loadRenderTemplateSettings = loadRenderTemplateSettings;
})();
