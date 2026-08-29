(function () {
    document.querySelectorAll('.settings-tab').forEach((btn) => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll('.settings-tab').forEach((b) => b.classList.toggle('active', b === btn));
            document.querySelectorAll('.settings-panel').forEach((panel) => {
                panel.hidden = panel.id !== `panel-${tab}`;
            });
            if (tab === 'ingestion') {
                window.loadIngestionSettings?.();
                window.loadMediaPipelineSettings?.();
            }
            if (tab === 'hot-radar') {
                window.loadHotRadarSettings?.();
            }
            if (tab === 'scoring') {
                window.loadScoringSettings?.();
            }
            if (tab === 'image-scoring') {
                window.loadImageScoringSettings?.();
            }
            if (tab === 'render-templates') {
                window.loadRenderTemplateSettings?.();
            }
            if (tab === 'title-prompts') {
                window.loadTitlePromptSettings?.();
            }
            if (tab === 'usage') {
                window.loadTokenUsage?.();
            }
        });
    });

    const hash = (location.hash || '').replace('#', '');
    if (hash === 'ingestion') {
        document.querySelector('.settings-tab[data-tab="ingestion"]')?.click();
    }
    if (hash === 'scoring') {
        document.querySelector('.settings-tab[data-tab="scoring"]')?.click();
    }
    if (hash === 'image-scoring') {
        document.querySelector('.settings-tab[data-tab="image-scoring"]')?.click();
    }
    if (hash === 'render-templates') {
        document.querySelector('.settings-tab[data-tab="render-templates"]')?.click();
    }
    if (hash === 'title-prompts') {
        document.querySelector('.settings-tab[data-tab="title-prompts"]')?.click();
    }
    if (hash === 'hot-radar') {
        document.querySelector('.settings-tab[data-tab="hot-radar"]')?.click();
    }
    if (hash === 'usage') {
        document.querySelector('.settings-tab[data-tab="usage"]')?.click();
    }
})();
