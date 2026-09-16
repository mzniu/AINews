(function () {
    const TOAST_DURATION_MS = 3000;

    function ensureToastStack() {
        let stack = document.getElementById('app-toast-stack');
        if (stack) return stack;
        stack = document.createElement('div');
        stack.id = 'app-toast-stack';
        stack.className = 'app-toast-stack';
        stack.setAttribute('aria-live', 'polite');
        document.body.appendChild(stack);
        return stack;
    }

    function showToast(message, variant) {
        const stack = ensureToastStack();
        const toast = document.createElement('div');
        const kind = variant || 'info';
        toast.className = `app-toast is-${kind}`;
        toast.setAttribute('role', 'status');
        toast.textContent = String(message ?? '');
        stack.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('is-visible'));
        setTimeout(() => {
            toast.classList.remove('is-visible');
            setTimeout(() => toast.remove(), 220);
        }, TOAST_DURATION_MS);
        return toast;
    }

    function openModal(options) {
        const opts = options || {};
        const overlay = document.createElement('div');
        overlay.className = 'app-modal-overlay';
        overlay.innerHTML = `
            <div class="app-modal" role="dialog" aria-modal="true" aria-labelledby="app-modal-title">
                <div class="app-modal-header">
                    <h2 id="app-modal-title">${opts.title || ''}</h2>
                    <button type="button" class="app-modal-close" aria-label="关闭">&times;</button>
                </div>
                <div class="app-modal-body">${opts.body || ''}</div>
                <div class="app-modal-actions">
                    ${opts.actionsHtml || '<button type="button" class="btn btn-primary" data-action="close">确定</button>'}
                </div>
            </div>`;

        function close() {
            overlay.remove();
            document.removeEventListener('keydown', onKey);
        }

        function onKey(event) {
            if (event.key === 'Escape') close();
        }

        overlay.addEventListener('click', (event) => {
            if (event.target === overlay || event.target.closest('[data-action="close"]')) {
                close();
            }
        });
        document.addEventListener('keydown', onKey);
        document.body.appendChild(overlay);
        return { close, overlay };
    }

    function showBanner(container, options) {
        const opts = options || {};
        const host = typeof container === 'string'
            ? document.querySelector(container)
            : container;
        if (!host) return null;
        const variant = opts.variant || 'info';
        host.innerHTML = '';
        host.className = `app-banner is-${variant}`;
        host.hidden = false;
        host.setAttribute('role', 'status');
        if (opts.html) {
            host.innerHTML = opts.html;
        } else {
            host.textContent = String(opts.message ?? '');
        }
        return host;
    }

    function AppBanner(container, options) {
        return showBanner(container, options);
    }

    window.AppUI = { showToast, openModal, showBanner, AppBanner };
})();
