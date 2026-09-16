(function () {
    const KIND_LABEL = { language: '语言', vision: '视觉' };
    const EMPTY_TEXT = '该时间范围内还没有用量记录。完成一次模型测试或资讯评分后会显示在这里。';

    const $ = (id) => document.getElementById(id);

    function formatCount(value) {
        const n = Number(value || 0);
        return Number.isFinite(n) ? n.toLocaleString('zh-CN') : '0';
    }

    function setStatus(text, type) {
        const bar = $('usageStatusBar');
        if (!bar) return;
        bar.textContent = text || '';
        bar.className = 'status-bar' + (type ? ` ${type}` : '');
    }

    function renderCards(totals) {
        const el = $('usageSummaryCards');
        if (!el) return;
        const cards = [
            { label: '总 Token', value: formatCount(totals.total_tokens) },
            { label: '语言模型', value: formatCount(totals.language_tokens) },
            { label: '视觉模型', value: formatCount(totals.vision_tokens) },
            { label: '调用次数', value: formatCount(totals.calls) },
        ];
        el.innerHTML = cards.map((card) => `
            <div class="usage-summary-card">
                <div class="label">${card.label}</div>
                <div class="value">${card.value}</div>
            </div>
        `).join('');
    }

    function renderTable(containerId, columns, rows) {
        const el = $(containerId);
        if (!el) return;
        if (!rows.length) {
            el.innerHTML = `<p class="section-desc">${EMPTY_TEXT}</p>`;
            return;
        }
        el.innerHTML = `
            <div class="usage-table-wrap">
                <table class="usage-table">
                    <thead><tr>${columns.map((col) => `<th>${col.label}</th>`).join('')}</tr></thead>
                    <tbody>
                        ${rows.map((row) => `<tr>${columns.map((col) => `<td>${col.value(row)}</td>`).join('')}</tr>`).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    async function loadTokenUsage() {
        const range = $('usageRangeSelect')?.value || '7d';
        setStatus('加载中…');
        try {
            const resp = await fetch(`/api/models/usage?range=${encodeURIComponent(range)}`);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || '加载失败');
            const totals = data.totals || {};
            renderCards(totals);
            renderTable('usageByModel', [
                { label: '类型', value: (row) => KIND_LABEL[row.kind] || row.kind },
                { label: '名称', value: (row) => row.display_name || row.model || '—' },
                { label: '模型', value: (row) => row.model || '—' },
                { label: '次数', value: (row) => formatCount(row.calls) },
                { label: '输入', value: (row) => formatCount(row.prompt_tokens) },
                { label: '输出', value: (row) => formatCount(row.completion_tokens) },
                { label: '合计', value: (row) => formatCount(row.total_tokens) },
            ], data.by_model || []);
            renderTable('usageByTask', [
                { label: '任务', value: (row) => row.label || row.task },
                { label: '次数', value: (row) => formatCount(row.calls) },
                { label: '合计 Token', value: (row) => formatCount(row.total_tokens) },
            ], data.by_task || []);
            setStatus(totals.calls ? `已统计 ${formatCount(totals.calls)} 次调用` : '暂无记录', totals.calls ? 'ok' : '');
        } catch (err) {
            setStatus(err.message || '加载失败', 'error');
        }
    }

    async function clearTokenUsage() {
        if (!window.confirm('清空本机全部 token 统计？不可恢复。')) return;
        try {
            const resp = await fetch('/api/models/usage/clear', { method: 'POST' });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || '清空失败');
            await loadTokenUsage();
            setStatus(`已清空 ${formatCount(data.deleted)} 条记录`, 'ok');
        } catch (err) {
            setStatus(err.message || '清空失败', 'error');
        }
    }

    window.loadTokenUsage = loadTokenUsage;

    document.addEventListener('DOMContentLoaded', () => {
        $('usageRangeSelect')?.addEventListener('change', loadTokenUsage);
        $('reloadUsageBtn')?.addEventListener('click', loadTokenUsage);
        $('clearUsageBtn')?.addEventListener('click', clearTokenUsage);
    });
})();
