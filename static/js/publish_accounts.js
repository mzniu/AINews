/** 账号绑定：平台账号扫码登录与管理 */
(function () {
    let qrPollTimer = null;
    let qrSessionId = null;
    let platformCatalog = [];

    function esc(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/"/g, '&quot;');
    }

    function statusLabel(status) {
        const map = { active: '有效', expired: '已过期', unknown: '未知' };
        return map[status] || status;
    }

    function statusClass(status) {
        if (status === 'active') return 'status-active';
        if (status === 'expired') return 'status-expired';
        return 'status-unknown';
    }

    function platformName(platformId) {
        const p = platformCatalog.find((x) => x.id === platformId);
        return (p && p.display_name) || platformId;
    }

    async function checkHealth() {
        const resp = await fetch('/api/publishing/health');
        const data = await resp.json();
        const banner = document.getElementById('workerBanner');
        if (!banner) return;
        banner.hidden = !!data.worker_reachable;
        if (!data.worker_reachable && data.worker_mode === 'embedded') {
            banner.textContent = '⚠️ 内嵌发布 worker 未就绪，请重启 web_server 或查看日志。';
        }
    }

    async function loadPlatformMenu() {
        const resp = await fetch('/api/publishing/platforms');
        const data = await resp.json();
        platformCatalog = data.platforms || [];
        const enabled = platformCatalog.filter((p) => p.enabled && p.capabilities?.account_login);
        const sel = document.getElementById('addPlatformSelect');
        const addBtn = document.getElementById('addAccountBtn');
        if (!sel || !addBtn) return;
        if (!enabled.length) {
            sel.innerHTML = '<option value="">暂无可用平台</option>';
            addBtn.disabled = true;
            return;
        }
        addBtn.disabled = false;
        sel.innerHTML = enabled.map((p) => `<option value="${p.id}">${esc(p.display_name)}</option>`).join('');
    }

    function renderAccountsGrouped(accounts) {
        const grid = document.getElementById('accountsGrid');
        if (!grid) return;
        if (!accounts.length) {
            grid.innerHTML = '<p class="hint">暂无账号，选择平台后点击「添加账号」。</p>';
            return;
        }
        const sorted = accounts.slice().sort((a, b) => {
            const platformCmp = platformName(a.platform).localeCompare(platformName(b.platform), 'zh');
            if (platformCmp !== 0) return platformCmp;
            return (a.nickname || '').localeCompare(b.nickname || '', 'zh');
        });
        grid.innerHTML = `<div class="accounts-flex">${sorted.map((a) => {
            const badge = a.can_publish
                ? '<span class="badge badge-publish">可发布</span>'
                : '<span class="badge badge-account">仅账号</span>';
            return `
                <div class="account-card" id="account-card-${a.id}">
                    <div><strong>${esc(a.nickname || platformName(a.platform))}</strong>${badge}</div>
                    <div class="account-platform">${esc(a.platform_display_name || platformName(a.platform))}</div>
                    <div class="status-line" data-account-id="${a.id}">
                        状态：<span class="${statusClass(a.status)}">${statusLabel(a.status)}</span>
                    </div>
                    <div class="account-actions">
                        <button type="button" class="btn-secondary btn" data-action="check" data-id="${a.id}">检查状态</button>
                        <button type="button" class="btn-secondary btn" data-action="refresh" data-id="${a.id}" data-platform="${esc(a.platform)}">重新登录</button>
                        <button type="button" class="btn-secondary btn" data-action="delete" data-id="${a.id}">删除</button>
                    </div>
                </div>`;
        }).join('')}</div>`;
    }

    async function loadAccounts() {
        const resp = await fetch('/api/publishing/accounts');
        const data = await resp.json();
        renderAccountsGrouped(data.accounts || []);
    }

    async function checkAccountStatus(id) {
        const line = document.querySelector(`.status-line[data-account-id="${id}"]`);
        if (line) line.innerHTML = '状态：<span class="status-checking">检查中…</span>';
        try {
            const resp = await fetch(`/api/publishing/accounts/${id}/check-status`, { method: 'POST' });
            const data = await resp.json();
            if (!resp.ok) {
                alert('检查失败: ' + (data.detail || resp.statusText));
                loadAccounts();
                return;
            }
            if (line) {
                line.innerHTML = `状态：<span class="${statusClass(data.status)}">${statusLabel(data.status)}</span>`;
            }
            alert(data.message || '检查完成');
            loadAccounts();
        } catch (err) {
            alert('检查失败: ' + err.message);
            loadAccounts();
        }
    }

    async function startQr(platform, purpose, accountId) {
        const displayName = platformName(platform);
        document.getElementById('qrModalTitle').textContent = `扫码登录${displayName}`;
        const resp = await fetch('/api/publishing/accounts/qr-start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform, purpose, account_id: accountId }),
        });
        const data = await resp.json();
        qrSessionId = data.session_id;
        document.getElementById('qrModal').style.display = 'flex';
        document.getElementById('qrStatusText').textContent = '等待 worker 生成二维码…';
        if (qrPollTimer) clearInterval(qrPollTimer);
        qrPollTimer = setInterval(pollQr, 2000);
        pollQr();
    }

    async function pollQr() {
        if (!qrSessionId) return;
        const resp = await fetch(`/api/publishing/accounts/qr-status/${qrSessionId}`);
        const data = await resp.json();
        const statusMap = {
            waiting_scan: '请使用 App 扫码',
            scanned: '已扫码，请在手机确认',
            confirmed: '登录成功',
            expired: '已过期',
            failed: '失败',
        };
        let statusText = statusMap[data.status] || data.status;
        if (data.status === 'failed' && data.error_message) {
            statusText = `${statusText}：${data.error_message}`;
        }
        document.getElementById('qrStatusText').textContent = statusText;
        if (data.qr_image_url) {
            document.getElementById('qrImage').src = data.qr_image_url + '?t=' + Date.now();
        }
        if (['confirmed', 'expired', 'failed'].includes(data.status)) {
            clearInterval(qrPollTimer);
            if (data.status === 'confirmed') {
                setTimeout(() => {
                    document.getElementById('qrModal').style.display = 'none';
                    loadAccounts();
                }, 800);
            }
        }
    }

    async function deleteAccount(id) {
        if (!confirm('确定删除该账号？')) return;
        await fetch(`/api/publishing/accounts/${id}`, { method: 'DELETE' });
        loadAccounts();
    }

    function bindEvents() {
        document.getElementById('addAccountBtn')?.addEventListener('click', () => {
            const platform = document.getElementById('addPlatformSelect')?.value;
            if (!platform) return;
            startQr(platform, 'create');
        });
        document.getElementById('qrCloseBtn')?.addEventListener('click', () => {
            if (qrPollTimer) clearInterval(qrPollTimer);
            document.getElementById('qrModal').style.display = 'none';
        });
        document.getElementById('accountsGrid')?.addEventListener('click', (event) => {
            const btn = event.target.closest('button[data-action]');
            if (!btn) return;
            const id = btn.dataset.id;
            if (btn.dataset.action === 'check') checkAccountStatus(id);
            if (btn.dataset.action === 'refresh') startQr(btn.dataset.platform, 'refresh', id);
            if (btn.dataset.action === 'delete') deleteAccount(id);
        });
    }

    function init() {
        bindEvents();
        checkHealth();
        loadPlatformMenu();
        loadAccounts();
        setInterval(checkHealth, 15000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
