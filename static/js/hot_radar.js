(function () {
    const $ = (id) => document.getElementById(id);
    let snapshotData = null;
    let discoveryPollTimer = null;

    const DISCOVERY_STATUS_LABELS = {
        pending: '等待中',
        running: '抓取中',
        succeeded: '已入库',
        failed: '失败',
        skipped: '已存在',
        new: '已入库',
    };

    function escapeHtml(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function setStatus(message, kind) {
        const bar = $('statusBar');
        if (!bar) return;
        bar.textContent = message || '';
        bar.className = 'status-bar' + (kind ? ` ${kind}` : '');
    }

    async function api(path, options) {
        const resp = await fetch(path, options);
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
        }
        return data;
    }

    function formatTime(value) {
        if (!value) return '—';
        if (window.DateTimeUtil && typeof window.DateTimeUtil.formatBeijing === 'function') {
            return window.DateTimeUtil.formatBeijing(value);
        }
        return value;
    }

    function boardLabel(board) {
        const name = board?.name || '';
        const display = board?.display || '';
        if (name && display) return `${name}·${display}`;
        return name || display || board?.board_id || board?.hashid || '热榜';
    }

    function populateBoardFilter(boards) {
        const select = $('boardFilter');
        if (!select) return;
        const current = select.value;
        select.innerHTML = '<option value="">全部榜单</option>' +
            (boards || []).map((board) => {
                const value = board.hashid || board.board_id || '';
                return `<option value="${escapeHtml(value)}">${escapeHtml(boardLabel(board))}</option>`;
            }).join('');
        if (current && Array.from(select.options).some((opt) => opt.value === current)) {
            select.value = current;
        }
    }

    function renderItemRows(items) {
        const body = $('hotListBody');
        const filter = $('boardFilter')?.value || '';
        const filtered = filter
            ? (items || []).filter((item) => (item.board_hashid || item.board_id) === filter)
            : (items || []);

        if (!filtered.length) {
            body.innerHTML = '<tr><td colspan="5" class="empty-cell">暂无热榜数据，请点击「刷新热榜」或在设置页配置 TopHub</td></tr>';
            return;
        }

        body.innerHTML = filtered.map((item) => {
            const rankCls = item.rank <= 3 ? 'rank-top' : '';
            const link = item.url
                ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">打开</a>`
                : '—';
            return `<tr>
                <td class="small">${escapeHtml(item.board_label || '—')}</td>
                <td class="${rankCls}">${item.rank}</td>
                <td class="hot-title">${escapeHtml(item.title)}</td>
                <td class="hot-heat">${escapeHtml(item.heat_label || '—')}</td>
                <td>${link}</td>
            </tr>`;
        }).join('');
    }

    function renderSnapshot(data) {
        snapshotData = data;
        $('snapshotStatus').textContent = data.status || '—';
        $('snapshotTime').textContent = formatTime(data.fetched_at);
        $('snapshotCount').textContent = String(data.item_count ?? 0);
        const boardCount = data.config?.board_count ?? (data.boards || []).length;
        $('snapshotBoard').textContent = `TopHub · ${boardCount} 个榜单`;
        $('listHint').textContent = data.config?.has_access_key ? '数据源：TopHub 榜眼数据' : '未配置 API Key，请前往系统配置';

        populateBoardFilter(data.boards || []);

        const err = $('snapshotError');
        if (data.error_message) {
            err.style.display = '';
            err.textContent = data.error_message;
        } else {
            err.style.display = 'none';
            err.textContent = '';
        }

        renderItemRows(data.items || []);
    }

    function discoveryStatusLabel(item) {
        const status = typeof item === 'string' ? item : (item?.outcome || item?.status);
        return DISCOVERY_STATUS_LABELS[status] || status || '—';
    }

    function renderDiscoverySummary(summary) {
        const el = $('discoverySummary');
        if (!el) return;
        const s = summary || {};
        const parts = [
            ['pending', '等待'],
            ['running', '进行中'],
            ['succeeded', '已入库'],
            ['failed', '失败'],
        ];
        el.innerHTML = parts
            .map(([key, label]) => `<span class="discovery-pill">${label} ${s[key] || 0}</span>`)
            .join('');
    }

    function renderDiscoveryQueue(data) {
        const body = $('discoveryQueueBody');
        if (!body) return;
        renderDiscoverySummary(data.summary);
        const items = data.items || [];
        if (!items.length) {
            body.innerHTML = '<tr><td colspan="7" class="empty-cell">近 72 小时暂无热榜发现任务。刷新热榜后，符合条件的新链接会出现在这里。</td></tr>';
            scheduleDiscoveryPoll(false);
            return;
        }

        body.innerHTML = items.map((item) => {
            const status = item.status || 'pending';
            const statusKey = item.outcome || status;
            const statusCls = `discovery-status discovery-status-${statusKey}`;
            const rankCls = item.rank && item.rank <= 3 ? 'rank-top' : '';
            const actions = [];
            if (item.url) {
                actions.push(`<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">原文</a>`);
            }
            if (item.article_id) {
                actions.push(
                    `<a href="/ingestion-library?article_id=${encodeURIComponent(item.article_id)}">资讯库</a>`
                );
            }
            const error = item.error_message
                ? `<span class="discovery-error">${escapeHtml(item.error_message)}</span>`
                : '';
            return `<tr>
                <td><span class="${statusCls}">${escapeHtml(discoveryStatusLabel(item))}</span>${error}</td>
                <td class="small">${escapeHtml(item.board_label || '—')}</td>
                <td class="${rankCls}">${item.rank != null ? item.rank : '—'}</td>
                <td class="discovery-title">${escapeHtml(item.title || '—')}</td>
                <td class="small">${escapeHtml(item.source_id || '—')}</td>
                <td class="small">${escapeHtml(formatTime(item.created_at))}</td>
                <td class="small">${actions.join(' · ') || '—'}</td>
            </tr>`;
        }).join('');

        const active = (data.summary?.pending || 0) + (data.summary?.running || 0);
        scheduleDiscoveryPoll(active > 0);
    }

    function scheduleDiscoveryPoll(shouldPoll) {
        if (discoveryPollTimer) {
            clearInterval(discoveryPollTimer);
            discoveryPollTimer = null;
        }
        if (!shouldPoll) return;
        discoveryPollTimer = setInterval(() => {
            loadDiscoveryQueue().catch(() => {});
        }, 8000);
    }

    async function loadDiscoveryQueue() {
        const data = await api('/api/ingestion/hot-radar/discovery-queue');
        renderDiscoveryQueue(data);
        return data;
    }

    function renderMatch(data) {
        const panel = $('matchPanel');
        const match = data.match;
        const stored = data.stored_match;
        const dim = data.hot_radar_dimension;
        const hitCls = data.matched ? 'match-hit' : 'match-miss';
        const hitLabel = data.matched ? '已命中当前热榜' : '未命中当前热榜';

        let matchBlock = '';
        if (match) {
            const boardText = match.board_label || boardLabel(match);
            matchBlock = `
                <div class="match-block">
                    <h3>实时匹配</h3>
                    <p class="match-meta">${escapeHtml(boardText)} · 排名 #${match.rank} · 热度 ${escapeHtml(match.heat_label || '—')} · ${escapeHtml(match.match_method === 'url' ? 'URL 命中' : '标题命中')}</p>
                    <p class="small">${escapeHtml(match.hot_title)}</p>
                    ${match.hot_url ? `<p class="small"><a href="${escapeHtml(match.hot_url)}" target="_blank" rel="noopener">热榜原文</a></p>` : ''}
                </div>`;
        }

        let storedBlock = '';
        if (stored) {
            storedBlock = `
                <div class="match-block">
                    <h3>评分时记录</h3>
                    <p class="match-meta">排名 #${stored.rank} · 热度 ${escapeHtml(stored.heat_label || '—')} · ${escapeHtml(stored.match_method || '')}</p>
                    <p class="small">${escapeHtml(stored.hot_title || '')}</p>
                </div>`;
        }

        let dimBlock = '';
        if (dim) {
            dimBlock = `
                <div class="match-block">
                    <h3>规则评分 · 热榜雷达维度</h3>
                    <p class="match-meta">${escapeHtml(dim.label || '热榜雷达')} ${dim.score}/10 · 加权 ${dim.weighted}</p>
                    <p class="small">${escapeHtml((dim.signals || []).join('、'))}</p>
                </div>`;
        }

        panel.innerHTML = `
            <div class="${hitCls}">
                <p class="match-title">${escapeHtml(data.article_title || '—')}</p>
                <p class="match-meta">${hitLabel}</p>
                <p class="match-meta">文章 ID：${escapeHtml(data.article_id)}</p>
                <p class="match-meta">评分：${escapeHtml(data.score_grade || '—')} ${data.score_total != null ? Math.round(data.score_total) + ' 分' : ''}</p>
                <p class="match-meta"><a href="${escapeHtml(data.article_url || '#')}" target="_blank" rel="noopener">原文链接</a></p>
                ${matchBlock}
                ${storedBlock}
                ${dimBlock}
            </div>`;
    }

    async function loadSnapshot(refresh) {
        setStatus(refresh ? '正在刷新热榜…' : '加载热榜快照…');
        const query = refresh ? '?refresh=true' : '';
        const data = await api(`/api/ingestion/hot-radar${query}`);
        renderSnapshot(data);
        setStatus(refresh ? '热榜已刷新' : '热榜快照已加载', 'ok');
    }

    async function lookupArticle() {
        const articleId = ($('articleIdInput')?.value || '').trim();
        if (!articleId) {
            setStatus('请输入文章 ID', 'error');
            return;
        }
        setStatus('查询命中详情…');
        const data = await api(`/api/ingestion/hot-radar/articles/${encodeURIComponent(articleId)}`);
        renderMatch(data);
        setStatus(data.matched ? '该文章已命中热榜' : '该文章未命中热榜', data.matched ? 'ok' : '');
    }

    async function refreshSnapshot() {
        setStatus('正在拉取 TopHub 热榜…');
        const result = await api('/api/ingestion/hot-radar/refresh', { method: 'POST' });
        await loadSnapshot(false);
        const discovery = result.pipeline?.discovery;
        await loadDiscoveryQueue();
        if (discovery && typeof discovery.enqueued === 'number') {
            setStatus(
                `热榜已刷新 · 自动发现入队 ${discovery.enqueued} 条（跳过 ${discovery.skipped || 0}）`,
                discovery.enqueued ? 'ok' : '',
            );
            return;
        }
        setStatus('热榜已刷新', 'ok');
    }

    function initFromQuery() {
        const params = new URLSearchParams(window.location.search);
        const articleId = params.get('article_id');
        if (articleId && $('articleIdInput')) {
            $('articleIdInput').value = articleId;
            lookupArticle().catch((e) => setStatus(e.message, 'error'));
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        $('refreshSnapshotBtn')?.addEventListener('click', () => {
            refreshSnapshot().catch((e) => setStatus(e.message, 'error'));
        });
        $('lookupBtn')?.addEventListener('click', () => {
            lookupArticle().catch((e) => setStatus(e.message, 'error'));
        });
        $('boardFilter')?.addEventListener('change', () => {
            if (snapshotData) renderItemRows(snapshotData.items || []);
        });
        $('articleIdInput')?.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                lookupArticle().catch((e) => setStatus(e.message, 'error'));
            }
        });

        loadSnapshot(false)
            .then(() => loadDiscoveryQueue())
            .then(initFromQuery)
            .catch((e) => setStatus(e.message, 'error'));
    });
})();
