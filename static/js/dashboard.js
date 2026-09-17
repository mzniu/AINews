(function () {
    const SPRITE = '/static/icons/sprites.svg';

    function icon(name) {
        return `<svg class="nav-icon" aria-hidden="true"><use href="${SPRITE}#icon-${name}"/></svg>`;
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value ?? '—';
    }

    function setPipelineStep(index, state, sub) {
        const step = document.querySelector(`.pipeline-step[data-step="${index}"]`);
        if (!step) return;
        step.classList.remove('is-done', 'is-active');
        if (state) step.classList.add(state);
        if (sub) {
            const subEl = step.querySelector('.pipeline-sub');
            if (subEl) subEl.textContent = sub;
        }
    }

    async function fetchJson(url) {
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`${url} ${resp.status}`);
        return resp.json();
    }

    async function loadMetrics() {
        let articlesToday = '—';
        let pending = '—';
        let candidates = '—';
        let views = '—';

        try {
            const articles = await fetchJson('/api/ingestion/articles?limit=1');
            if (typeof articles.total === 'number') {
                articlesToday = String(articles.total);
            }
        } catch (err) {
            console.warn('ingestion articles', err);
        }

        try {
            const jobs = await fetchJson('/api/publishing/jobs?status=pending&limit=200');
            const list = jobs.items || jobs.jobs || [];
            pending = String(Array.isArray(list) ? list.length : (jobs.total ?? '—'));
        } catch (err) {
            console.warn('publish jobs', err);
        }

        try {
            const pool = await fetchJson('/api/publishing/candidates?limit=1');
            candidates = String(pool.total ?? (pool.items || []).length ?? '—');
        } catch (err) {
            console.warn('candidates', err);
        }

        try {
            const summary = await fetchJson('/api/publishing/metrics/summary?days=7');
            const totalViews = summary.total_views ?? summary.views ?? summary.play_count;
            if (totalViews != null) {
                views = totalViews >= 1000
                    ? `${(totalViews / 1000).toFixed(1)}k`
                    : String(totalViews);
            }
        } catch (err) {
            console.warn('metrics summary', err);
        }

        setText('metricArticles', articlesToday);
        setText('metricPending', pending);
        setText('metricCandidates', candidates);
        setText('metricViews', views);

        setPipelineStep(1, 'is-done', '资讯库');
        setPipelineStep(2, pending !== '0' && pending !== '—' ? 'is-active' : 'is-done', `${pending} 待发布`);
        setPipelineStep(3, 'is-active', '制作中');
        setPipelineStep(4, Number(pending) > 0 ? 'is-active' : '', `队列 ${pending}`);
    }

    async function loadHotRadar() {
        const list = document.getElementById('hotTopList');
        if (!list) return;
        try {
            const data = await fetchJson('/api/ingestion/hot-radar?limit=1');
            const snapshot = (data.items || data.snapshots || [])[0];
            const hits = snapshot?.hits || snapshot?.articles || [];
            if (!hits.length) {
                list.innerHTML = '<li>暂无热榜数据</li>';
                return;
            }
            list.innerHTML = hits.slice(0, 5).map((item, idx) => `
                <li>
                    <span class="hot-rank">${idx + 1}</span>
                    <span>${item.title || item.headline || '—'}</span>
                </li>`).join('');
        } catch (err) {
            list.innerHTML = '<li>热榜加载失败</li>';
            console.warn('hot radar', err);
        }
    }

    async function loadActivity() {
        const list = document.getElementById('activityList');
        if (!list) return;
        const lines = [];
        try {
            const jobs = await fetchJson('/api/publishing/jobs?limit=5');
            (jobs.items || jobs.jobs || []).slice(0, 3).forEach((job) => {
                lines.push(`发布队列 · ${job.title || job.id || '任务'}`);
            });
        } catch (err) {
            console.warn('activity jobs', err);
        }
        list.innerHTML = lines.length
            ? lines.map((line) => `<li>${line}</li>`).join('')
            : '<li>暂无最近动态</li>';
    }

    async function init() {
        await Promise.all([loadMetrics(), loadHotRadar(), loadActivity()]);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
