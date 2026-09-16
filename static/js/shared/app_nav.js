/**
 * 全站统一左侧导航 — 挂到 #app-nav-root
 */
(function () {
    const SPRITE = '/static/icons/sprites.svg';
    const PATH_ALIASES = {
        '/model-settings': '/settings',
        '/index.html': '/',
    };

    const NAV_GROUPS = [
        {
            items: [
                {
                    href: '/',
                    label: '工作台',
                    icon: 'home',
                    match: (p) => p === '/' || p === '/index.html',
                },
            ],
        },
        {
            label: '内容',
            items: [
                { href: '/ingestion-library', label: '资讯库', icon: 'library' },
                { href: '/hot-radar', label: '热榜雷达', icon: 'radar' },
            ],
        },
        {
            label: '制作',
            items: [
                { href: '/video-maker', label: '视频制作', icon: 'film' },
                { href: '/github-video-maker', label: 'GitHub', icon: 'film' },
                { href: '/digital-human', label: '数字人', icon: 'film' },
                { href: '/scrape', label: '内容抓取', icon: 'scrape' },
            ],
        },
        {
            label: '分发',
            items: [
                {
                    href: '/publish-center',
                    label: '发布中心',
                    icon: 'send',
                    match: (p) => p === '/publish-center'
                        || p.startsWith('/publish-')
                        || p === '/candidate-pool',
                },
            ],
        },
        {
            label: '系统',
            items: [
                {
                    href: '/settings',
                    label: '系统配置',
                    icon: 'settings',
                    match: (p) => p === '/settings' || p === '/model-settings',
                },
            ],
        },
    ];

    const NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items);
    const NAV_COLLAPSE_KEY = 'ainews-nav-collapsed';
    const APP_VERSION_FALLBACK = '1.0.2';
    let userMenuOpen = false;
    let userMenuDocListenerBound = false;

    function esc(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/"/g, '&quot;');
    }

    function navIcon(name) {
        if (!name) return '';
        return `<svg class="nav-icon" aria-hidden="true"><use href="${SPRITE}#icon-${esc(name)}"/></svg>`;
    }

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

    function forceRefresh() {
        const url = new URL(window.location.href);
        url.searchParams.set('_refresh', String(Date.now()));
        if ('caches' in window) {
            caches.keys()
                .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
                .finally(() => {
                    window.location.replace(url.toString());
                });
            return;
        }
        window.location.replace(url.toString());
    }

    function getNavCollapsed() {
        try {
            return localStorage.getItem(NAV_COLLAPSE_KEY) === '1';
        } catch (_) {
            return false;
        }
    }

    function setNavCollapsed(collapsed) {
        const isCollapsed = Boolean(collapsed);
        document.body.classList.toggle('nav-collapsed', isCollapsed);
        document.body.classList.toggle('nav-top-bar', isCollapsed);
        document.body.dataset.navCollapsed = isCollapsed ? 'true' : 'false';
        try {
            localStorage.setItem(NAV_COLLAPSE_KEY, isCollapsed ? '1' : '0');
        } catch (_) {
            /* ignore */
        }
        const btn = document.getElementById('app-nav-collapse');
        if (btn) {
            btn.setAttribute('aria-pressed', isCollapsed ? 'true' : 'false');
            btn.title = isCollapsed ? '展开侧栏' : '收起侧栏';
            btn.setAttribute('aria-label', btn.title);
        }
    }

    function toggleNavCollapse() {
        setNavCollapsed(!getNavCollapsed());
    }

    function bindNavCollapseButton(root) {
        const btn = root.querySelector('#app-nav-collapse');
        if (!btn || btn.dataset.bound === '1') return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', (event) => {
            event.preventDefault();
            toggleNavCollapse();
        });
    }

    function bindRefreshButton(root) {
        const btn = root.querySelector('#app-nav-refresh');
        if (!btn) return;
        btn.addEventListener('click', (event) => {
            event.preventDefault();
            forceRefresh();
        });
    }

    function renderGroup(group, pathname) {
        const links = group.items.map((item) => {
            const cls = isActive(item, pathname) ? 'nav-link active' : 'nav-link';
            return `<a href="${item.href}" class="${cls}">${navIcon(item.icon)}<span class="nav-label">${esc(item.label)}</span></a>`;
        }).join('');
        const label = group.label
            ? `<div class="nav-group-label">${esc(group.label)}</div>`
            : '';
        return `<div class="nav-group">${label}${links}</div>`;
    }

    function renderNav(root) {
        const pathname = window.location.pathname;
        const groups = NAV_GROUPS.map((group) => renderGroup(group, pathname)).join('');

        root.innerHTML = `
    <nav class="app-nav" aria-label="站点导航">
        <div class="nav-sidebar">
            <div class="nav-brand-row">
                <a href="/" class="nav-brand">
                    <img class="nav-brand-icon" src="/static/brand/ainews-mark.png?v=20260913" width="32" height="32" alt="">
                    <span>AINews</span>
                </a>
                <button type="button" class="nav-refresh-btn" id="app-nav-refresh" title="强制刷新" aria-label="强制刷新">
                    ${navIcon('refresh')}
                </button>
                <button type="button" class="nav-collapse-btn" id="app-nav-collapse" title="收起侧栏" aria-label="收起侧栏" aria-pressed="false">
                    ${navIcon('settings')}
                </button>
            </div>
            <div class="nav-top-bar" aria-label="快捷导航">
                ${NAV_ITEMS.map((item) => {
                    const cls = isActive(item, pathname) ? 'nav-top-link active' : 'nav-top-link';
                    return `<a href="${item.href}" class="${cls}" title="${esc(item.label)}">${navIcon(item.icon)}<span>${esc(item.label)}</span></a>`;
                }).join('')}
            </div>
            <div class="nav-scroll">
                <div id="global-search-root" class="nav-global-search"></div>
                ${groups}
            </div>
            <div class="nav-footer">
                <div class="nav-theme-row">
                    <span data-theme-label>浅色</span>
                    <button type="button" class="theme-toggle" aria-label="切换主题">
                        ${navIcon('sun').replace('nav-icon', 'nav-icon icon-sun')}
                        ${navIcon('moon').replace('nav-icon', 'nav-icon icon-moon')}
                    </button>
                </div>
                <div class="nav-user-menu" id="app-nav-user-menu">
                    <button type="button" class="nav-user-trigger" id="app-nav-user-trigger" aria-label="用户菜单" aria-haspopup="menu" aria-expanded="false" aria-controls="app-nav-user-dropdown">
                        <span class="nav-user-avatar" id="app-nav-user-avatar" aria-hidden="true">U</span>
                        <span class="nav-user-copy" aria-hidden="true">
                            <span class="nav-user-name" id="app-nav-user-name">用户</span>
                            <span class="nav-version" id="app-nav-version">v${esc(APP_VERSION_FALLBACK)}</span>
                        </span>
                        <svg class="nav-user-chevron" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                            <path fill="currentColor" d="M7 10l5 5 5-5z"/>
                        </svg>
                    </button>
                    <div class="nav-user-dropdown" id="app-nav-user-dropdown" role="menu" hidden></div>
                </div>
            </div>
        </div>
    </nav>`;

        bindRefreshButton(root);
        bindNavCollapseButton(root);
        setNavCollapsed(getNavCollapsed());
        bindUserMenu(root);
        bindAuthStatusListener(root);
        bindVersion(root);
        if (window.AINewsTheme) {
            window.AINewsTheme.apply(window.AINewsTheme.getPreferred());
        }
    }

    function formatAuthLabel(status) {
        if (status?.phone) return status.phone;
        if (status?.email) return status.email;
        if (status?.mode === 'offline') return '离线授权';
        if (status?.authorized) return '已登录';
        return '未登录';
    }

    function formatModeLabel(mode) {
        if (mode === 'offline') return '离线授权';
        if (mode === 'online') return '在线账号';
        return '本地模式';
    }

    function formatAccountStatus(status) {
        const map = {
            active: '正常',
            inactive: '未激活',
            suspended: '已停用',
        };
        return map[status] || status || '';
    }

    function userInitial(label) {
        const text = String(label || '').trim();
        if (!text) return 'U';
        return text.charAt(0).toUpperCase();
    }

    function closeUserMenu(root) {
        const menu = root.querySelector('#app-nav-user-menu');
        const trigger = root.querySelector('#app-nav-user-trigger');
        const dropdown = root.querySelector('#app-nav-user-dropdown');
        if (!menu || !trigger || !dropdown) return;
        userMenuOpen = false;
        menu.classList.remove('is-open');
        trigger.setAttribute('aria-expanded', 'false');
        dropdown.hidden = true;
    }

    function openUserMenu(root) {
        const menu = root.querySelector('#app-nav-user-menu');
        const trigger = root.querySelector('#app-nav-user-trigger');
        const dropdown = root.querySelector('#app-nav-user-dropdown');
        if (!menu || !trigger || !dropdown) return;
        userMenuOpen = true;
        menu.classList.add('is-open');
        trigger.setAttribute('aria-expanded', 'true');
        dropdown.hidden = false;
    }

    function toggleUserMenu(root) {
        if (userMenuOpen) closeUserMenu(root);
        else openUserMenu(root);
    }

    function bindUserMenuInteractions(root) {
        const trigger = root.querySelector('#app-nav-user-trigger');
        if (!trigger || trigger.dataset.bound === '1') return;
        trigger.dataset.bound = '1';
        trigger.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            toggleUserMenu(root);
        });

        if (!userMenuDocListenerBound) {
            userMenuDocListenerBound = true;
            document.addEventListener('click', (event) => {
                const navRoot = document.getElementById('app-nav-root');
                if (!navRoot || !userMenuOpen) return;
                if (navRoot.contains(event.target)) return;
                closeUserMenu(navRoot);
            });
            document.addEventListener('keydown', (event) => {
                if (event.key !== 'Escape' || !userMenuOpen) return;
                const navRoot = document.getElementById('app-nav-root');
                if (navRoot) closeUserMenu(navRoot);
            });
        }
    }

    function renderDropdownItem({ label, action, danger = false, href = '' }) {
        if (href) {
            return `<a class="nav-user-item${danger ? ' is-danger' : ''}" role="menuitem" href="${esc(href)}" data-action="${esc(action)}">${esc(label)}</a>`;
        }
        return `<button type="button" class="nav-user-item${danger ? ' is-danger' : ''}" role="menuitem" data-action="${esc(action)}">${esc(label)}</button>`;
    }

    function renderUserDropdown(status, { isDesktop }) {
        if (!isDesktop) {
            return `
                <div class="nav-user-dropdown-header">
                    <div class="nav-user-dropdown-title">本地模式</div>
                    <div class="nav-user-dropdown-subtitle">浏览器直接访问，无需云账号</div>
                </div>
                <div class="nav-user-dropdown-body">
                    ${renderDropdownItem({ label: '系统配置', action: 'settings', href: '/settings' })}
                    ${renderDropdownItem({ label: '强制刷新', action: 'refresh' })}
                </div>`;
        }

        if (!status?.authorized) {
            return `
                <div class="nav-user-dropdown-header">
                    <div class="nav-user-dropdown-title">未登录</div>
                    <div class="nav-user-dropdown-subtitle">登录后可同步配置与订阅状态</div>
                </div>
                <div class="nav-user-dropdown-body">
                    ${renderDropdownItem({ label: '登录账号', action: 'login' })}
                    ${renderDropdownItem({ label: '强制刷新', action: 'refresh' })}
                </div>`;
        }

        const label = formatAuthLabel(status);
        const modeLabel = formatModeLabel(status.mode);
        const accountStatus = formatAccountStatus(status.accountStatus);
        const subtitleParts = [modeLabel];
        if (accountStatus && status.mode === 'online') subtitleParts.push(accountStatus);
        if (status.mode === 'offline' && status.offlineExpiresAt) {
            subtitleParts.push(`有效期至 ${status.offlineExpiresAt}`);
        }
        const message = status.message
            ? `<div class="nav-user-dropdown-message">${esc(status.message)}</div>`
            : '';

        const items = [];
        if (status.mode === 'online') {
            items.push(renderDropdownItem({ label: '刷新登录状态', action: 'refresh-auth' }));
        }
        items.push(renderDropdownItem({ label: '强制刷新', action: 'refresh' }));
        items.push(renderDropdownItem({ label: '退出登录', action: 'logout', danger: true }));

        return `
            <div class="nav-user-dropdown-header">
                <div class="nav-user-dropdown-title">${esc(label)}</div>
                <div class="nav-user-dropdown-subtitle">${esc(subtitleParts.join(' · '))}</div>
                ${message}
            </div>
            <div class="nav-user-dropdown-body">
                ${items.join('')}
            </div>`;
    }

    function bindDropdownActions(root) {
        const menu = root.querySelector('#app-nav-user-menu');
        const invoke = window.__TAURI__?.core?.invoke;
        if (!menu || menu.dataset.actionsBound === '1') return;
        menu.dataset.actionsBound = '1';
        menu.addEventListener('click', async (event) => {
            const item = event.target.closest('[data-action]');
            if (!item) return;
            const action = item.dataset.action;
            closeUserMenu(root);
            if (action === 'refresh') {
                forceRefresh();
                return;
            }
            if (!invoke) return;
            try {
                if (action === 'login') {
                    await invoke('ainews_show_login');
                } else if (action === 'logout') {
                    await invoke('auth_logout');
                    await invoke('ainews_show_login');
                } else if (action === 'refresh-auth') {
                    await invoke('auth_refresh');
                }
                await bindUserMenu(root);
            } catch (err) {
                console.error(err);
            }
        });
    }

    async function fetchAuthStatus() {
        const invoke = window.__TAURI__?.core?.invoke;
        if (invoke) {
            try {
                return await invoke('auth_get_status');
            } catch (err) {
                console.warn('auth_get_status invoke failed, falling back to HTTP', err);
            }
        }
        try {
            const resp = await fetch('/api/desktop/auth-status');
            if (!resp.ok) return null;
            return await resp.json();
        } catch (err) {
            console.warn('auth status HTTP fallback failed', err);
            return null;
        }
    }

    async function bindUserMenu(root) {
        const avatar = root.querySelector('#app-nav-user-avatar');
        const name = root.querySelector('#app-nav-user-name');
        const dropdown = root.querySelector('#app-nav-user-dropdown');
        const invoke = window.__TAURI__?.core?.invoke;
        const isDesktop = Boolean(invoke);

        bindUserMenuInteractions(root);
        bindDropdownActions(root);

        const status = isDesktop ? await fetchAuthStatus() : null;
        const label = isDesktop ? formatAuthLabel(status) : '本地模式';
        if (avatar) avatar.textContent = userInitial(label);
        if (name) {
            name.textContent = label;
            name.title = label;
        }
        if (dropdown) {
            dropdown.innerHTML = renderUserDropdown(status, { isDesktop });
        }
    }

    const DEVTOOLS_CLICKS_REQUIRED = 5;
    const DEVTOOLS_CLICK_WINDOW_MS = 2500;

    async function openDevTools() {
        const invoke = window.__TAURI__?.core?.invoke;
        if (!invoke) {
            console.warn('开发者工具仅可在桌面客户端中使用');
            return;
        }
        try {
            await invoke('ainews_open_devtools');
        } catch (err) {
            console.warn('打开开发者工具失败', err);
        }
    }

    function bindVersionDevTools(el) {
        if (!el || el.dataset.devtoolsBound === '1') return;
        el.dataset.devtoolsBound = '1';
        let clicks = 0;
        let resetTimer = null;

        el.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            clicks += 1;
            if (resetTimer) clearTimeout(resetTimer);
            if (clicks >= DEVTOOLS_CLICKS_REQUIRED) {
                clicks = 0;
                openDevTools();
                return;
            }
            resetTimer = setTimeout(() => {
                clicks = 0;
            }, DEVTOOLS_CLICK_WINDOW_MS);
        });
    }

    async function bindVersion(root) {
        const el = root.querySelector('#app-nav-version');
        if (!el) return;
        bindVersionDevTools(el);
        try {
            const resp = await fetch('/api/health');
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.version) el.textContent = `v${data.version}`;
        } catch (err) {
            console.warn('app version lookup failed', err);
        }
    }

    function bindAuthStatusListener(root) {
        const listen = window.__TAURI__?.event?.listen;
        if (!listen || root.dataset.authListener === '1') return;
        root.dataset.authListener = '1';
        listen('auth://status-changed', () => {
            bindUserMenu(root).catch((err) => console.warn(err));
        }).catch((err) => console.warn('auth listener unavailable', err));
        listen('ainews:backend-ready', () => {
            bindUserMenu(root).catch((err) => console.warn(err));
        }).catch(() => {});
    }

    function ensureFavicon() {
        if (document.querySelector('link[rel="icon"]')) return;
        const icon = document.createElement('link');
        icon.rel = 'icon';
        icon.type = 'image/png';
        icon.href = '/static/brand/ainews-mark.png?v=20260913';
        document.head.appendChild(icon);
    }

    function initGlobalSearch() {
        const host = document.getElementById('global-search-root');
        if (!host) return;
        const mount = () => window.AINewsGlobalSearch?.mount(host);
        if (window.AINewsGlobalSearch) {
            mount();
            return;
        }
        const script = document.createElement('script');
        script.src = '/static/js/shared/global_search.js?v=20260916';
        script.onload = mount;
        document.head.appendChild(script);
    }

    function init() {
        ensureFavicon();
        const root = document.getElementById('app-nav-root');
        if (root) {
            renderNav(root);
            initGlobalSearch();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.AppNav = {
        NAV_ITEMS,
        NAV_GROUPS,
        renderNav,
        normalizePath,
        isActive,
        forceRefresh,
        getNavCollapsed,
        setNavCollapsed,
        toggleNavCollapse,
    };
})();
