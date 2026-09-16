(function () {
    const TABS = [
        { id: 'accounts', label: '账号绑定' },
        { id: 'queue', label: '发布队列' },
        { id: 'metrics', label: '已发布数据' },
        { id: 'comments', label: '评论管理' },
        { id: 'pool', label: '候选池' },
    ];

    const IFRAME_SRC = {
        queue: '/publish-queue?embed=1',
        metrics: '/publish-metrics?embed=1',
        comments: '/publish-comments?embed=1',
        pool: '/candidate-pool?embed=1',
    };

    function currentTab() {
        const params = new URLSearchParams(window.location.search);
        const tab = params.get('tab') || 'accounts';
        return TABS.some((t) => t.id === tab) ? tab : 'accounts';
    }

    function activate(tabId) {
        document.querySelectorAll('.hub-tab').forEach((btn) => {
            btn.classList.toggle('is-active', btn.dataset.tab === tabId);
        });
        document.querySelectorAll('.hub-panel').forEach((panel) => {
            const active = panel.dataset.tabPanel === tabId;
            panel.hidden = !active;
        });
        const url = new URL(window.location.href);
        url.searchParams.set('tab', tabId);
        window.history.replaceState({}, '', url.toString());
    }

    function bindTabs() {
        document.querySelectorAll('.hub-tab').forEach((btn) => {
            btn.addEventListener('click', () => activate(btn.dataset.tab));
        });
        activate(currentTab());
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindTabs);
    } else {
        bindTabs();
    }
})();
