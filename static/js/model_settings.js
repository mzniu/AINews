(function () {
    const state = {
        providers: {},
        language_presets: [],
        vision_presets: [],
        defaults: {},
        language: { active_id: null, profiles: [] },
        vision: { active_id: null, profiles: [] },
    };

    const $ = (id) => document.getElementById(id);

    function setStatus(text, type = '') {
        const bar = $('statusBar') || $('modelsStatusBar');
        if (!bar) return;
        bar.textContent = text;
        bar.className = 'status-bar' + (type ? ` ${type}` : '');
    }

    async function api(path, options = {}) {
        const resp = await fetch(path, {
            headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
            ...options,
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
        }
        return data;
    }

    function providerBaseUrl(provider) {
        return (state.providers[provider] || {}).default_base_url || 'https://api.deepseek.com';
    }

    function newProfileId(prefix) {
        return `${prefix}_${Date.now().toString(36)}`;
    }

    function profileFromPreset(preset, kind) {
        const defaults = (state.defaults[kind] || {});
        return {
            id: preset.id || newProfileId(kind),
            display_name: preset.display_name || preset.model,
            provider: preset.provider || 'deepseek',
            base_url: providerBaseUrl(preset.provider),
            model: preset.model,
            api_key: '',
            api_key_masked: '',
            max_tokens: defaults.max_tokens || (kind === 'vision' ? 2048 : 8192),
            temperature: defaults.temperature ?? (kind === 'vision' ? 0.3 : 0.7),
            enabled: true,
        };
    }

    function emptyProfile(kind) {
        const defaults = (state.defaults[kind] || {});
        return {
            id: newProfileId(kind),
            display_name: kind === 'vision' ? '新视觉模型' : '新语言模型',
            provider: 'deepseek',
            base_url: providerBaseUrl('deepseek'),
            model: kind === 'vision' ? 'qwen-vl-max' : 'deepseek-chat',
            api_key: '',
            api_key_masked: '',
            max_tokens: defaults.max_tokens || (kind === 'vision' ? 2048 : 8192),
            temperature: defaults.temperature ?? (kind === 'vision' ? 0.3 : 0.7),
            enabled: true,
        };
    }

    function renderProfileCard(kind, profile, index) {
        const section = state[kind];
        const isActive = section.active_id === profile.id;
        const providerOptions = Object.entries(state.providers)
            .map(([id, meta]) => `<option value="${id}" ${profile.provider === id ? 'selected' : ''}>${meta.label || id}</option>`)
            .join('');

        return `
        <div class="profile-card ${isActive ? 'active' : ''}" data-kind="${kind}" data-index="${index}">
            <div class="profile-card-head">
                <h3>${escapeHtml(profile.display_name || profile.model)}</h3>
                <div>
                    ${isActive ? '<span class="badge badge-active">当前使用</span>' : ''}
                    ${profile.enabled ? '' : '<span class="badge badge-disabled">已停用</span>'}
                    <button type="button" class="btn btn-outline btn-sm set-active-btn">设为当前</button>
                    <button type="button" class="btn btn-danger btn-sm remove-btn">删除</button>
                </div>
            </div>
            <div class="form-grid">
                <div>
                    <label class="field-label">显示名称</label>
                    <input class="form-control" data-field="display_name" value="${escapeAttr(profile.display_name || '')}">
                </div>
                <div>
                    <label class="field-label">提供商</label>
                    <select class="form-control" data-field="provider">${providerOptions}</select>
                </div>
                <div>
                    <label class="field-label">模型 ID</label>
                    <input class="form-control" data-field="model" value="${escapeAttr(profile.model || '')}">
                </div>
                <div>
                    <label class="field-label">API Base URL</label>
                    <input class="form-control" data-field="base_url" value="${escapeAttr(profile.base_url || '')}">
                </div>
                <div>
                    <label class="field-label">API Key ${profile.api_key_masked ? `(已保存 ${escapeHtml(profile.api_key_masked)})` : ''}</label>
                    <input class="form-control" data-field="api_key" type="password" placeholder="留空则保留已保存的密钥" value="">
                </div>
                <div>
                    <label class="field-label">Max Tokens</label>
                    <input class="form-control" data-field="max_tokens" type="number" min="1" value="${Number(profile.max_tokens) || 8192}">
                </div>
                <div>
                    <label class="field-label">Temperature</label>
                    <input class="form-control" data-field="temperature" type="number" min="0" max="2" step="0.1" value="${Number(profile.temperature ?? 0.7)}">
                </div>
                <div>
                    <label class="field-label">启用</label>
                    <select class="form-control" data-field="enabled">
                        <option value="true" ${profile.enabled !== false ? 'selected' : ''}>是</option>
                        <option value="false" ${profile.enabled === false ? 'selected' : ''}>否</option>
                    </select>
                </div>
            </div>
        </div>`;
    }

    function renderSection(kind) {
        const container = kind === 'language' ? $('languageProfiles') : $('visionProfiles');
        const profiles = state[kind].profiles || [];
        if (!profiles.length) {
            container.innerHTML = '<p class="hint">暂无配置，请从预设添加或自定义。</p>';
            return;
        }
        container.innerHTML = profiles.map((p, i) => renderProfileCard(kind, p, i)).join('');
        bindProfileEvents(kind);
    }

    function bindProfileEvents(kind) {
        const container = kind === 'language' ? $('languageProfiles') : $('visionProfiles');
        container.querySelectorAll('.profile-card').forEach((card) => {
            const index = Number(card.dataset.index);
            const providerEl = card.querySelector('[data-field="provider"]');
            let previousProvider = state[kind].profiles[index].provider;
            card.querySelectorAll('[data-field]').forEach((el) => {
                if (el === providerEl) return;
                el.addEventListener('change', () => readProfileFromDom(kind, index, card));
                el.addEventListener('input', () => readProfileFromDom(kind, index, card));
            });
            if (providerEl) {
                providerEl.addEventListener('change', () => {
                    handleProviderChange(kind, index, card, providerEl.value, previousProvider);
                    previousProvider = providerEl.value;
                });
            }
            card.querySelector('.set-active-btn').addEventListener('click', () => {
                state[kind].active_id = state[kind].profiles[index].id;
                renderSection(kind);
            });
            card.querySelector('.remove-btn').addEventListener('click', () => {
                const removed = state[kind].profiles.splice(index, 1)[0];
                if (state[kind].active_id === removed.id) {
                    state[kind].active_id = state[kind].profiles[0]?.id || null;
                }
                renderSection(kind);
            });
        });
    }

    function readProfileFromDom(kind, index, card) {
        const profile = state[kind].profiles[index];
        card.querySelectorAll('[data-field]').forEach((el) => {
            const field = el.dataset.field;
            if (field === 'enabled') {
                profile.enabled = el.value === 'true';
            } else if (field === 'max_tokens') {
                profile.max_tokens = Number(el.value) || 8192;
            } else if (field === 'temperature') {
                profile.temperature = Number(el.value);
            } else if (field === 'api_key') {
                profile.api_key = el.value;
            } else {
                profile[field] = el.value;
            }
        });
    }

    function handleProviderChange(kind, index, card, newProvider, previousProvider) {
        const profile = state[kind].profiles[index];
        const baseInput = card.querySelector('[data-field="base_url"]');
        const currentUrl = (baseInput?.value || profile.base_url || '').trim();
        const prevDefault = providerBaseUrl(previousProvider || profile.provider);
        const shouldAutofill = !currentUrl || currentUrl === prevDefault;
        profile.provider = newProvider;
        if (shouldAutofill) {
            const nextUrl = providerBaseUrl(newProvider);
            profile.base_url = nextUrl;
            if (baseInput) baseInput.value = nextUrl;
        } else {
            profile.base_url = currentUrl;
            if (baseInput) baseInput.value = currentUrl;
        }
    }

    function fillPresetSelects() {
        const langSel = $('languagePresetSelect');
        const visSel = $('visionPresetSelect');
        langSel.innerHTML = state.language_presets.map((p) =>
            `<option value="${p.id}">${escapeHtml(p.display_name)} (${p.model})</option>`
        ).join('');
        visSel.innerHTML = state.vision_presets.map((p) =>
            `<option value="${p.id}">${escapeHtml(p.display_name)} (${p.model})</option>`
        ).join('');
    }

    function addFromPreset(kind) {
        const presets = kind === 'language' ? state.language_presets : state.vision_presets;
        const sel = kind === 'language' ? $('languagePresetSelect') : $('visionPresetSelect');
        const preset = presets.find((p) => p.id === sel.value) || presets[0];
        if (!preset) return;
        const profile = profileFromPreset(preset, kind);
        state[kind].profiles.push(profile);
        if (!state[kind].active_id) state[kind].active_id = profile.id;
        renderSection(kind);
    }

    function addCustom(kind) {
        const profile = emptyProfile(kind);
        state[kind].profiles.push(profile);
        if (!state[kind].active_id) state[kind].active_id = profile.id;
        renderSection(kind);
    }

    function collectPayload() {
        ['language', 'vision'].forEach((kind) => {
            const container = kind === 'language' ? $('languageProfiles') : $('visionProfiles');
            container.querySelectorAll('.profile-card').forEach((card) => {
                readProfileFromDom(kind, Number(card.dataset.index), card);
            });
        });
        return {
            version: 1,
            language: {
                active_id: state.language.active_id,
                profiles: state.language.profiles.map((p) => ({
                    id: p.id,
                    display_name: p.display_name,
                    provider: p.provider,
                    base_url: p.base_url,
                    model: p.model,
                    api_key: p.api_key || undefined,
                    max_tokens: Number(p.max_tokens) || 8192,
                    temperature: Number(p.temperature ?? 0.7),
                    enabled: p.enabled !== false,
                })),
            },
            vision: {
                active_id: state.vision.active_id,
                profiles: state.vision.profiles.map((p) => ({
                    id: p.id,
                    display_name: p.display_name,
                    provider: p.provider,
                    base_url: p.base_url,
                    model: p.model,
                    api_key: p.api_key || undefined,
                    max_tokens: Number(p.max_tokens) || 2048,
                    temperature: Number(p.temperature ?? 0.3),
                    enabled: p.enabled !== false,
                })),
            },
        };
    }

    function applyConfig(data) {
        state.providers = data.providers || {};
        state.language_presets = data.language_presets || [];
        state.vision_presets = data.vision_presets || [];
        state.defaults = data.defaults || {};
        state.language = data.language || { active_id: null, profiles: [] };
        state.vision = data.vision || { active_id: null, profiles: [] };
        fillPresetSelects();
        renderSection('language');
        renderSection('vision');
    }

    async function loadConfig() {
        setStatus('加载中…');
        const data = await api('/api/models/config');
        applyConfig(data);
        setStatus(data.has_local_file ? '已加载本地配置' : '使用默认模板（尚未保存本地配置）', 'ok');
    }

    async function saveConfig() {
        setStatus('保存中…');
        const payload = collectPayload();
        const data = await api('/api/models/config', {
            method: 'PUT',
            body: JSON.stringify(payload),
        });
        applyConfig(data);
        setStatus('配置已保存', 'ok');
    }

    async function testModel(kind) {
        const path = kind === 'language' ? '/api/models/test/language' : '/api/models/test/vision';
        setStatus('测试中…');
        await saveConfig();
        const data = await api(path, { method: 'POST' });
        setStatus(data.message + (data.reply ? ` · 回复: ${data.reply}` : ''), data.success ? 'ok' : 'error');
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        })[c]);
    }

    function escapeAttr(s) {
        return escapeHtml(s).replace(/"/g, '&quot;');
    }

    $('addLanguagePresetBtn').addEventListener('click', () => addFromPreset('language'));
    $('addVisionPresetBtn').addEventListener('click', () => addFromPreset('vision'));
    $('addLanguageBtn').addEventListener('click', () => addCustom('language'));
    $('addVisionBtn').addEventListener('click', () => addCustom('vision'));
    $('saveBtn')?.addEventListener('click', () => saveConfig().catch((e) => setStatus(e.message, 'error')));
    $('reloadBtn')?.addEventListener('click', () => loadConfig().catch((e) => setStatus(e.message, 'error')));
    $('saveModelsBtn')?.addEventListener('click', () => saveConfig().catch((e) => setStatus(e.message, 'error')));
    $('reloadModelsBtn')?.addEventListener('click', () => loadConfig().catch((e) => setStatus(e.message, 'error')));
    $('testLanguageBtn').addEventListener('click', () => testModel('language').catch((e) => setStatus(e.message, 'error')));
    $('testVisionBtn').addEventListener('click', () => testModel('vision').catch((e) => setStatus(e.message, 'error')));

    loadConfig().catch((e) => setStatus(e.message, 'error'));
})();
