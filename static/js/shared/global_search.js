/**
 * Global search — articles + published posts via /api/search
 */
(function () {
    const DEBOUNCE_MS = 280;
    let debounceTimer = null;

    function esc(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/"/g, '&quot;');
    }

    function renderResults(data, dropdown) {
        const articles = data.articles || [];
        const posts = data.published_posts || [];
        if (!articles.length && !posts.length) {
            dropdown.innerHTML = '<div class="global-search-empty">无匹配结果</div>';
            dropdown.hidden = false;
            return;
        }
        const articleHtml = articles.length
            ? `<div class="global-search-group"><div class="global-search-group-label">资讯库</div>${articles.map((a) => `
                <a class="global-search-item" href="${esc(a.href)}">
                    <span class="global-search-title">${esc(a.title)}</span>
                    ${a.score_grade ? `<span class="global-search-meta">${esc(a.score_grade)}</span>` : ''}
                </a>`).join('')}</div>`
            : '';
        const postsHtml = posts.length
            ? `<div class="global-search-group"><div class="global-search-group-label">发布记录</div>${posts.map((p) => `
                <a class="global-search-item" href="${esc(p.href)}">
                    <span class="global-search-title">${esc(p.title)}</span>
                    <span class="global-search-meta">${esc(p.platform || '')}</span>
                </a>`).join('')}</div>`
            : '';
        dropdown.innerHTML = articleHtml + postsHtml;
        dropdown.hidden = false;
    }

    async function runSearch(query, dropdown) {
        const q = query.trim();
        if (!q) {
            dropdown.hidden = true;
            dropdown.innerHTML = '';
            return;
        }
        dropdown.innerHTML = '<div class="global-search-empty">搜索中…</div>';
        dropdown.hidden = false;
        try {
            const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=8`);
            if (!resp.ok) throw new Error(String(resp.status));
            const data = await resp.json();
            renderResults(data, dropdown);
        } catch (err) {
            console.warn('global search failed', err);
            dropdown.innerHTML = '<div class="global-search-empty">搜索失败</div>';
        }
    }

    function bindSearch(root) {
        const input = root.querySelector('#global-search-input');
        const dropdown = root.querySelector('#global-search-dropdown');
        if (!input || !dropdown) return;

        input.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => runSearch(input.value, dropdown), DEBOUNCE_MS);
        });

        input.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                dropdown.hidden = true;
                input.blur();
            }
        });

        document.addEventListener('click', (event) => {
            if (!root.contains(event.target)) dropdown.hidden = true;
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey) {
                const tag = (event.target?.tagName || '').toLowerCase();
                if (tag === 'input' || tag === 'textarea' || event.target?.isContentEditable) return;
                event.preventDefault();
                input.focus();
            }
        });
    }

    function mount(host) {
        if (!host || host.dataset.searchBound === '1') return;
        host.dataset.searchBound = '1';
        host.innerHTML = `
            <div class="global-search" role="search">
                <label class="sr-only" for="global-search-input">全局搜索</label>
                <input id="global-search-input" class="global-search-input form-control"
                    type="search" placeholder="搜索资讯 / 发布记录 (按 / 聚焦)" autocomplete="off">
                <div id="global-search-dropdown" class="global-search-dropdown" hidden></div>
            </div>`;
        bindSearch(host);
    }

    window.AINewsGlobalSearch = { mount, runSearch };
})();
