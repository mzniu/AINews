(function () {
    const FIELD_MAP = {
        system_role: 'titlePromptSystemRole',
        content_formula: 'titlePromptFormula',
        main_line1_patterns: 'titlePromptMainLine1',
        short_title_patterns: 'titlePromptShortTitle',
        stage2_main_line1: 'titlePromptStage2',
        stage2_short_title: 'titlePromptStage2Short',
        json_main_line1_hint: 'titlePromptJsonHint',
        json_short_title_hint: 'titlePromptJsonShortHint',
        first_comment_patterns: 'titlePromptFirstComment',
    };

    const $ = (id) => document.getElementById(id);

    function setStatus(text, type = '') {
        const bar = $('titlePromptsStatusBar');
        if (!bar) return;
        bar.textContent = text;
        bar.className = 'status-bar' + (type ? ` ${type}` : '');
    }

    function fillForm(data) {
        Object.entries(FIELD_MAP).forEach(([key, id]) => {
            const el = $(id);
            if (el) el.value = data[key] || '';
        });
    }

    function collectPayload() {
        const payload = {};
        Object.entries(FIELD_MAP).forEach(([key, id]) => {
            payload[key] = ($(id)?.value || '').trim();
        });
        return payload;
    }

    async function loadTitlePromptSettings() {
        setStatus('加载中…');
        const resp = await fetch('/api/content-prompts');
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
        fillForm(data);
        setStatus(data.has_local_override ? '已加载（含本地覆盖）' : '已加载默认提示词', 'ok');
        return data;
    }

    async function saveTitlePromptSettings() {
        setStatus('保存中…');
        const resp = await fetch('/api/content-prompts', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(collectPayload()),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.message || '保存失败');
        fillForm(data);
        setStatus(data.message || '标题提示词已保存', 'ok');
    }

    async function resetTitlePromptSettings() {
        if (!window.confirm('恢复默认标题提示词？本地覆盖会被清除。')) return;
        setStatus('恢复中…');
        const resp = await fetch('/api/content-prompts/reset', { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.message || '恢复失败');
        fillForm(data);
        setStatus(data.message || '已恢复默认', 'ok');
    }

    window.loadTitlePromptSettings = loadTitlePromptSettings;

    $('saveTitlePromptsBtn')?.addEventListener('click', () => {
        saveTitlePromptSettings().catch((err) => setStatus(err.message || String(err), 'error'));
    });
    $('reloadTitlePromptsBtn')?.addEventListener('click', () => {
        loadTitlePromptSettings().catch((err) => setStatus(err.message || String(err), 'error'));
    });
    $('resetTitlePromptsBtn')?.addEventListener('click', () => {
        resetTitlePromptSettings().catch((err) => setStatus(err.message || String(err), 'error'));
    });
})();
