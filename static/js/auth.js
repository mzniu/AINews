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

    async function enterApp() {
        setMsg($('phone-msg'), '正在启动应用…', null);
        const url = await invoke('auth_start_app');
        if (url) {
            window.location.href = url;
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
        $('boot-wait').hidden = false;
        $('auth-forms').hidden = true;
        for (let i = 0; i < 60; i += 1) {
            const done = await invoke('auth_bootstrap_completed');
            if (done) break;
            await new Promise((r) => setTimeout(r, 200));
        }
        $('boot-wait').hidden = true;
        $('auth-forms').hidden = false;
        if (await refreshAuthUi()) return;
        await loadRememberedEmails();
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
                purpose: 'login',
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

    async function phoneLogin() {
        const phone = $('phone').value.trim();
        const code = $('phone-code').value.trim();
        const msgEl = $('phone-msg');
        const err = validatePhone(phone);
        if (err) {
            setMsg(msgEl, err, 'error');
            return;
        }
        if (code.length !== 6) {
            setMsg(msgEl, '验证码应为 6 位', 'error');
            return;
        }
        setMsg(msgEl, '正在登录…', null);
        $('btn-phone-login').disabled = true;
        try {
            const status = await invoke('auth_phone_login', { phone, code });
            if (status.authorized) {
                await enterApp();
            } else {
                setMsg(msgEl, status.message || '登录未成功', 'error');
            }
        } catch (e) {
            setMsg(msgEl, String(e), 'error');
        } finally {
            $('btn-phone-login').disabled = false;
        }
    }

    async function emailLogin() {
        const email = $('email').value.trim();
        const password = $('password').value;
        const msgEl = $('email-msg');
        if (!email) {
            setMsg(msgEl, '请输入邮箱', 'error');
            return;
        }
        if (!password) {
            setMsg(msgEl, '请输入密码', 'error');
            return;
        }
        setMsg(msgEl, '正在登录…', null);
        $('btn-email-login').disabled = true;
        try {
            const status = await invoke('auth_login', { email, password });
            if ($('remember-password').checked) {
                try {
                    await invoke('auth_save_remembered_password', { email, password });
                } catch (_) {
                    /* non-blocking */
                }
            }
            if (status.authorized) {
                await enterApp();
            } else {
                setMsg(msgEl, status.message || '登录未成功', 'error');
            }
        } catch (e) {
            setMsg(msgEl, String(e), 'error');
        } finally {
            $('btn-email-login').disabled = false;
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
        $('btn-phone-login').addEventListener('click', phoneLogin);
        $('btn-email-login').addEventListener('click', emailLogin);
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
            refreshAuthUi().catch(() => {});
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindEvents();
        waitForBootstrap().catch((err) => {
            $('boot-wait').hidden = true;
            $('auth-forms').hidden = false;
            setMsg($('phone-msg'), String(err), 'error');
        });
    });
})();
