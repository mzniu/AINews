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
        document.querySelectorAll('.theme-toggle-btn[data-theme-set]').forEach((btn) => {
            const isActive = btn.getAttribute('data-theme-set') === next;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    }

    function toggle() {
        const current = root.getAttribute('data-theme') || getPreferred();
        apply(current === 'light' ? 'dark' : 'light');
    }

    apply(getPreferred());

    document.addEventListener('click', (event) => {
        const setBtn = event.target.closest('.theme-toggle-btn[data-theme-set]');
        if (setBtn) {
            event.preventDefault();
            apply(setBtn.getAttribute('data-theme-set'));
        }
    });

    window.AINewsTheme = { apply, getPreferred, toggle, STORAGE_KEY };
})();
