(function () {
  const STORAGE_KEY = 'ainews-mockup-theme';
  const root = document.documentElement;

  function getPreferred() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
    return 'light';
  }

  function apply(theme) {
    root.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    document.querySelectorAll('[data-theme-label]').forEach((el) => {
      el.textContent = theme === 'light' ? '浅色' : '深色';
    });
    document.querySelectorAll('.theme-toggle .icon-sun').forEach((el) => {
      el.hidden = theme !== 'dark';
    });
    document.querySelectorAll('.theme-toggle .icon-moon').forEach((el) => {
      el.hidden = theme !== 'light';
    });
  }

  apply(getPreferred());

  document.querySelectorAll('.theme-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      apply(next);
    });
  });
})();
