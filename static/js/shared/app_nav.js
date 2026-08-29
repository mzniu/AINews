/**
 * 全站统一顶部导航 — 挂载到 #app-nav-root
 */
(function () {
    const PATH_ALIASES = {
        '/model-settings': '/settings',
    };

    const NAV_ITEMS = [
        { href: '/', label: '主页', match: (p) => p === '/' || p === '/index.html' },
        { href: '/video-maker', label: '视频制作' },
        { href: '/ingestion-library', label: '资讯库' },
        { href: '/hot-radar', label: '热榜雷达' },
        { href: '/publish-center', label: '发布中心' },
        { href: '/publish-queue', label: '发布队列', match: (p) => p === '/publish-queue' },
        { href: '/settings', label: '系统配置', match: (p) => p === '/settings' || p === '/model-settings' },
        { href: '/github-video-maker', label: 'GitHub' },
        { href: '/digital-human', label: '数字人' },
    ];

    function normalizePath(pathname) {
        const trimmed = (pathname || '/').replace(/\/+$/, '') || '/';
        return PATH_ALIASES[trimmed] || trimmed;
    }

    function isActive(item, pathname) {
        const current = normalizePath(pathname);
        if (typeof item.match === 'function') {
            return item.match(current);
        }
        const href = item.href.replace(/\/+$/, '') || '/';
        return current === href;
    }

    function renderNav(root) {
        const pathname = window.location.pathname;
        const links = NAV_ITEMS.map((item) => {
            const cls = isActive(item, pathname) ? 'nav-link active' : 'nav-link';
            return `<a href="${item.href}" class="${cls}">${item.label}</a>`;
        }).join('\n                ');

        root.innerHTML = `
    <nav class="app-nav navbar" aria-label="站点导航">
        <div class="nav-container">
            <a href="/" class="nav-brand">AINews</a>
            <div class="nav-menu">
                ${links}
            </div>
        </div>
    </nav>`;
    }

    function init() {
        const root = document.getElementById('app-nav-root');
        if (root) {
            renderNav(root);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.AppNav = { NAV_ITEMS, renderNav, normalizePath, isActive };
})();
