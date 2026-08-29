(function () {
    let scoringState = { dimensions: [], presets: [], weights: {}, grades: {} };
    let dirty = false;

    const $ = (id) => document.getElementById(id);

    function setStatus(text, type = '') {
        const bar = $('imageScoringStatusBar');
        if (!bar) return;
        bar.textContent = text;
        bar.className = 'status-bar' + (type ? ` ${type}` : '');
    }

    function markDirty() {
        dirty = true;
        setStatus('有未保存的修改', '');
    }

    function pct(value) {
        return Math.round(Number(value) * 1000) / 10;
    }

    function updateWeightSum() {
        const weights = collectWeights();
        const sum = Object.values(weights).reduce((acc, v) => acc + v, 0);
        const el = $('imageScoringWeightSum');
        if (el) {
            el.textContent = `合计 ${pct(sum)}%`;
            el.className = 'badge' + (Math.abs(sum - 1) > 0.02 ? ' badge-warn' : '');
        }
    }

    function renderPresetOptions(data) {
        const select = $('imageScoringPresetSelect');
        if (!select) return;
        const options = (data.presets || []).map((preset) =>
            `<option value="${preset.id}">${escapeHtml(preset.label)}</option>`
        );
        options.push('<option value="custom">自定义权重</option>');
        select.innerHTML = options.join('');
        select.value = data.profile || 'short_video_clip';
        updatePresetDescription(data);
    }

    function updatePresetDescription(data) {
        const desc = $('imageScoringPresetDesc');
        const select = $('imageScoringPresetSelect');
        if (!desc || !select) return;
        if (select.value === 'custom') {
            desc.textContent = '当前为自定义权重，可拖动滑块微调各维度占比。';
            return;
        }
        const preset = (data.presets || []).find((item) => item.id === select.value);
        desc.textContent = preset ? preset.description : '';
    }

    function renderWeights(data) {
        const list = $('imageScoringWeightsList');
        if (!list) return;
        const dimensions = data.dimensions || [];
        list.innerHTML = dimensions.map((dim) => {
            const value = Number((data.weights || {})[dim.key] || 0);
            return `
                <div class="scoring-weight-row" data-key="${escapeAttr(dim.key)}">
                    <div class="scoring-weight-head">
                        <strong>${escapeHtml(dim.label)}</strong>
                        <span class="scoring-weight-pct" data-pct-for="${escapeAttr(dim.key)}">${pct(value)}%</span>
                    </div>
                    <input type="range" class="scoring-weight-slider image-scoring-weight-slider" data-weight-key="${escapeAttr(dim.key)}"
                        min="0" max="50" step="1" value="${Math.round(value * 100)}">
                    <p class="hint">${escapeHtml(dim.hint || '')}</p>
                </div>
            `;
        }).join('');

        list.querySelectorAll('.image-scoring-weight-slider').forEach((slider) => {
            slider.addEventListener('input', () => {
                const key = slider.dataset.weightKey;
                const pctEl = list.querySelector(`[data-pct-for="${key}"]`);
                if (pctEl) pctEl.textContent = `${slider.value}%`;
                $('imageScoringPresetSelect').value = 'custom';
                updatePresetDescription({ presets: scoringState.presets });
                updateWeightSum();
                markDirty();
            });
        });
        updateWeightSum();
    }

    function renderGrades(data) {
        const grades = data.grades || {};
        $('imageGradeThresholdA').value = grades.A ?? 80;
        $('imageGradeThresholdB').value = grades.B ?? 60;
        $('imageGradeThresholdC').value = grades.C ?? 40;
    }

    function renderGifBoost(data) {
        const box = $('imagePreferGifBoost');
        if (box) box.checked = !!data.prefer_gif_boost;
        const boostHint = $('imageGifBoostHint');
        if (boostHint) boostHint.textContent = String(Math.round(Number(data.gif_boost_points) || 25));
        const animHint = $('imageAnimatedBonusHint');
        if (animHint) animHint.textContent = String(Math.round(Number(data.animated_bonus) || 8));
    }

    function collectWeights() {
        const weights = {};
        document.querySelectorAll('.image-scoring-weight-slider').forEach((slider) => {
            weights[slider.dataset.weightKey] = Number(slider.value) / 100;
        });
        return weights;
    }

    function collectGrades() {
        return {
            A: Number($('imageGradeThresholdA').value),
            B: Number($('imageGradeThresholdB').value),
            C: Number($('imageGradeThresholdC').value),
        };
    }

    function applyPresetToForm(preset) {
        if (!preset) return;
        document.querySelectorAll('.image-scoring-weight-slider').forEach((slider) => {
            const key = slider.dataset.weightKey;
            const value = Number((preset.weights || {})[key] || 0);
            slider.value = Math.round(value * 100);
            const pctEl = document.querySelector(`[data-pct-for="${key}"]`);
            if (pctEl) pctEl.textContent = `${pct(value)}%`;
        });
        const grades = preset.grades || {};
        $('imageGradeThresholdA').value = grades.A ?? $('imageGradeThresholdA').value;
        $('imageGradeThresholdB').value = grades.B ?? $('imageGradeThresholdB').value;
        $('imageGradeThresholdC').value = grades.C ?? $('imageGradeThresholdC').value;
        updateWeightSum();
    }

    function applyConfig(data) {
        scoringState = data;
        dirty = false;
        renderPresetOptions(data);
        renderWeights(data);
        renderGrades(data);
        renderGifBoost(data);
    }

    async function loadImageScoringSettings() {
        setStatus('加载中…');
        const resp = await fetch('/api/ingestion/image-scoring/settings');
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
        applyConfig(data);
        setStatus(
            data.has_local_override ? '已加载配图评分配置' : '使用默认配图评分模板（尚未保存本地覆盖）',
            'ok'
        );
    }

    async function saveImageScoringSettings(payload) {
        const resp = await fetch('/api/ingestion/image-scoring/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.message || '保存失败');
        applyConfig(data);
        dirty = false;
        setStatus(data.message || '配图评分配置已保存', 'ok');
        return data;
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        })[c]);
    }

    function escapeAttr(s) {
        return escapeHtml(s).replace(/"/g, '&quot;');
    }

    window.loadImageScoringSettings = loadImageScoringSettings;

    $('imageScoringPresetSelect')?.addEventListener('change', (event) => {
        const presetId = event.target.value;
        updatePresetDescription(scoringState);
        if (presetId === 'custom') {
            markDirty();
            return;
        }
        const preset = (scoringState.presets || []).find((item) => item.id === presetId);
        applyPresetToForm(preset);
        markDirty();
    });

    ['imageGradeThresholdA', 'imageGradeThresholdB', 'imageGradeThresholdC'].forEach((id) => {
        $(id)?.addEventListener('input', () => markDirty());
    });

    $('imagePreferGifBoost')?.addEventListener('change', () => markDirty());

    $('saveImageScoringBtn')?.addEventListener('click', () => {
        const preset = $('imageScoringPresetSelect').value;
        const payload = { grades: collectGrades(), prefer_gif_boost: !!$('imagePreferGifBoost')?.checked };
        if (preset === 'custom') {
            payload.profile = 'custom';
            payload.weights = collectWeights();
        } else {
            payload.profile = preset;
        }
        saveImageScoringSettings(payload).catch((e) => setStatus(e.message, 'error'));
    });

    $('reloadImageScoringBtn')?.addEventListener('click', () => {
        if (dirty && !window.confirm('有未保存的修改，确定重新加载？')) return;
        loadImageScoringSettings().catch((e) => setStatus(e.message, 'error'));
    });
})();
