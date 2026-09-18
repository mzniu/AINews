(function () {
    const invoke = (cmd, args) => {
        const tauri = window.__TAURI__;
        if (!tauri?.core?.invoke) {
            throw new Error('请在 AINews 桌面客户端中打开此页面');
        }
        return tauri.core.invoke(cmd, args);
    };

    const $ = (id) => document.getElementById(id);

    let phoneCooldownTimer = null;
    let phoneCooldownSeconds = 0;
    let pendingCaptcha = null;
    let phoneMode = 'login';
    let emailMode = 'login';
    let appEnterInProgress = false;
    let startupStatusTimer = null;
    let startupStatusIndex = 0;

    const MIN_PASSWORD_LENGTH = 8;
    const STARTUP_STATUS_MESSAGES = [
        '正在启动本地服务…',
        '正在检查服务连接…',
        '即将进入主界面…',
    ];

    function setMsg(el, text, kind) {
        if (!el) return;
        el.textContent = text || '';
        el.classList.remove('error', 'ok');
        if (kind) el.classList.add(kind);
    }

    function validatePhone(phone) {
        const cleaned = phone.trim().replace(/[\s-]/g, '');
        if (cleaned.length !== 11) return '请输入 11 位手机号';
        if (!/^\d+$/.test(cleaned)) return '手机号只能包含数字';
        return null;
    }

    function validatePassword(password) {
        if (!password) return '请输入密码';
        if (password.length < MIN_PASSWORD_LENGTH) {
            return `密码至少需要 ${MIN_PASSWORD_LENGTH} 个字符`;
        }
        return null;
    }

    function setSendCodeButton(btn, seconds) {
        btn.disabled = seconds > 0;
        btn.textContent = seconds > 0 ? `${seconds}s 后重发` : '发送验证码';
    }

    function startPhoneCooldown(btn) {
        phoneCooldownSeconds = 60;
        setSendCodeButton(btn, phoneCooldownSeconds);
        phoneCooldownTimer = setInterval(() => {
            phoneCooldownSeconds -= 1;
            setSendCodeButton(btn, phoneCooldownSeconds);
            if (phoneCooldownSeconds <= 0 && phoneCooldownTimer) {
                clearInterval(phoneCooldownTimer);
                phoneCooldownTimer = null;
            }
        }, 1000);
    }

    function setTab(tab) {
        document.querySelectorAll('.tab').forEach((el) => {
            el.classList.toggle('is-active', el.dataset.tab === tab);
        });
        $('panel-phone-login').hidden = tab !== 'phone-login';
        $('panel-email-login').hidden = tab !== 'email-login';
    }

    function updatePhoneModeUi() {
        const isRegister = phoneMode === 'register';
        $('btn-phone-submit').textContent = isRegister ? '注册' : '登录';
        $('phone-mode-hint').textContent = isRegister ? '已有账号？' : '没有账号？';
        $('phone-mode-toggle').textContent = isRegister ? '登录' : '注册';
        setMsg($('phone-msg'), '', null);
    }

    function updateEmailModeUi() {
        const isRegister = emailMode === 'register';
        $('btn-email-submit').textContent = isRegister ? '注册' : '登录';
        $('email-mode-hint').textContent = isRegister ? '已有账号？' : '没有账号？';
        $('email-mode-toggle').textContent = isRegister ? '登录' : '注册';
        $('email-register-fields').hidden = !isRegister;
        document.querySelectorAll('.login-only').forEach((el) => {
            el.hidden = isRegister;
        });
        $('password').autocomplete = isRegister ? 'new-password' : 'current-password';
        setMsg($('email-msg'), '', null);
    }

    function togglePhoneMode() {
        phoneMode = phoneMode === 'login' ? 'register' : 'login';
        updatePhoneModeUi();
    }

    function toggleEmailMode() {
        emailMode = emailMode === 'login' ? 'register' : 'login';
        updateEmailModeUi();
    }

    function updateStartupStatus(text) {
        const el = $('startup-status');
        if (el) el.textContent = text;
    }

    function setStartupProgress(percent, stepLabel) {
        const wrap = $('startup-progress');
        const bar = $('startup-progress-bar');
        const stepEl = $('startup-step-label');
        if (wrap) {
            wrap.hidden = false;
            wrap.setAttribute('aria-hidden', 'false');
        }
        if (bar) bar.style.width = `${Math.min(100, Math.max(0, percent))}%`;
        if (stepEl) {
            stepEl.hidden = !stepLabel;
            stepEl.textContent = stepLabel || '';
        }
        if (startupStatusTimer) {
            clearInterval(startupStatusTimer);
            startupStatusTimer = null;
        }
    }

    function bindSetupProgressListener() {
        const tauri = window.__TAURI__;
        if (!tauri?.event?.listen || window.__ainewsSetupListener) return;
        window.__ainewsSetupListener = true;
        tauri.event.listen('ainews:setup-progress', (ev) => {
            const p = ev.payload || {};
            if (p.label) updateStartupStatus(p.label);
            if (typeof p.percent === 'number') setStartupProgress(p.percent, p.step || '');
        });
    }

    async function ensureRuntimeSetup() {
        bindSetupProgressListener();
        const status = await invoke('runtime_setup_status');
        if (status.ready) return;
        showStartupLoading('正在初始化运行环境…');
        setStartupProgress(5, '准备下载');
        await invoke('runtime_setup_run');
        setStartupProgress(100, '完成');
    }

    function setHidden(id, hidden) {
        const el = $(id);
        if (el) el.hidden = hidden;
    }

    function clearStartupError() {
        setHidden('startup-error', true);
        const detail = $('startup-error-detail');
        if (detail) detail.textContent = '';
        const summary = $('startup-error-summary');
        if (summary) summary.textContent = '';
        $('startup-body')?.classList.remove('is-error');
        setHidden('startup-status', false);
        setHidden('startup-hint', false);
    }

    function startupFriendlySummary(err) {
        const text = String(err || '');
        if (/No Python at/i.test(text) || /内置 Python 环境仍指向/i.test(text) || /内置 Python 无法启动/i.test(text)) {
            return '内置 Python 运行环境不完整或安装包未正确打包。请重新下载并安装最新版 AINews；若仍失败，请复制下方诊断信息发给开发人员。';
        }
        if (/已退出|进程已退出|exited/i.test(text)) {
            return '本地服务启动后异常退出。请查看下方日志摘要，或复制诊断信息联系支持。';
        }
        if (/超时|timeout/i.test(text)) {
            return '等待本地服务就绪超时。请检查防火墙、端口占用，或稍后重试。';
        }
        return '本地服务未能正常启动。请重试；若反复失败，请复制诊断信息发给开发人员。';
    }

    function buildDiagnosticsReport(err, diag) {
        const lines = [
            '=== AINews 启动诊断 ===',
            `时间: ${new Date().toISOString()}`,
            `错误: ${String(err || diag?.error || '未知')}`,
        ];
        if (diag?.installDir) lines.push(`安装目录: ${diag.installDir}`);
        if (diag?.pythonPath) lines.push(`Python: ${diag.pythonPath}`);
        if (diag?.appDir) lines.push(`应用目录: ${diag.appDir}`);
        if (diag?.dataDir) lines.push(`数据目录: ${diag.dataDir}`);
        if (diag?.port) lines.push(`端口: ${diag.port}`);
        if (diag?.logPath) lines.push(`日志文件: ${diag.logPath}`);
        if (diag?.logTail) {
            lines.push('', '--- 日志末尾 ---', diag.logTail);
        }
        return lines.join('\n');
    }

    async function loadStartupDiagnostics() {
        try {
            return await invoke('auth_get_startup_diagnostics');
        } catch (_) {
            return null;
        }
    }

    let lastDiagnosticsReport = '';

    function showStartupError(title, summary, detail) {
        const overlay = $('startup-loading');
        if (!overlay) return;
        overlay.hidden = false;
        $('auth-card')?.setAttribute('aria-hidden', 'true');
        $('startup-body')?.classList.add('is-error');
        setHidden('startup-status', true);
        setHidden('startup-hint', true);
        if (startupStatusTimer) {
            clearInterval(startupStatusTimer);
            startupStatusTimer = null;
        }
        const panel = $('startup-error');
        const titleEl = $('startup-error-title');
        const summaryEl = $('startup-error-summary');
        const detailEl = $('startup-error-detail');
        if (titleEl) titleEl.textContent = title || '启动失败';
        if (summaryEl) summaryEl.textContent = summary || '';
        if (detailEl) detailEl.textContent = detail || '';
        if (panel) panel.hidden = false;
    }

    async function copyStartupDiagnostics() {
        const text = lastDiagnosticsReport || $('startup-error-detail')?.textContent || '';
        if (!text) return;
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.setAttribute('readonly', '');
                ta.style.position = 'fixed';
                ta.style.left = '-9999px';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
            }
            const btn = $('btn-startup-copy');
            if (btn) {
                const prev = btn.textContent;
                btn.textContent = '已复制';
                setTimeout(() => { btn.textContent = prev; }, 2000);
            }
        } catch (_) {
            window.prompt('请手动复制以下诊断信息：', text);
        }
    }

    async function showStartupFailure(err, title) {
        appEnterInProgress = false;
        const diag = await loadStartupDiagnostics();
        const summary = startupFriendlySummary(err || diag?.error);
        lastDiagnosticsReport = buildDiagnosticsReport(err, diag);
        showStartupError(title || '无法进入主界面', summary, lastDiagnosticsReport);
        setMsg($('phone-msg'), summary, 'error');
        setMsg($('email-msg'), summary, 'error');
        setMsg($('offline-msg'), summary, 'error');
    }

    function showStartupLoading(initialMessage) {
        const overlay = $('startup-loading');
        if (!overlay) return;
        clearStartupError();
        overlay.hidden = false;
        $('auth-card')?.setAttribute('aria-hidden', 'true');
        updateStartupStatus(initialMessage || STARTUP_STATUS_MESSAGES[0]);
        startupStatusIndex = 0;
        if (startupStatusTimer) clearInterval(startupStatusTimer);
        startupStatusTimer = setInterval(() => {
            startupStatusIndex = (startupStatusIndex + 1) % STARTUP_STATUS_MESSAGES.length;
            updateStartupStatus(STARTUP_STATUS_MESSAGES[startupStatusIndex]);
        }, 2800);
    }

    function hideStartupLoading() {
        const overlay = $('startup-loading');
        if (overlay) overlay.hidden = true;
        $('auth-card')?.removeAttribute('aria-hidden');
        clearStartupError();
        if (startupStatusTimer) {
            clearInterval(startupStatusTimer);
            startupStatusTimer = null;
        }
    }

    async function enterApp() {
        if (appEnterInProgress) return;
        appEnterInProgress = true;
        showStartupLoading('正在启动应用…');
        try {
            await ensureRuntimeSetup();
            // Rust `auth_start_app` starts the backend, waits for health, and navigates.
            await invoke('auth_start_app');
        } catch (e) {
            await showStartupFailure(e, '启动本地服务失败');
            throw e;
        }
    }

    async function refreshAuthUi() {
        const status = await invoke('auth_get_status');
        if (status.authorized) {
            await enterApp();
            return true;
        }
        if (status.message) {
            await showStartupFailure(status.message, '登录状态无效');
        }
        return false;
    }

    async function showPersistedStartupError() {
        const diag = await loadStartupDiagnostics();
        if (!diag?.error) return false;
        await showStartupFailure(diag.error, '上次启动失败');
        return true;
    }

    async function waitForBootstrap() {
        bindSetupProgressListener();
        showStartupLoading('正在检查登录状态…');
        $('auth-forms').hidden = true;
        for (let i = 0; i < 60; i += 1) {
            const done = await invoke('auth_bootstrap_completed');
            if (done) break;
            await new Promise((r) => setTimeout(r, 200));
        }
        if (await refreshAuthUi()) return;
        if (await showPersistedStartupError()) return;
        hideStartupLoading();
        $('auth-forms').hidden = false;
        await loadRememberedEmails();
        updatePhoneModeUi();
        updateEmailModeUi();
    }

    async function loadRememberedEmails() {
        try {
            const emails = await invoke('auth_list_remembered_emails');
            const list = $('remembered-emails');
            if (!list) return;
            list.innerHTML = (emails || []).map((e) => `<option value="${e}"></option>`).join('');
        } catch (_) {
            /* ignore */
        }
    }

    async function maybeLoadRememberedPassword() {
        if (emailMode !== 'login') return;
        const email = $('email').value.trim();
        if (!email) return;
        try {
            const password = await invoke('auth_load_remembered_password', { email });
            if (password) $('password').value = password;
        } catch (_) {
            /* ignore */
        }
    }

    async function promptCaptcha() {
        const modal = $('captcha-modal');
        const svgHost = $('captcha-svg');
        const answerInput = $('captcha-answer');
        answerInput.value = '';
        let captcha;
        try {
            captcha = await invoke('auth_get_captcha');
        } catch (err) {
            return null;
        }
        svgHost.innerHTML = captcha.svg_data;
        modal.hidden = false;
        return new Promise((resolve) => {
            pendingCaptcha = { captcha, resolve };
        });
    }

    function closeCaptcha(result) {
        $('captcha-modal').hidden = true;
        if (pendingCaptcha) {
            pendingCaptcha.resolve(result);
            pendingCaptcha = null;
        }
    }

    async function sendPhoneCode() {
        const phone = $('phone').value.trim();
        const btn = $('btn-send-code');
        const msgEl = $('phone-msg');
        const err = validatePhone(phone);
        if (err) {
            setMsg(msgEl, err, 'error');
            return;
        }
        setMsg(msgEl, '正在发送验证码…', null);
        btn.disabled = true;
        try {
            let captchaId = null;
            let captchaCode = null;
            const captchaResult = await promptCaptcha();
            if (captchaResult === false) {
                setMsg(msgEl, '已取消发送', null);
                return;
            }
            if (captchaResult) {
                captchaId = captchaResult.captcha_id;
                captchaCode = captchaResult.code;
            }
            const message = await invoke('auth_send_phone_code', {
                phone,
                purpose: phoneMode === 'register' ? 'register' : 'login',
                captchaId,
                captchaCode,
            });
            setMsg(msgEl, message || '验证码已发送', 'ok');
            startPhoneCooldown(btn);
        } catch (e) {
            setMsg(msgEl, String(e), 'error');
            btn.disabled = false;
        }
    }

    async function phoneSubmit() {
        const phone = $('phone').value.trim();
        const code = $('phone-code').value.trim();
        const msgEl = $('phone-msg');
        const btn = $('btn-phone-submit');
        const err = validatePhone(phone);
        if (err) {
            setMsg(msgEl, err, 'error');
            return;
        }
        if (code.length !== 6) {
            setMsg(msgEl, '验证码应为 6 位', 'error');
            return;
        }
        const isRegister = phoneMode === 'register';
        setMsg(msgEl, isRegister ? '正在注册…' : '正在登录…', null);
        btn.disabled = true;
        try {
            const status = await invoke(
                isRegister ? 'auth_phone_register' : 'auth_phone_login',
                { phone, code },
            );
            if (status.authorized) {
                await enterApp();
            } else {
                setMsg(msgEl, status.message || (isRegister ? '注册未成功' : '登录未成功'), 'error');
            }
        } catch (e) {
            setMsg(msgEl, String(e), 'error');
        } finally {
            btn.disabled = false;
        }
    }

    async function emailSubmit() {
        const email = $('email').value.trim();
        const password = $('password').value;
        const msgEl = $('email-msg');
        const btn = $('btn-email-submit');
        const isRegister = emailMode === 'register';

        if (!email) {
            setMsg(msgEl, '请输入邮箱', 'error');
            return;
        }
        const passwordErr = validatePassword(password);
        if (passwordErr) {
            setMsg(msgEl, passwordErr, 'error');
            return;
        }
        if (isRegister) {
            const confirm = $('password-confirm').value;
            if (password !== confirm) {
                setMsg(msgEl, '两次输入的密码不一致', 'error');
                return;
            }
        }

        setMsg(msgEl, isRegister ? '正在注册…' : '正在登录…', null);
        btn.disabled = true;
        try {
            const status = await invoke(
                isRegister ? 'auth_register' : 'auth_login',
                { email, password },
            );
            if (!isRegister && $('remember-password').checked) {
                try {
                    await invoke('auth_save_remembered_password', { email, password });
                } catch (_) {
                    /* non-blocking */
                }
            }
            if (status.authorized) {
                await enterApp();
            } else {
                setMsg(msgEl, status.message || (isRegister ? '注册未成功' : '登录未成功'), 'error');
            }
        } catch (e) {
            setMsg(msgEl, String(e), 'error');
        } finally {
            btn.disabled = false;
        }
    }

    async function offlineRedeem() {
        const code = $('offline-code').value.trim();
        const msgEl = $('offline-msg');
        if (!code) {
            setMsg(msgEl, '请输入授权码', 'error');
            return;
        }
        setMsg(msgEl, '正在验证…', null);
        $('btn-offline-redeem').disabled = true;
        try {
            const status = await invoke('auth_redeem_offline_code', { code });
            if (status.authorized) {
                await enterApp();
            } else {
                setMsg(msgEl, status.message || '授权未成功', 'error');
            }
        } catch (e) {
            setMsg(msgEl, String(e), 'error');
        } finally {
            $('btn-offline-redeem').disabled = false;
        }
    }

    function bindEvents() {
        document.querySelectorAll('.tab').forEach((tab) => {
            tab.addEventListener('click', () => setTab(tab.dataset.tab));
        });
        $('btn-send-code').addEventListener('click', sendPhoneCode);
        $('btn-phone-submit').addEventListener('click', phoneSubmit);
        $('btn-email-submit').addEventListener('click', emailSubmit);
        $('phone-mode-toggle').addEventListener('click', togglePhoneMode);
        $('email-mode-toggle').addEventListener('click', toggleEmailMode);
        $('btn-offline-redeem').addEventListener('click', offlineRedeem);
        $('email').addEventListener('change', maybeLoadRememberedPassword);
        $('email').addEventListener('blur', maybeLoadRememberedPassword);
        $('captcha-cancel').addEventListener('click', () => closeCaptcha(false));
        $('captcha-confirm').addEventListener('click', () => {
            if (!pendingCaptcha) return;
            const code = $('captcha-answer').value.trim();
            if (!code) return;
            closeCaptcha({ captcha_id: pendingCaptcha.captcha.captcha_id, code });
        });
        const tauri = window.__TAURI__;
        tauri?.event?.listen?.('auth://status-changed', () => {
            if (appEnterInProgress) return;
            refreshAuthUi().catch((err) => {
                showStartupFailure(err, '登录状态已变化').catch(() => {});
            });
        });
        tauri?.event?.listen?.('ainews:startup-failed', (event) => {
            if (appEnterInProgress) return;
            const payload = event?.payload ?? '本地服务启动失败';
            showStartupFailure(payload, '本地服务启动失败').catch(() => {});
        });
        $('btn-startup-copy')?.addEventListener('click', () => {
            copyStartupDiagnostics().catch(() => {});
        });
        $('btn-startup-retry')?.addEventListener('click', () => {
            clearStartupError();
            enterApp().catch(() => {});
        });
        $('btn-startup-back')?.addEventListener('click', () => {
            appEnterInProgress = false;
            hideStartupLoading();
            $('auth-forms').hidden = false;
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindEvents();
        waitForBootstrap().catch((err) => {
            showStartupFailure(err, '初始化失败').catch(() => {
                hideStartupLoading();
                $('auth-forms').hidden = false;
                setMsg($('phone-msg'), String(err), 'error');
            });
        });
    });
})();
