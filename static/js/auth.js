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

    function showStartupLoading(initialMessage) {
        const overlay = $('startup-loading');
        if (!overlay) return;
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
            // Rust `auth_start_app` starts the backend, waits for health, and navigates.
            await invoke('auth_start_app');
        } catch (e) {
            appEnterInProgress = false;
            hideStartupLoading();
            setMsg($('phone-msg'), String(e), 'error');
            throw e;
        }
    }

    async function refreshAuthUi() {
        const status = await invoke('auth_get_status');
        if (status.authorized) {
            await enterApp();
            return true;
        }
        return false;
    }

    async function waitForBootstrap() {
        showStartupLoading('正在检查登录状态…');
        $('auth-forms').hidden = true;
        for (let i = 0; i < 60; i += 1) {
            const done = await invoke('auth_bootstrap_completed');
            if (done) break;
            await new Promise((r) => setTimeout(r, 200));
        }
        if (await refreshAuthUi()) return;
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
            refreshAuthUi().catch(() => {});
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindEvents();
        waitForBootstrap().catch((err) => {
            hideStartupLoading();
            $('auth-forms').hidden = false;
            setMsg($('phone-msg'), String(err), 'error');
        });
    });
})();
