(function () {
    document.querySelectorAll('.settings-tab').forEach((btn) => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll('.settings-tab').forEach((b) => b.classList.toggle('active', b === btn));
            document.querySelectorAll('.settings-panel').forEach((panel) => {
                panel.hidden = panel.id !== `panel-${tab}`;
            });
            if (tab === 'ingestion' && window.loadIngestionSettings) {
                window.loadIngestionSettings();
            }
        });
    });

    const hash = (location.hash || '').replace('#', '');
    if (hash === 'ingestion') {
        document.querySelector('.settings-tab[data-tab="ingestion"]')?.click();
    }
})();
