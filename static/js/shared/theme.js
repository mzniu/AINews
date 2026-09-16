(function () {
    const STORAGE_KEY = 'ainews-theme';
    const root = document.documentElement;

    function getPreferred() {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved === 'light' || saved === 'dark') return saved;
        return 'light';
    }

    function apply(theme) {
        const next = theme === 'dark' ? 'dark' : 'light';
        root.setAttribute('data-theme', next);
        localStorage.setItem(STORAGE_KEY, next);
        document.querySelectorAll('[data-theme-label]').forEach((el) => {
            el.textContent = next === 'light' ? '浅色' : '深色';
        });
        document.querySelectorAll('.theme-toggle .icon-sun').forEach((el) => {
            el.hidden = next !== 'dark';
        });
        document.querySelectorAll('.theme-toggle .icon-moon').forEach((el) => {
            el.hidden = next !== 'light';
        });
    }

    function toggle() {
        const current = root.getAttribute('data-theme') || getPreferred();
        apply(current === 'light' ? 'dark' : 'light');
    }

    apply(getPreferred());

    document.addEventListener('click', (event) => {
        const btn = event.target.closest('.theme-toggle');
        if (!btn) return;
        event.preventDefault();
        toggle();
    });

    window.AINewsTheme = { apply, getPreferred, toggle, STORAGE_KEY };
})();
