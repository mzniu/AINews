(function () {
    document.addEventListener('DOMContentLoaded', function () {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.setAttribute('aria-label', '回到顶部');
        btn.textContent = '↑';
        btn.style.cssText = [
            'position: fixed',
            'right: 20px',
            'bottom: 20px',
            'width: 48px',
            'height: 48px',
            'border-radius: 50%',
            'border: none',
            'background: var(--brand-grad, linear-gradient(135deg, #667eea 0%, #764ba2 100%))',
            'color: #fff',
            'font-size: 22px',
            'font-weight: bold',
            'line-height: 1',
            'cursor: pointer',
            'box-shadow: var(--shadow-md, 0 4px 12px rgba(0,0,0,0.2))',
            'z-index: 9999',
            'opacity: 0',
            'visibility: hidden',
            'transition: opacity 0.25s ease, visibility 0.25s ease, transform 0.15s ease, filter 0.15s ease',
            'display: flex',
            'align-items: center',
            'justify-content: center'
        ].join(';');

        btn.addEventListener('mouseenter', function () {
            btn.style.filter = 'brightness(1.1)';
        });
        btn.addEventListener('mouseleave', function () {
            btn.style.filter = '';
        });
        btn.addEventListener('click', function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        document.body.appendChild(btn);

        function updateVisibility() {
            if (window.scrollY > 300) {
                btn.style.opacity = '1';
                btn.style.visibility = 'visible';
            } else {
                btn.style.opacity = '0';
                btn.style.visibility = 'hidden';
            }
        }
        window.addEventListener('scroll', updateVisibility, { passive: true });
        updateVisibility();
    });
})();
