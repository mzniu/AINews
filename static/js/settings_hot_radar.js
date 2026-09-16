(function () {
    let hotRadarState = { boards: [] };

    const $ = (id) => document.getElementById(id);

    function escapeHtml(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function escapeAttr(text) {
        return escapeHtml(text).replace(/'/g, '&#39;');
    }

    function setStatus(text, type = '') {
        const bar = $('hotRadarStatusBar');
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

    function renderBoards(boards) {
        const list = $('hotRadarBoardsList');
        if (!list) return;
        if (!boards.length) {
            list.innerHTML = '<p class="hint">暂无热榜节点</p>';
            return;
        }
        list.innerHTML = boards.map((b, i) => `
            <div class="profile-card" data-board-index="${i}">
                <div class="profile-card-head">
                    <h3>${escapeHtml(b.name || b.id)} <span class="badge">${escapeHtml(b.display || b.hashid)}</span></h3>
                    <select class="form-control" data-field="enabled" style="width:auto;">
                        <option value="true" ${b.enabled ? 'selected' : ''}>启用</option>
                        <option value="false" ${!b.enabled ? 'selected' : ''}>停用</option>
                    </select>
                </div>
                <div class="form-grid">
                    <div>
                        <label class="field-label">节点 ID</label>
                        <input class="form-control" data-field="id" value="${escapeAttr(b.id || '')}">
                    </div>
                    <div>
                        <label class="field-label">TopHub hashid</label>
                        <input class="form-control" data-field="hashid" value="${escapeAttr(b.hashid || '')}">
                    </div>
                    <div>
                        <label class="field-label">平台名称</label>
                        <input class="form-control" data-field="name" value="${escapeAttr(b.name || '')}">
                    </div>
                    <div>
                        <label class="field-label">榜单名称</label>
                        <input class="form-control" data-field="display" value="${escapeAttr(b.display || '')}">
                    </div>
                </div>
            </div>
        `).join('');
    }

    function collectBoards() {
        const cards = document.querySelectorAll('#hotRadarBoardsList .profile-card');
        return Array.from(cards).map((card) => {
            const get = (field) => card.querySelector(`[data-field="${field}"]`)?.value;
            return {
                id: get('id')?.trim(),
                hashid: get('hashid')?.trim(),
                name: get('name')?.trim(),
                display: get('display')?.trim(),
                enabled: get('enabled') === 'true',
            };
        });
    }

    function addBoardRow() {
        hotRadarState.boards.push({
            id: `board_${Date.now()}`,
            hashid: '',
            name: '',
            display: '',
            enabled: true,
        });
        renderBoards(hotRadarState.boards);
    }

    async function loadHotRadarSettings() {
        setStatus('加载中…');
        try {
            const data = await api('/api/ingestion/hot-radar/settings');
            hotRadarState = data;
            $('hotRadarEnabled').value = String(data.enabled !== false);
            $('hotRadarApiBase').value = data.api_base_url || 'https://api.tophubdata.com';
            $('hotRadarRefreshCron').value = data.refresh_cron || '0 8 * * *';
            $('hotRadarMaxAge').value = data.max_age_minutes ?? 1440;
            $('hotRadarMatchThreshold').value = data.title_match_threshold ?? 0.72;
            $('hotRadarAccessKey').value = '';
            $('hotRadarAccessKeyHint').textContent = data.access_key_masked
                ? `已保存 ${data.access_key_masked}，留空则保留`
                : '未配置，请填写 TopHub API Key';
            const discovery = data.discovery || {};
            $('hotRadarDiscoveryEnabled').value = String(discovery.enabled !== false);
            $('hotRadarDiscoveryMaxRank').value = discovery.max_rank ?? 10;
            $('hotRadarDiscoveryMaxUrls').value = discovery.max_urls_per_refresh ?? 5;
            const batch = data.batch || {};
            $('hotRadarRescoreOnRefresh').value = String(batch.rescore_on_refresh !== false);
            renderBoards(data.boards || []);
            setStatus('已加载热榜雷达配置', 'ok');
        } catch (e) {
            setStatus('加载失败: ' + e.message, 'error');
        }
    }

    async function saveHotRadarSettings() {
        setStatus('保存中…');
        try {
            const payload = {
                enabled: $('hotRadarEnabled').value === 'true',
                api_base_url: $('hotRadarApiBase').value.trim(),
                refresh_cron: $('hotRadarRefreshCron').value.trim(),
                max_age_minutes: Number($('hotRadarMaxAge').value),
                title_match_threshold: Number($('hotRadarMatchThreshold').value),
                boards: collectBoards(),
                discovery: {
                    enabled: $('hotRadarDiscoveryEnabled').value === 'true',
                    max_rank: Number($('hotRadarDiscoveryMaxRank').value),
                    max_urls_per_refresh: Number($('hotRadarDiscoveryMaxUrls').value),
                },
                batch: {
                    rescore_on_refresh: $('hotRadarRescoreOnRefresh').value === 'true',
                },
            };
            const key = $('hotRadarAccessKey').value.trim();
            if (key) payload.access_key = key;
            const data = await api('/api/ingestion/hot-radar/settings', {
                method: 'PUT',
                body: JSON.stringify(payload),
            });
            $('hotRadarAccessKey').value = '';
            $('hotRadarAccessKeyHint').textContent = data.access_key_masked
                ? `已保存 ${data.access_key_masked}，留空则保留`
                : '未配置';
            setStatus(data.message || '热榜雷达配置已保存', 'ok');
        } catch (e) {
            setStatus('保存失败: ' + e.message, 'error');
        }
    }

    window.loadHotRadarSettings = loadHotRadarSettings;

    document.addEventListener('DOMContentLoaded', () => {
        $('reloadHotRadarBtn')?.addEventListener('click', loadHotRadarSettings);
        $('saveHotRadarBtn')?.addEventListener('click', saveHotRadarSettings);
        $('addHotRadarBoardBtn')?.addEventListener('click', addBoardRow);
    });
})();
