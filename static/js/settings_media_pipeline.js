(function () {
    const $ = (id) => document.getElementById(id);

    function setStatus(text, type = '') {
        const bar = $('mediaPipelineStatusBar');
        if (!bar) return;
        bar.textContent = text;
        bar.className = 'status-bar' + (type ? ` ${type}` : '');
    }

    function updateHint(data) {
        const hint = $('mediaPipelineHint');
        if (!hint) return;
        hint.textContent =
            `当前规则：等级达到 ${data.min_grade} 级及以上，或总分 ≥ ${data.min_score} 时自动出片（满足任一即可）。` +
            ' 配置保存在 config/article_scoring.local.yaml。';
    }

    function applySettings(data) {
        const gradeSelect = $('mediaPipelineMinGrade');
        const scoreInput = $('mediaPipelineMinScore');
        if (gradeSelect && data.min_grade) {
            gradeSelect.value = data.min_grade;
            gradeSelect.dataset.lastValue = data.min_grade;
        }
        if (scoreInput && data.min_score != null) {
            scoreInput.value = Math.round(Number(data.min_score));
            scoreInput.dataset.lastValue = String(scoreInput.value);
        }
        updateHint(data);
    }

    async function loadMediaPipelineSettings() {
        const gradeSelect = $('mediaPipelineMinGrade');
        if (!gradeSelect) return;
        setStatus('加载中…');
        try {
            const resp = await fetch('/api/ingestion/media-pipeline/settings');
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
            applySettings(data);
            setStatus(data.has_local_override ? '已加载自动出片配置' : '使用默认配置（尚未保存本地覆盖）', 'ok');
        } catch (e) {
            setStatus('加载失败: ' + e.message, 'error');
        }
    }

    async function saveMediaPipelineSettings(payload) {
        const resp = await fetch('/api/ingestion/media-pipeline/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ logic: 'or', ...payload }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.message || '保存失败');
        applySettings(data);
        setStatus('自动出片规则已保存', 'ok');
        return data;
    }

    window.loadMediaPipelineSettings = loadMediaPipelineSettings;

    $('mediaPipelineMinGrade')?.addEventListener('change', async (event) => {
        const minGrade = event.target.value;
        const previous = event.target.dataset.lastValue || 'S';
        setStatus('保存中…');
        try {
            await saveMediaPipelineSettings({ min_grade: minGrade });
            event.target.dataset.lastValue = minGrade;
        } catch (err) {
            event.target.value = previous;
            setStatus('保存失败: ' + err.message, 'error');
        }
    });

    $('mediaPipelineMinScore')?.addEventListener('change', async (event) => {
        const input = event.target;
        const minScore = Number(input.value);
        const previous = input.dataset.lastValue || '80';
        if (!Number.isFinite(minScore) || minScore < 0 || minScore > 100) {
            input.value = previous;
            setStatus('总分须在 0–100 之间', 'error');
            return;
        }
        setStatus('保存中…');
        try {
            await saveMediaPipelineSettings({ min_score: minScore });
            input.dataset.lastValue = String(minScore);
        } catch (err) {
            input.value = previous;
            setStatus('保存失败: ' + err.message, 'error');
        }
    });
})();
