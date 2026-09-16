/**
 * Cross-page pipeline stepper — syncs discover → topic → video → publish → review.
 */
(function () {
    const STORAGE_KEY = 'ainews-pipeline-step';

    const PIPELINE_STEPS = [
        { id: 1, label: '发现内容', paths: ['/hot-radar', '/scrape'] },
        { id: 2, label: '选题评分', paths: ['/ingestion-library'] },
        { id: 3, label: '生成成片', paths: ['/video-maker', '/github-video-maker', '/digital-human', '/video-editor3'] },
        { id: 4, label: '审核发布', paths: ['/publish-center', '/publish-queue', '/candidate-pool'] },
        { id: 5, label: '复盘数据', paths: ['/publish-metrics'] },
    ];

    function normalizePath(pathname) {
        const trimmed = (pathname || '/').replace(/\/+$/, '') || '/';
        if (trimmed === '/index.html') return '/';
        return trimmed;
    }

    function stepForPath(pathname) {
        const current = normalizePath(pathname);
        if (current === '/') return 1;
        const found = PIPELINE_STEPS.find((step) =>
            step.paths.some((p) => current === p || current.startsWith(p + '/')),
        );
        return found ? found.id : null;
    }

    function getStoredStep() {
        const raw = localStorage.getItem(STORAGE_KEY);
        const n = Number(raw);
        return Number.isFinite(n) && n >= 1 && n <= 5 ? n : null;
    }

    function setActiveStep(stepId) {
        if (!stepId || stepId < 1 || stepId > 5) return;
        localStorage.setItem(STORAGE_KEY, String(stepId));
    }

    function syncFromPath(pathname) {
        const detected = stepForPath(pathname || window.location.pathname);
        const stored = getStoredStep();
        const active = detected || stored || 1;
        if (detected) setActiveStep(detected);
        return active;
    }

    function renderBar(host, activeStep) {
        if (!host) return;
        const steps = PIPELINE_STEPS.map((step) => {
            let cls = 'pipeline-bar-step';
            if (step.id < activeStep) cls += ' is-done';
            else if (step.id === activeStep) cls += ' is-active';
            const href = step.paths[0] || '/';
            return `
                <a href="${href}" class="${cls}" data-step="${step.id}">
                    <span class="pipeline-bar-dot">${step.id}</span>
                    <span class="pipeline-bar-label">${step.label}</span>
                </a>`;
        }).join('');
        host.innerHTML = `<nav class="pipeline-bar" aria-label="内容管线进度">${steps}</nav>`;
    }

    function mount(hostId) {
        const host = document.getElementById(hostId || 'pipeline-bar-root');
        if (!host) return;
        const active = syncFromPath(window.location.pathname);
        renderBar(host, active);
    }

    window.AINewsPipeline = {
        PIPELINE_STEPS,
        stepForPath,
        getStoredStep,
        setActiveStep,
        syncFromPath,
        mount,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => mount());
    } else {
        mount();
    }
})();
