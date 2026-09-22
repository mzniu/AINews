(function () {
    let hotRadarState = { boards: [], catalogItems: [], catalogLoaded: false };

    const $ = (id) => document.getElementById(id);
    const PICKER_LIMIT = 100;

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

    function boardLabel(board) {
        const name = board.name || board.id || '';
        const display = board.display || '';
        return display ? `${name} · ${display}` : name;
    }

    function renderBoards(boards) {
        hotRadarState.boards = Array.isArray(boards) ? boards : [];
        const list = $('hotRadarBoardsList');
        if (!list) return;
        if (!hotRadarState.boards.length) {
            list.innerHTML = '<p class="hint">暂无已选热榜。点击「添加热榜」从目录挑选。</p>';
            return;
        }
        list.innerHTML = hotRadarState.boards.map((b, i) => `
            <div class="profile-card" data-board-index="${i}"
                 data-id="${escapeAttr(b.id || '')}"
                 data-hashid="${escapeAttr(b.hashid || '')}"
                 data-name="${escapeAttr(b.name || '')}"
                 data-display="${escapeAttr(b.display || '')}">
                <div class="profile-card-head">
                    <h3>${escapeHtml(boardLabel(b))}</h3>
                    <select class="form-control" data-field="enabled" style="width:auto;">
                        <option value="true" ${b.enabled ? 'selected' : ''}>启用</option>
                        <option value="false" ${!b.enabled ? 'selected' : ''}>停用</option>
                    </select>
                </div>
                ${b.domain ? `<p class="hint">${escapeHtml(b.domain)}</p>` : ''}
                <div class="footer-actions">
                    <button type="button" class="btn btn-outline btn-sm" data-action="remove">从当前行业移除</button>
                </div>
            </div>
        `).join('');
        list.querySelectorAll('[data-action="remove"]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const card = btn.closest('.profile-card');
                const index = Number(card?.dataset.boardIndex);
                if (Number.isNaN(index)) return;
                const next = collectBoards().filter((_, i) => i !== index);
                renderBoards(next);
            });
        });
    }

    function collectBoards() {
        const cards = document.querySelectorAll('#hotRadarBoardsList .profile-card');
        return Array.from(cards).map((card) => ({
            id: (card.dataset.id || '').trim(),
            hashid: (card.dataset.hashid || '').trim(),
            name: (card.dataset.name || '').trim(),
            display: (card.dataset.display || '').trim(),
            enabled: card.querySelector('[data-field="enabled"]')?.value === 'true',
        }));
    }

    function selectedHashids() {
        return new Set(collectBoards().map((b) => b.hashid).filter(Boolean));
    }

    function filterCatalog(query) {
        const q = String(query || '').trim().toLowerCase();
        if (!q) return [];
        return (hotRadarState.catalogItems || []).filter((item) => {
            const hay = `${item.name || ''} ${item.display || ''} ${item.domain || ''}`.toLowerCase();
            return hay.includes(q);
        });
    }

    function renderPickerResults(query) {
        const host = $('hotRadarPickerResults');
        if (!host) return;
        const matches = filterCatalog(query);
        if (!String(query || '').trim()) {
            host.innerHTML = '<p class="hint">输入平台或榜单名称</p>';
            return;
        }
        if (!matches.length) {
            host.innerHTML = '<p class="hint">没有匹配的热榜</p>';
            return;
        }
        const extra = matches.length > PICKER_LIMIT
            ? `<p class="hint">仅显示前 ${PICKER_LIMIT} 条，请缩小关键词（共 ${matches.length} 条）</p>`
            : '';
        const added = selectedHashids();
        const rows = matches.slice(0, PICKER_LIMIT).map((item) => {
            const already = added.has(item.hashid);
            return `<label class="hot-radar-picker-row${already ? ' is-added' : ''}">
                <input type="checkbox" value="${escapeAttr(item.hashid)}" ${already ? 'checked disabled' : ''}>
                <span>
                    <strong>${escapeHtml(item.name || item.hashid)}</strong>
                    ${item.display ? ` · ${escapeHtml(item.display)}` : ''}
                    ${already ? ' <span class="badge">已添加</span>' : ''}
                    <p class="hot-radar-picker-meta">${escapeHtml(item.domain || '')}</p>
                </span>
            </label>`;
        }).join('');
        host.innerHTML = extra + `<div class="hot-radar-picker-list">${rows}</div>`;
    }

    async function loadCatalog(refresh = false) {
        const hint = $('hotRadarPickerHint');
        if (hint) hint.textContent = refresh ? '正在刷新 TopHub 目录…' : '正在从 TopHub 拉取目录…';
        const path = refresh
            ? '/api/ingestion/hot-radar/nodes?refresh=true'
            : '/api/ingestion/hot-radar/nodes';
        const data = await api(path);
        hotRadarState.catalogItems = data.items || [];
        hotRadarState.catalogLoaded = true;
        if (hint) {
            hint.textContent = data.stale
                ? `已使用缓存目录（可能过期）· ${data.count || hotRadarState.catalogItems.length} 条`
                : `目录 ${data.count || hotRadarState.catalogItems.length} 条`;
        }
    }

    function closePicker() {
        $('hotRadarPickerOverlay')?.classList.remove('is-open');
    }

    function confirmPicker() {
        const boxes = document.querySelectorAll('#hotRadarPickerResults input[type="checkbox"]:checked:not(:disabled)');
        const byHash = new Map((hotRadarState.catalogItems || []).map((item) => [item.hashid, item]));
        const current = collectBoards();
        const seen = new Set(current.map((b) => b.hashid));
        boxes.forEach((box) => {
            const hashid = box.value;
            if (!hashid || seen.has(hashid)) return;
            const item = byHash.get(hashid) || { hashid };
            current.push({
                id: hashid,
                hashid,
                name: item.name || hashid,
                display: item.display || '',
                domain: item.domain || '',
                enabled: true,
            });
            seen.add(hashid);
        });
        renderBoards(current);
        closePicker();
    }

    async function openPicker() {
        let overlay = $('hotRadarPickerOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'hotRadarPickerOverlay';
            overlay.className = 'app-modal-overlay';
            overlay.innerHTML = `
                <div class="app-modal app-modal--wide" role="dialog" aria-modal="true" aria-labelledby="hotRadarPickerTitle">
                    <h3 id="hotRadarPickerTitle">添加热榜</h3>
                    <div class="hot-radar-picker-toolbar">
                        <input id="hotRadarPickerSearch" class="form-control" type="search" placeholder="搜索平台 / 榜单 / 域名" autocomplete="off">
                        <button type="button" class="btn btn-outline btn-sm" id="hotRadarPickerRefreshBtn">刷新目录</button>
                    </div>
                    <p class="hint" id="hotRadarPickerHint"></p>
                    <div id="hotRadarPickerResults"></div>
                    <div class="app-modal-actions">
                        <button type="button" class="btn btn-outline" data-action="close">取消</button>
                        <button type="button" class="btn" id="hotRadarPickerConfirmBtn">加入</button>
                    </div>
                </div>`;
            document.body.appendChild(overlay);
            overlay.addEventListener('click', (event) => {
                if (event.target === overlay || event.target.closest('[data-action="close"]')) {
                    closePicker();
                }
            });
            $('hotRadarPickerSearch')?.addEventListener('input', (event) => {
                renderPickerResults(event.target.value);
            });
            $('hotRadarPickerRefreshBtn')?.addEventListener('click', async () => {
                try {
                    await loadCatalog(true);
                    renderPickerResults($('hotRadarPickerSearch')?.value || '');
                } catch (e) {
                    const hint = $('hotRadarPickerHint');
                    if (hint) hint.textContent = e.message || '刷新失败';
                }
            });
            $('hotRadarPickerConfirmBtn')?.addEventListener('click', confirmPicker);
        }
        overlay.classList.add('is-open');
        const search = $('hotRadarPickerSearch');
        if (search) search.value = '';
        renderPickerResults('');
        try {
            if (!hotRadarState.catalogLoaded) await loadCatalog(false);
            else {
                const hint = $('hotRadarPickerHint');
                if (hint) hint.textContent = `目录 ${hotRadarState.catalogItems.length} 条`;
            }
        } catch (e) {
            hotRadarState.catalogLoaded = false;
            const hint = $('hotRadarPickerHint');
            if (hint) hint.textContent = e.message || '无法加载目录。请先填写 TopHub API Key。';
        }
    }

    async function loadHotRadarSettings() {
        setStatus('加载中…');
        try {
            const data = await api('/api/ingestion/hot-radar/settings');
            hotRadarState = { ...hotRadarState, ...data };
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
            renderBoards(data.boards || collectBoards());
            setStatus(data.message || '热榜雷达配置已保存', 'ok');
        } catch (e) {
            setStatus('保存失败: ' + e.message, 'error');
        }
    }

    window.loadHotRadarSettings = loadHotRadarSettings;

    document.addEventListener('DOMContentLoaded', () => {
        $('reloadHotRadarBtn')?.addEventListener('click', loadHotRadarSettings);
        $('saveHotRadarBtn')?.addEventListener('click', saveHotRadarSettings);
        $('addHotRadarBoardBtn')?.addEventListener('click', openPicker);
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') closePicker();
        });
    });
})();
