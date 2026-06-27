const API_BASE = '/api/digital-human';

const state = {
    avatar: null,
    audio: null,
    taskId: null,
    timer: null,
};

const avatarInput = document.getElementById('avatarInput');
const avatarImageInput = document.getElementById('avatarImageInput');
const audioInput = document.getElementById('audioInput');
const avatarName = document.getElementById('avatarName');
const avatarImageName = document.getElementById('avatarImageName');
const audioName = document.getElementById('audioName');
const avatarSelect = document.getElementById('avatarSelect');
const audioSelect = document.getElementById('audioSelect');
const modeSelect = document.getElementById('modeSelect');
const engineSelect = document.getElementById('engineSelect');
const engineSeg = document.getElementById('engineSeg');
const imageUploadBox = document.getElementById('imageUploadBox');
const videoUploadBox = document.getElementById('videoUploadBox');
const engineHint = document.getElementById('engineHint');
const uploadStatus = document.getElementById('uploadStatus');
const generateBtn = document.getElementById('generateBtn');
const progressCard = document.getElementById('progressCard');
const progressText = document.getElementById('progressText');
const progressPercent = document.getElementById('progressPercent');
const progressFill = document.getElementById('progressFill');
const resultVideo = document.getElementById('resultVideo');
const previewEmpty = document.getElementById('previewEmpty');
const resultActions = document.getElementById('resultActions');
const downloadLink = document.getElementById('downloadLink');

const ENGINE_HINTS = {
    auto: '自动选择可用的最佳引擎（EchoMimic V2 → MuseTalk → Wav2Lip）',
    echomimic: '只需上传一张正脸半身图片，EchoMimic V2 用扩散模型驱动口型与动作',
    musetalk: '上传一段人物视频作为形象，MuseTalk 1.5 进行高质量唇形同步',
    wav2lip: '上传一段人物视频作为形象，Wav2Lip 进行唇形同步（兜底方案）',
};

function updateEngineUI(engine) {
    engineSeg.querySelectorAll('.engine-seg-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.engine === engine);
    });
    engineSelect.value = engine;

    const isEchoMimic = engine === 'echomimic';
    imageUploadBox.style.display = isEchoMimic ? '' : 'none';
    videoUploadBox.style.display = isEchoMimic ? 'none' : '';

    engineHint.textContent = ENGINE_HINTS[engine] || '';

    const modeRow = document.getElementById('modeRow');
    if (modeRow) {
        if (isEchoMimic) {
            modeRow.style.display = 'none';
            modeSelect.value = 'ai';
        } else {
            modeRow.style.display = '';
        }
    }
    syncEngineSelectState();
}

engineSeg.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-engine]');
    if (!btn) return;
    updateEngineUI(btn.dataset.engine);
});

function setStatus(message, type = '') {
    uploadStatus.innerHTML = message ? `<div class="${type}">${message}</div>` : '';
}

function setProgress(task) {
    const progress = Math.max(0, Math.min(100, Number(task.progress || 0)));
    progressCard.classList.remove('hidden');
    progressText.textContent = task.message || task.status || '处理中';
    progressPercent.textContent = `${progress}%`;
    progressFill.style.width = `${progress}%`;
}

function syncEngineSelectState() {
    const isAiMode = (modeSelect.value || 'fast') === 'ai';
    engineSelect.disabled = !isAiMode;
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    let payload = null;
    try {
        payload = await response.json();
    } catch (error) {
        payload = { detail: await response.text() };
    }
    if (!response.ok || payload.success === false) {
        throw new Error(payload.detail || payload.message || '请求失败');
    }
    return payload;
}

async function uploadFile(file, endpoint) {
    const formData = new FormData();
    formData.append('file', file);
    return requestJson(`${API_BASE}/${endpoint}`, {
        method: 'POST',
        body: formData,
    });
}

async function refreshAvatars(selectedPath = '') {
    const payload = await requestJson(`${API_BASE}/avatars`);
    avatarSelect.innerHTML = '';
    if (!payload.avatars.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '请先上传形象视频';
        avatarSelect.appendChild(option);
        return;
    }

    for (const avatar of payload.avatars) {
        const option = document.createElement('option');
        option.value = avatar.url || avatar.path;
        option.textContent = `${avatar.label || avatar.name}${avatar.duration ? ` · ${avatar.duration}s` : ''}`;
        avatarSelect.appendChild(option);
    }

    if (selectedPath) {
        avatarSelect.value = selectedPath;
    }
}

async function refreshAudio(selectedUrl = '') {
    const payload = await requestJson(`${API_BASE}/audio`);
    audioSelect.innerHTML = '';
    if (!payload.audio || !payload.audio.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = '请先上传驱动音频';
        audioSelect.appendChild(option);
        return;
    }

    for (const audio of payload.audio) {
        const option = document.createElement('option');
        option.value = audio.url;
        option.textContent = `${audio.label || audio.name}${audio.duration ? ` · ${audio.duration}s` : ''}`;
        audioSelect.appendChild(option);
    }

    if (selectedUrl) {
        audioSelect.value = selectedUrl;
    }
}

avatarInput.addEventListener('change', async () => {
    const file = avatarInput.files && avatarInput.files[0];
    if (!file) return;
    avatarName.textContent = file.name;
    setStatus('正在上传形象视频...');
    avatarInput.disabled = true;
    try {
        const payload = await uploadFile(file, 'upload-avatar');
        state.avatar = payload.file;
        setStatus(`形象视频上传成功：${payload.file.filename}`, 'ok');
        await refreshAvatars(payload.file.url);
    } catch (error) {
        setStatus(error.message, 'error');
    } finally {
        avatarInput.disabled = false;
    }
});

