(function () {
    let ingestionState = { defaults: {}, worker: {}, sources: [] };

    const $ = (id) => document.getElementById(id);

    function setStatus(text, type = '') {
        const bar = $('ingestionStatusBar');
        if (!bar) return;
        bar.textContent = text;
        bar.className = 'status-bar' + (type ? ` ${type}` : '');
    }

    async function api(path, options = {}) {
        const resp = await fetch(path, {
            headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
            ...options,
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
        return data;
    }

    function renderWorkerStatus(data) {
        const el = $('ingestionWorkerStatus');
        if (!el) return;
        const mode = data.worker_mode || 'embedded';
        const ok = data.worker_reachable;
        el.innerHTML = ok
            ? `✅ 爬取 Worker 运行中（模式: <code>${mode}</code>）`
            : `⚠️ 爬取 Worker 未就绪（模式: <code>${mode}</code>）。请重启 web_server，或设置 <code>INGESTION_WORKER_MODE=separate</code> 后运行 <code>python -m services.ingestion.worker</code>`;
        el.className = ok ? 'status-bar ok' : 'status-bar error';
    }

    async function loadWorkerHealth() {
        try {
            const data = await api('/api/ingestion/health');
            renderWorkerStatus(data);
        } catch (e) {
            const el = $('ingestionWorkerStatus');
            if (el) el.textContent = '无法检测 Worker 状态: ' + e.message;
        }
    }

    function renderDefaults(defaults) {
        $('defaultScheduleCron').value = defaults.schedule_cron || '0 * * * *';
        $('requestDelaySec').value = defaults.request_delay_sec ?? 2;
        $('maxListPages').value = defaults.max_list_pages ?? 2;
        $('maxNewPerRun').value = defaults.max_new_articles_per_run ?? 30;
        $('stopAfterExisting').value = defaults.stop_after_existing ?? 5;
        $('maxImagesPerArticle').value = defaults.max_images_per_article ?? 20;
        $('downloadImages').value = String(defaults.download_images !== false);
    }

    function renderSources(sources) {
        const list = $('ingestionSourcesList');
        if (!sources.length) {
            list.innerHTML = '<p class="hint">暂无数据源</p>';
            return;
        }
        list.innerHTML = sources.map((s, i) => `
            <div class="profile-card" data-source-index="${i}">
                <div class="profile-card-head">
                    <h3>${escapeHtml(s.display_name)} <span class="badge">${escapeHtml(s.id)}</span></h3>
                    <select class="form-control" data-field="enabled" style="width:auto;">
                        <option value="true" ${s.enabled ? 'selected' : ''}>启用</option>
                        <option value="false" ${!s.enabled ? 'selected' : ''}>停用</option>
                    </select>
                </div>
                <div class="form-grid">
                    <div>
                        <label class="field-label">定时 Cron</label>
                        <input class="form-control" data-field="schedule_cron" value="${escapeAttr(s.schedule_cron || '')}">
                    </div>
                    <div>
                        <label class="field-label">列表翻页数</label>
                        <input class="form-control" data-field="max_list_pages" type="number" min="1" value="${Number(s.max_list_pages) || 1}">
                    </div>
                    <div>
                        <label class="field-label">单次新文章上限</label>
                        <input class="form-control" data-field="max_new_articles_per_run" type="number" min="1" value="${Number(s.max_new_articles_per_run) || 30}">
                    </div>
                    <div>
                        <label class="field-label">请求间隔（秒）</label>
                        <input class="form-control" data-field="request_delay_sec" type="number" min="0" step="0.5" value="${Number(s.request_delay_sec) || 2}">
                    </div>
                    <div>
                        <label class="field-label">连续已存在停止阈值</label>
                        <input class="form-control" data-field="stop_after_existing" type="number" min="1" value="${Number(s.stop_after_existing) || 5}">
                    </div>
                    <div>
                        <label class="field-label">每篇最多图片</label>
                        <input class="form-control" data-field="max_images_per_article" type="number" min="0" value="${Number(s.max_images_per_article) || 20}">
                    </div>
                </div>
                <p class="hint">${escapeHtml(s.list_url || s.base_url || '')}</p>
            </div>
        `).join('');
    }

    function collectPayload() {
        const defaults = {
            schedule_cron: $('defaultScheduleCron').value.trim(),
            request_delay_sec: Number($('requestDelaySec').value),
            max_list_pages: Number($('maxListPages').value),
            max_new_articles_per_run: Number($('maxNewPerRun').value),
            stop_after_existing: Number($('stopAfterExisting').value),
            max_images_per_article: Number($('maxImagesPerArticle').value),
            download_images: $('downloadImages').value === 'true',
        };
        const worker = {
            poll_interval_sec: Number($('pollIntervalSec').value) || 5,
        };
        const sources = [];
        document.querySelectorAll('#ingestionSourcesList .profile-card').forEach((card, i) => {
            const base = ingestionState.sources[i] || {};
            const read = (field) => card.querySelector(`[data-field="${field}"]`)?.value;
            sources.push({
                id: base.id,
                display_name: base.display_name,
                enabled: read('enabled') === 'true',
                schedule_cron: read('schedule_cron'),
                max_list_pages: Number(read('max_list_pages')),
                max_new_articles_per_run: Number(read('max_new_articles_per_run')),
                request_delay_sec: Number(read('request_delay_sec')),
                stop_after_existing: Number(read('stop_after_existing')),
                max_images_per_article: Number(read('max_images_per_article')),
                download_images: defaults.download_images,
            });
        });
        return { version: 1, defaults, worker, sources };
    }

    function applyConfig(data) {
        ingestionState = data;
        $('pollIntervalSec').value = (data.worker || {}).poll_interval_sec ?? 5;
        renderDefaults(data.defaults || {});
        renderSources(data.sources || []);
    }

    async function loadIngestionSettings() {
        setStatus('加载中…');
        await loadWorkerHealth();
        const data = await api('/api/ingestion/settings');
        applyConfig(data);
        setStatus(data.has_local_file ? '已加载爬取配置' : '使用默认模板（尚未保存本地覆盖）', 'ok');
    }

    async function saveIngestionSettings() {
        setStatus('保存中…');
        const payload = collectPayload();
        const data = await api('/api/ingestion/settings', {
            method: 'PUT',
            body: JSON.stringify(payload),
        });
        applyConfig(data);
        await loadWorkerHealth();
        setStatus(data.message || '爬取配置已保存', 'ok');
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        })[c]);
    }

    function escapeAttr(s) {
        return escapeHtml(s).replace(/"/g, '&quot;');
    }

    window.loadIngestionSettings = loadIngestionSettings;

    $('saveIngestionBtn')?.addEventListener('click', () => saveIngestionSettings().catch((e) => setStatus(e.message, 'error')));
    $('reloadIngestionBtn')?.addEventListener('click', () => loadIngestionSettings().catch((e) => setStatus(e.message, 'error')));
})();
