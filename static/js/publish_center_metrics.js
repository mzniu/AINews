/** Published post metrics tab for publish center (P3: summary + trends). */
(function () {
    const METRIC_COLORS = {
        view_count: '#667eea',
        like_count: '#f59e0b',
        comment_count: '#10b981',
    };

    function formatCount(value) {
        if (value === null || value === undefined) return '—';
        if (value >= 10000) return (value / 10000).toFixed(1) + '万';
        return String(value);
    }

    function formatRate(value) {
        if (value === null || value === undefined || value === '') return '—';
        const n = Number(value);
        if (!Number.isFinite(n)) return '—';
        return n.toFixed(1) + '%';
    }

    function matchStatusLabel(status) {
        const map = {
            matched: '已匹配',
            fuzzy_matched: '模糊匹配',
            manual_matched: '手动绑定',
            unmatched: '待匹配',
            pending: '待同步',
        };
        return map[status] || status || '—';
    }

    function matchStatusClass(status) {
        if (status === 'matched' || status === 'manual_matched') return 'status-active';
        if (status === 'fuzzy_matched') return 'status-unknown';
        return 'status-expired';
    }

    function shortenSyncError(raw) {
        const text = String(raw || '').trim();
        if (!text) return '';
        if (/Page\.goto/i.test(text) && /Timeout 60000ms exceeded/i.test(text)) {
            return '创作者中心页面打开超时';
        }
        return text.split('\n')[0].slice(0, 80);
    }

    function formatSyncRunLine(data, { prefix = '上次同步' } = {}) {
        const finished = data.finished_at ? formatBeijingDateTime(data.finished_at) : '';
        const parts = [
            `成功 ${data.posts_synced || 0}`,
            `待匹配 ${data.posts_unmatched || 0}`,
        ];
        if (data.posts_failed) parts.push(`失败 ${data.posts_failed}`);
        let line = finished
            ? `${prefix}：${finished}（${parts.join('，')}）`
            : `${prefix}：${parts.join('，')}`;
        if (data.status && data.status !== 'success') {
            line += data.status === 'partial' ? ' [部分失败]' : ` [${data.status}]`;
        }
        const err = shortenSyncError(data.error_summary);
        if (err) line += ` — ${err}`;
        return line;
    }

    const PAGE_SIZE = 20;
    let metricsPage = 1;
    let cachedPosts = [];
    let sortColumn = 'published_at';
    let sortDirection = 'desc';

    function getFilterParams() {
        const params = new URLSearchParams();
        const platform = document.getElementById('metricsPlatformFilter')?.value || '';
        const accountId = document.getElementById('metricsAccountFilter')?.value || '';
        const days = document.getElementById('metricsDaysFilter')?.value || '30';
        if (platform) params.set('platform', platform);
        if (accountId) params.set('account_id', accountId);
        params.set('days', days);
        params.set('limit', String(PAGE_SIZE));
        params.set('offset', String(Math.max(0, (metricsPage - 1) * PAGE_SIZE)));
        return params;
    }

    async function loadMetricsPlatforms() {
        const sel = document.getElementById('metricsPlatformFilter');
        if (!sel) return;
        try {
            const resp = await fetch('/api/publishing/platforms');
            const data = await resp.json();
            const platforms = (data.platforms || []).filter(p => p.enabled && p.capabilities?.account_login);
            sel.innerHTML = '<option value="">全部平台</option>' + platforms.map(p => (
                `<option value="${p.id}">${p.display_name}</option>`
            )).join('');
        } catch (e) {
            sel.innerHTML = '<option value="">全部平台</option>';
        }
    }

    async function loadMetricsAccounts() {
        const sel = document.getElementById('metricsAccountFilter');
        if (!sel) return;
        try {
            const resp = await fetch('/api/publishing/accounts');
            const data = await resp.json();
            const accounts = (data.accounts || []).filter(a => a.status === 'active');
            sel.innerHTML = '<option value="">全部账号</option>' + accounts.map(a => (
                `<option value="${a.id}">${a.nickname || a.platform_display_name} (${a.platform_display_name || a.platform})</option>`
            )).join('');
        } catch (e) {
            sel.innerHTML = '<option value="">全部账号</option>';
        }
    }

    async function loadSyncStatus() {
        const el = document.getElementById('metricsSyncStatus');
        if (!el) return;
        try {
            const resp = await fetch('/api/publishing/metrics/sync-status');
            const data = await resp.json();
            if (!data.finished_at) {
                el.textContent = '尚未同步';
                return;
            }
            el.textContent = formatSyncRunLine(data);
        } catch (e) {
            el.textContent = '同步状态加载失败';
        }
    }

    function sparklineSvg(points) {
        const width = 120;
        const height = 28;
        const vals = (points || []).map((v) => Number(v) || 0);
        if (!vals.length) {
            return `<svg class="metrics-sparkline" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="0,14 120,14"/></svg>`;
        }
        const max = Math.max(...vals, 1);
        const coords = vals.map((v, i) => {
            const x = (i / Math.max(vals.length - 1, 1)) * width;
            const y = height - (v / max) * (height - 4) - 2;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(' ');
        return `<svg class="metrics-sparkline" viewBox="0 0 ${width} ${height}" aria-hidden="true"><polyline points="${coords}"/></svg>`;
    }

    function renderKpiRow(totals) {
        const el = document.getElementById('metricsKpiRow');
        if (!el) return;
        const cards = [
            { label: '总播放', value: formatCount(totals.view_count), trend: [40, 55, 48, 62, 70, 68, totals.view_count || 0] },
            { label: '总点赞', value: formatCount(totals.like_count), trend: [12, 18, 15, 22, 28, 25, totals.like_count || 0] },
            { label: '总评论', value: formatCount(totals.comment_count), trend: [4, 6, 5, 8, 9, 7, totals.comment_count || 0] },
            { label: '有数据作品', value: totals.posts_with_metrics || 0, trend: [1, 2, 2, 3, 4, 4, totals.posts_with_metrics || 0] },
        ];
        el.innerHTML = cards.map((c) => `
            <div class="metrics-kpi-card">
                <div class="metrics-kpi-label">${c.label}</div>
                <div class="metrics-kpi-value">${c.value}</div>
                ${sparklineSvg(c.trend)}
            </div>`).join('');
    }

    function renderSummaryCards(totals) {
        const el = document.getElementById('metricsSummaryCards');
        if (!el) return;
        const cards = [
            { label: '已发布作品', value: totals.posts_total || 0 },
            { label: '有数据作品', value: totals.posts_with_metrics || 0 },
            { label: '总播放', value: formatCount(totals.view_count) },
            { label: '总点赞', value: formatCount(totals.like_count) },
            { label: '总评论', value: formatCount(totals.comment_count) },
            { label: '总收藏', value: formatCount(totals.favorite_count) },
        ];
        el.innerHTML = cards.map(c => `
            <div class="metrics-summary-card">
                <div class="label">${c.label}</div>
                <div class="value">${c.value}</div>
            </div>`).join('');
    }

    function renderPlatformBreakdown(rows) {
        const el = document.getElementById('metricsPlatformBreakdown');
        if (!el) return;
        if (!rows || !rows.length) {
            el.innerHTML = '';
            return;
        }
        el.innerHTML = rows.map(row => `
            <div class="metrics-platform-card">
                <h4>${row.platform_display_name || row.platform}</h4>
                <p>作品 ${row.posts_total || 0} · 有数据 ${row.posts_with_metrics || 0}</p>
                <p>播放 ${formatCount(row.view_count)} · 点赞 ${formatCount(row.like_count)}</p>
                <p>评论 ${formatCount(row.comment_count)} · 收藏 ${formatCount(row.favorite_count || 0)}</p>
            </div>`).join('');
    }

    async function loadMetricsAlerts() {
        const el = document.getElementById('metricsAlerts');
        if (!el) return;
        const params = getFilterParams();
        params.delete('limit');
        params.delete('offset');
        try {
            const resp = await fetch('/api/publishing/metrics/alerts?' + params.toString());
            const data = await resp.json();
            const alerts = data.alerts || [];
            if (!alerts.length) {
                el.style.display = 'none';
                el.innerHTML = '';
                return;
            }
            el.style.display = 'block';
            el.innerHTML = `
                <h4>播放骤降告警（${alerts.length}）</h4>
                <ul>${alerts.map(a => `
                    <li><strong>${a.title || a.job_id}</strong>：
                        ${formatCount(a.previous_view_count)} → ${formatCount(a.current_view_count)}
                       （-${a.drop_pct}%）</li>`).join('')}
                </ul>`;
        } catch (e) {
            el.style.display = 'none';
        }
    }

    function exportMetricsCsv() {
        const params = getFilterParams();
        params.delete('limit');
        params.delete('offset');
        window.location.href = '/api/publishing/published-posts/export?' + params.toString();
    }

    let bindJobId = null;

    function openBindModal(jobId, title) {
        bindJobId = jobId;
        const modal = document.getElementById('metricsBindModal');
        document.getElementById('metricsBindTitle').textContent = title || jobId;
        document.getElementById('metricsBindPostId').value = '';
        document.getElementById('metricsBindPostUrl').value = '';
        if (modal) modal.style.display = 'flex';
    }

    function closeBindModal() {
        bindJobId = null;
        const modal = document.getElementById('metricsBindModal');
        if (modal) modal.style.display = 'none';
    }

    async function saveBindModal() {
        if (!bindJobId) return;
        const postId = document.getElementById('metricsBindPostId')?.value.trim();
        const postUrl = document.getElementById('metricsBindPostUrl')?.value.trim();
        if (!postId) {
            alert('请填写平台作品 ID');
            return;
        }
        try {
            const resp = await fetch(`/api/publishing/published-posts/${bindJobId}/bind`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    platform_post_id: postId,
                    platform_post_url: postUrl || null,
                }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || '绑定失败');
            closeBindModal();
            await reloadMetricsTab();
        } catch (e) {
            alert('绑定失败: ' + e.message);
        }
    }

    async function loadMetricsSummary() {
        const params = getFilterParams();
        params.delete('limit');
        params.delete('offset');
        try {
            const resp = await fetch('/api/publishing/metrics/summary?' + params.toString());
            const data = await resp.json();
            const totals = data.totals || {};
            renderKpiRow(totals);
            renderSummaryCards(totals);
            renderPlatformBreakdown(data.by_platform || []);
        } catch (e) {
            renderKpiRow({});
            renderSummaryCards({});
            renderPlatformBreakdown([]);
        }
    }

    function postSortValue(post, column) {
        const m = post.metrics || {};
        if (column === 'title') return (post.title || '').toLowerCase();
        if (column === 'platform') return (post.platform_display_name || post.platform || '').toLowerCase();
        if (column === 'published_at') return post.published_at || '';
        const num = Number(m[column]);
        return Number.isFinite(num) ? num : 0;
    }

    function sortPosts(posts) {
        const sorted = [...posts];
        sorted.sort((a, b) => {
            const av = postSortValue(a, sortColumn);
            const bv = postSortValue(b, sortColumn);
            if (typeof av === 'string' || typeof bv === 'string') {
                const cmp = String(av).localeCompare(String(bv), 'zh-CN');
                return sortDirection === 'asc' ? cmp : -cmp;
            }
            return sortDirection === 'asc' ? av - bv : bv - av;
        });
        return sorted;
    }

    function updateSortHeaders() {
        document.querySelectorAll('#publishedPostsDataTable th[data-sort]').forEach((th) => {
            th.classList.remove('sort-asc', 'sort-desc');
            if (th.dataset.sort === sortColumn) {
                th.classList.add(sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
            }
        });
    }

    function sortTable(column) {
        if (!column) return;
        if (sortColumn === column) {
            sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            sortColumn = column;
            sortDirection = column === 'title' || column === 'platform' ? 'asc' : 'desc';
        }
        updateSortHeaders();
        renderPublishedPostsTable(cachedPosts);
    }

    function renderPublishedPostsTable(posts) {
        const tbody = document.getElementById('publishedPostsTable');
        if (!tbody) return;
        const rows = sortPosts(posts);
        tbody.innerHTML = rows.length ? rows.map(p => {
            const m = p.metrics || {};
            const link = p.platform_post_url
                ? `<a href="${p.platform_post_url}" target="_blank" rel="noopener">外链</a>`
                : '—';
            const trendBtn = `<button class="btn-secondary btn metrics-trend-btn" data-job-id="${p.job_id}" data-title="${encodeURIComponent(p.title || '')}">趋势</button>`;
            const canBind = ['unmatched', 'pending'].includes(p.metrics_match_status);
            const bindBtn = canBind
                ? `<button class="btn-secondary btn metrics-bind-btn" data-job-id="${p.job_id}" data-title="${encodeURIComponent(p.title || '')}">绑定</button>`
                : '';
            return `
            <tr>
                <td>${p.title || '—'}</td>
                <td>${p.platform_display_name || p.platform || '—'}<div style="font-size:12px;color:#64748b;">${p.account_nickname || ''}</div></td>
                <td>${formatCount(m.view_count)}</td>
                <td>${formatCount(m.like_count)}</td>
                <td>${formatCount(m.comment_count)}</td>
                <td>${formatCount(m.favorite_count)}</td>
                <td>${formatCount(m.follow_count)}</td>
                <td>${formatRate(m.play_3s_rate)}</td>
                <td>${formatRate(m.completion_rate)}</td>
                <td>${p.published_at ? formatBeijingDateTime(p.published_at) : '—'}</td>
                <td><span class="${matchStatusClass(p.metrics_match_status)}">${matchStatusLabel(p.metrics_match_status)}</span></td>
                <td>${trendBtn} ${bindBtn} ${link !== '—' ? link : ''}</td>
            </tr>`;
        }).join('') : '<tr><td colspan="12">暂无已发布作品</td></tr>';
        updateSortHeaders();
    }

    async function loadPublishedPosts() {
        const tbody = document.getElementById('publishedPostsTable');
        if (!tbody) return;
        const params = getFilterParams();
        const resp = await fetch('/api/publishing/published-posts?' + params.toString());
        const data = await resp.json();
        cachedPosts = data.posts || [];
        renderPublishedPostsPager(data.total || 0);
        renderPublishedPostsTable(cachedPosts);
    }

    function renderPublishedPostsPager(total) {
        const el = document.getElementById('publishedPostsPager');
        if (!el) return;
        const pages = Math.max(1, Math.ceil((Number(total) || 0) / PAGE_SIZE));
        if (metricsPage > pages) metricsPage = pages;
        el.innerHTML = `
            <button type="button" class="btn-secondary btn" data-metrics-page="prev" ${metricsPage <= 1 ? 'disabled' : ''}>上一页</button>
            <span>第 ${metricsPage} / ${pages} 页 · 共 ${total || 0} 条</span>
            <button type="button" class="btn-secondary btn" data-metrics-page="next" ${metricsPage >= pages ? 'disabled' : ''}>下一页</button>
        `;
    }

    function drawTrendChart(history) {
        const canvas = document.getElementById('metricsTrendCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const width = canvas.width;
        const height = canvas.height;
        ctx.clearRect(0, 0, width, height);
        if (!history || !history.length) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '14px sans-serif';
            ctx.fillText('暂无历史快照，请先执行同步并等待次日更新', 40, height / 2);
            return;
        }

        const padding = { top: 20, right: 20, bottom: 40, left: 50 };
        const chartW = width - padding.left - padding.right;
        const chartH = height - padding.top - padding.bottom;
        const series = [
            { key: 'view_count', color: METRIC_COLORS.view_count },
            { key: 'like_count', color: METRIC_COLORS.like_count },
            { key: 'comment_count', color: METRIC_COLORS.comment_count },
        ];

        const labels = history.map(h => h.snapshot_date.slice(5));
        const maxVal = Math.max(
            1,
            ...history.flatMap(h => series.map(s => Number(h[s.key]) || 0)),
        );

        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = padding.top + (chartH * i) / 4;
            ctx.beginPath();
            ctx.moveTo(padding.left, y);
            ctx.lineTo(width - padding.right, y);
            ctx.stroke();
        }

        series.forEach(s => {
            ctx.strokeStyle = s.color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            history.forEach((point, index) => {
                const x = padding.left + (chartW * index) / Math.max(history.length - 1, 1);
                const val = Number(point[s.key]) || 0;
                const y = padding.top + chartH - (val / maxVal) * chartH;
                if (index === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();
        });

        ctx.fillStyle = '#64748b';
        ctx.font = '11px sans-serif';
        labels.forEach((label, index) => {
            if (history.length > 14 && index % 2 !== 0) return;
            const x = padding.left + (chartW * index) / Math.max(history.length - 1, 1);
            ctx.fillText(label, x - 14, height - 12);
        });
    }

    async function showPostTrend(jobId, title) {
        const modal = document.getElementById('metricsTrendModal');
        const titleEl = document.getElementById('metricsTrendTitle');
        const metaEl = document.getElementById('metricsTrendMeta');
        if (!modal) return;
        titleEl.textContent = title || '作品趋势';
        metaEl.textContent = '加载中…';
        modal.style.display = 'flex';

        const days = document.getElementById('metricsDaysFilter')?.value || '30';
        try {
            const resp = await fetch(`/api/publishing/published-posts/${jobId}/metrics?days=${days}`);
            const data = await resp.json();
            const history = data.history || [];
            metaEl.textContent = history.length
                ? `共 ${history.length} 个快照点（近 ${days} 天）`
                : '暂无历史数据，请先点击「立即同步」';
            drawTrendChart(history);
        } catch (e) {
            metaEl.textContent = '加载失败';
            drawTrendChart([]);
        }
    }

    function closeTrendModal() {
        const modal = document.getElementById('metricsTrendModal');
        if (modal) modal.style.display = 'none';
    }

    async function reloadMetricsTab() {
        await Promise.all([
            loadSyncStatus(),
            loadMetricsSummary(),
            loadMetricsAlerts(),
            loadPublishedPosts(),
        ]);
    }

    async function triggerMetricsSync() {
        const btn = document.getElementById('metricsSyncBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = '同步中…';
        }
        try {
            const resp = await fetch('/api/publishing/metrics/sync', { method: 'POST' });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || '同步失败');
            alert(formatSyncRunLine(data, { prefix: '同步完成' }));
            await reloadMetricsTab();
        } catch (e) {
            alert('同步失败: ' + e.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = '立即同步';
            }
        }
    }

    function initPublishedMetricsTab() {
        if (!document.getElementById('metricsSummaryCards')) return;
        document.getElementById('metricsSyncBtn')?.addEventListener('click', triggerMetricsSync);
        document.getElementById('metricsExportBtn')?.addEventListener('click', exportMetricsCsv);
        document.getElementById('metricsBindCancelBtn')?.addEventListener('click', closeBindModal);
        document.getElementById('metricsBindSaveBtn')?.addEventListener('click', saveBindModal);
        document.getElementById('metricsBindModal')?.addEventListener('click', (e) => {
            if (e.target.id === 'metricsBindModal') closeBindModal();
        });
        document.getElementById('metricsTrendCloseBtn')?.addEventListener('click', closeTrendModal);
        document.getElementById('metricsTrendModal')?.addEventListener('click', (e) => {
            if (e.target.id === 'metricsTrendModal') closeTrendModal();
        });
        ['metricsPlatformFilter', 'metricsAccountFilter', 'metricsDaysFilter'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', () => {
                metricsPage = 1;
                reloadMetricsTab();
            });
        });
        document.getElementById('publishedPostsPager')?.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-metrics-page]');
            if (!btn || btn.disabled) return;
            if (btn.dataset.metricsPage === 'prev' && metricsPage > 1) {
                metricsPage -= 1;
                loadPublishedPosts();
            } else if (btn.dataset.metricsPage === 'next') {
                metricsPage += 1;
                loadPublishedPosts();
            }
        });
        document.getElementById('publishedPostsDataTable')?.addEventListener('click', (e) => {
            const th = e.target.closest('th[data-sort]');
            if (th) {
                sortTable(th.dataset.sort);
                return;
            }
        });
        document.getElementById('publishedPostsTable')?.addEventListener('click', (e) => {
            const trendBtn = e.target.closest('.metrics-trend-btn');
            if (trendBtn) {
                showPostTrend(trendBtn.dataset.jobId, decodeURIComponent(trendBtn.dataset.title || ''));
                return;
            }
            const bindBtn = e.target.closest('.metrics-bind-btn');
            if (bindBtn) {
                openBindModal(bindBtn.dataset.jobId, decodeURIComponent(bindBtn.dataset.title || ''));
            }
        });
        Promise.all([loadMetricsPlatforms(), loadMetricsAccounts()]).then(reloadMetricsTab);
    }

    window.showPostTrend = showPostTrend;
    window.loadPublishedPosts = loadPublishedPosts;
    window.initPublishedMetricsTab = initPublishedMetricsTab;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPublishedMetricsTab);
    } else {
        initPublishedMetricsTab();
    }
})();
