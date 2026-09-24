(function () {

    const $ = (id) => document.getElementById(id);



    function isDesktop() {

        return Boolean(window.__TAURI__?.core?.invoke);

    }



    async function invoke(cmd, args = {}) {

        const fn = window.__TAURI__?.core?.invoke;

        if (!fn) throw new Error('not_desktop');

        return fn(cmd, args);

    }



    function setStatus(text, type = '') {

        const bar = $('videoRendererStatusBar');

        if (!bar) return;

        bar.textContent = text;

        bar.className = 'status-bar' + (type ? ` ${type}` : '');

    }



    const ACTIVE_LABEL = {

        remotion: 'Remotion',

        python: 'Python',

    };



    const REPAIR_HINT = {

        upgrade_required: '应用已升级，需重新安装 Remotion 运行环境。',

        install_incomplete: 'Remotion 安装未完成，请重新配置或允许回退到 Python。',

    };



    const REMOTION_REASON = {

        node_modules_missing: '未检测到 remotion/node_modules',

        upgrade_required: 'package-lock 与已安装版本不一致',

        ok: '就绪',

    };



    let progressListener = null;



    function formatSummary(data) {

        const active = ACTIVE_LABEL[data.active] || data.active || '—';

        let line = `当前实际出片引擎：${active}`;

        if (data.env_override) {

            line += `（环境变量 VIDEO_RENDERER=${data.env_override} 覆盖配置）`;

        }

        if (data.last_render_renderer) {

            line += `；上次出片：${ACTIVE_LABEL[data.last_render_renderer] || data.last_render_renderer}`;

        }

        if (!data.consistent) {

            line += '；配置与运行环境不一致';

        }

        return line;

    }



    function formatDetail(data) {

        const parts = [];

        parts.push(`首选：${data.preferred}；允许 Python 回退：${data.allow_python_fallback ? '是' : '否'}`);

        const rem = data.remotion || {};

        const reason = REMOTION_REASON[rem.reason] || rem.reason || '—';

        parts.push(

            `Remotion：${rem.ready ? '就绪' : '未就绪'}（${reason}）` +

                (rem.upgrade_required ? '，需升级重装' : ''),

        );

        if (data.repair_hint) {

            parts.push(REPAIR_HINT[data.repair_hint] || data.repair_hint);

        }

        if (data.active_note === 'remotion_not_ready' && data.allow_python_fallback) {

            parts.push('已按设置回退到 Python 出片。');

        }

        return parts.join(' ');

    }



    function updateInstallUi(apiData, desktopStatus) {

        const btn = $('videoRendererInstallBtn');

        const block = $('videoRendererInstallBlock');

        if (!btn || !block) return;

        block.hidden = !isDesktop();

        if (!isDesktop()) return;



        const upgrade = Boolean(apiData?.remotion?.upgrade_required || desktopStatus?.upgradeRequired);

        if (upgrade) {

            btn.textContent = '重新安装 Remotion 运行环境';

        } else if (desktopStatus?.ready) {

            btn.textContent = 'Remotion 已安装';

            btn.disabled = true;

            return;

        } else {

            btn.textContent = '下载并配置 Remotion';

        }

        btn.disabled = false;

    }



    function applySettings(data, desktopStatus) {

        const preferred = $('videoRendererPreferred');

        const fallback = $('videoRendererAllowFallback');

        if (preferred && data.preferred) {

            preferred.value = data.preferred;

            preferred.dataset.lastValue = data.preferred;

        }

        if (fallback) {

            fallback.checked = Boolean(data.allow_python_fallback);

            fallback.dataset.lastValue = fallback.checked ? '1' : '0';

        }

        const summary = $('videoRendererSummary');

        if (summary) {

            let text = formatSummary(data);

            if (data.remotion?.upgrade_required) {

                text += ' 【请重新安装 Remotion 运行时】';

                summary.className = 'hint warn';

            } else {

                summary.className = 'hint' + (data.consistent === false ? ' warn' : '');

            }

            summary.textContent = text;

        }

        const detail = $('videoRendererDetail');

        if (detail) detail.textContent = formatDetail(data);



        updateInstallUi(data, desktopStatus);

    }



    async function loadDesktopRemotionStatus() {

        if (!isDesktop()) return null;

        try {

            return await invoke('remotion_setup_status');

        } catch (_err) {

            return null;

        }

    }



    async function loadVideoRendererSettings() {

        const preferred = $('videoRendererPreferred');

        if (!preferred) return;

        setStatus('加载中…');

        try {

            const [resp, desktopStatus] = await Promise.all([

                fetch('/api/runtime/video-renderer'),

                loadDesktopRemotionStatus(),

            ]);

            const data = await resp.json();

            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);

            applySettings(data, desktopStatus);

            setStatus('已加载成片引擎状态', 'ok');

        } catch (err) {

            setStatus('加载失败: ' + (err.message || String(err)), 'error');

        }

    }



    async function saveVideoRendererSettings() {

        const preferred = $('videoRendererPreferred');

        const fallback = $('videoRendererAllowFallback');

        if (!preferred || !fallback) return;

        const payload = {

            preferred: preferred.value,

            allow_python_fallback: fallback.checked,

        };

        setStatus('保存中…');

        try {

            const resp = await fetch('/api/runtime/video-renderer', {

                method: 'PUT',

                headers: { 'Content-Type': 'application/json' },

                body: JSON.stringify(payload),

            });

            const data = await resp.json();

            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);

            const desktopStatus = await loadDesktopRemotionStatus();

            applySettings(data, desktopStatus);

            setStatus('成片引擎偏好已保存', 'ok');

        } catch (err) {

            setStatus('保存失败: ' + (err.message || String(err)), 'error');

        }

    }



    async function runRemotionSetup() {

        const btn = $('videoRendererInstallBtn');

        if (!btn || btn.disabled) return;

        btn.disabled = true;

        setStatus('正在安装 Remotion（后台进行，窗口应可继续操作；进度见下方）…', '');

        try {

            await invoke('remotion_setup_run');

            setStatus('Remotion 安装完成，后端已自动重启，可直接重新出片', 'ok');

            await loadVideoRendererSettings();

        } catch (err) {

            setStatus('安装失败: ' + (err.message || String(err)), 'error');

            btn.disabled = false;

        }

    }



    function ensureProgressListener() {

        if (progressListener || !isDesktop()) return;

        const listen = window.__TAURI__?.event?.listen;

        if (!listen) return;

        listen('ainews:remotion-setup-progress', (event) => {

            const payload = event.payload || {};

            const label = payload.label || payload.step || '安装中…';

            const percent = payload.percent != null ? ` (${payload.percent}%)` : '';

            setStatus(label + percent, payload.done ? 'ok' : '');

        }).then((unlisten) => {

            progressListener = unlisten;

        });

    }



    window.loadVideoRendererSettings = loadVideoRendererSettings;



    $('saveVideoRendererBtn')?.addEventListener('click', saveVideoRendererSettings);

    $('reloadVideoRendererBtn')?.addEventListener('click', loadVideoRendererSettings);

    $('videoRendererInstallBtn')?.addEventListener('click', runRemotionSetup);

    ensureProgressListener();

})();