avatarImageInput.addEventListener('change', async () => {
    const file = avatarImageInput.files && avatarImageInput.files[0];
    if (!file) return;
    avatarImageName.textContent = file.name;
    setStatus('正在上传形象图片...');
    avatarImageInput.disabled = true;
    try {
        const payload = await uploadFile(file, 'upload-avatar');
        state.avatar = payload.file;
        setStatus(`形象图片上传成功：${payload.file.filename}`, 'ok');
        await refreshAvatars(payload.file.url);
    } catch (error) {
        setStatus(error.message, 'error');
    } finally {
        avatarImageInput.disabled = false;
    }
});

audioInput.addEventListener('change', async () => {
    const file = audioInput.files && audioInput.files[0];
    if (!file) return;
    audioName.textContent = file.name;
    setStatus('正在上传驱动音频...');
    audioInput.disabled = true;
    try {
        const payload = await uploadFile(file, 'upload-audio');
        state.audio = payload.file;
        setStatus(`驱动音频上传成功：${payload.file.filename}`, 'ok');
        await refreshAudio(payload.file.url);
    } catch (error) {
        setStatus(error.message, 'error');
    } finally {
        audioInput.disabled = false;
    }
});

generateBtn.addEventListener('click', async () => {
    const avatarPath = avatarSelect.value || (state.avatar && state.avatar.url);
    const audioPath = audioSelect.value || (state.audio && state.audio.url);
    if (!avatarPath) {
        setStatus('请先上传或选择形象视频', 'error');
        return;
    }
    if (!audioPath) {
        setStatus('请先上传驱动音频', 'error');
        return;
    }

    generateBtn.disabled = true;
    resultActions.classList.add('hidden');
    resultVideo.style.display = 'none';
    previewEmpty.style.display = 'block';
    setProgress({ progress: 0, message: '正在创建任务' });

    try {
        const payload = await requestJson(`${API_BASE}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                avatar_video: avatarPath,
                audio_file: audioPath,
                mode: modeSelect.value || 'fast',
                engine: engineSelect.value || 'auto',
                use_super_resolution: document.getElementById('superResolutionToggle').checked,
                use_action_generalization: document.getElementById('actionToggle').checked,
                batch_size: Number(document.getElementById('batchSizeInput').value || 4),
            }),
        });
        state.taskId = payload.task.task_id;
        pollProgress();
        state.timer = window.setInterval(pollProgress, 1800);
    } catch (error) {
        setStatus(error.message, 'error');
        generateBtn.disabled = false;
    }
});

async function pollProgress() {
    if (!state.taskId) return;
    try {
        const payload = await requestJson(`${API_BASE}/progress/${state.taskId}`);
        const task = payload.task;
        setProgress(task);
        if (task.status === 'done') {
            stopPolling();
            showResult(task.output_url);
            setStatus('数字人视频生成完成', 'ok');
            generateBtn.disabled = false;
        } else if (task.status === 'failed') {
            stopPolling();
            setStatus(task.error || '数字人视频生成失败', 'error');
            generateBtn.disabled = false;
        }
    } catch (error) {
        stopPolling();
        setStatus(error.message, 'error');
        generateBtn.disabled = false;
    }
}

function stopPolling() {
    if (state.timer) {
        window.clearInterval(state.timer);
        state.timer = null;
    }
}

function showResult(url) {
    if (!url) return;
    previewEmpty.style.display = 'none';
    resultVideo.src = url;
    resultVideo.style.display = 'block';
    downloadLink.href = url;
    resultActions.classList.remove('hidden');
}

document.getElementById('refreshAvatarsBtn').addEventListener('click', async () => {
    try {
        await refreshAvatars(avatarSelect.value);
        setStatus('形象库已刷新', 'ok');
    } catch (error) {
        setStatus(error.message, 'error');
    }
});

document.getElementById('copyLinkBtn').addEventListener('click', async () => {
    const href = downloadLink.href;
    if (!href || href.endsWith('#')) return;
    try {
        await navigator.clipboard.writeText(href);
        setStatus('视频地址已复制', 'ok');
    } catch (error) {
        setStatus('复制失败，请直接使用下载按钮', 'error');
    }
});

modeSelect.addEventListener('change', syncEngineSelectState);

async function refreshEngineStatus() {
    const badge = document.getElementById('engineStatusBadge');
    if (!badge) return;
    try {
        const payload = await requestJson(`${API_BASE}/engine-status`);
        const em = payload.engines.echomimic;
        const mt = payload.engines.musetalk;
        const wl = payload.engines.wav2lip;
        if (em && em.available) {
            badge.textContent = '✓ EchoMimic V2 就绪';
            badge.style.color = '#22c55e';
        } else if (mt.available) {
            badge.textContent = '✓ MuseTalk 就绪';
            badge.style.color = '#22c55e';
        } else if (wl.available) {
            badge.textContent = '⚠ 仅 Wav2Lip 可用';
            badge.style.color = '#f59e0b';
        } else {
            badge.textContent = '✗ AI 引擎不可用';
            badge.style.color = '#ef4444';
        }
    } catch {
        // ignore
    }
}

refreshAvatars().catch((error) => setStatus(error.message, 'error'));
refreshAudio().catch(() => {});
updateEngineUI('auto');
refreshEngineStatus();