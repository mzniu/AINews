// 全局变量
        let currentProjectId = null;
        const imageCatalog = new Map();
        let selectedImageItems = [];
        let generatedContent = null;
        let ghDragSrcEl = null;
        let baseVideoPath = null;
        let finalVoiceoverUrl = null;

        // DOM元素引用
        const stepPanels = {
            1: document.getElementById('step1-panel'),
            2: document.getElementById('step2-panel'),
            3: document.getElementById('step3-panel'),
            4: document.getElementById('step4-panel'),
            5: document.getElementById('step5-panel')
        };

        const stepIndicators = {
            1: document.getElementById('step1'),
            2: document.getElementById('step2'),
            3: document.getElementById('step3'),
            4: document.getElementById('step4'),
            5: document.getElementById('step5')
        };

        // API基础URL
        const API_BASE = '/api/github';

        function getSelectedImageIds() {
            return selectedImageItems.map(x => x.id);
        }

        function syncSelectedImageItemsFromDom() {
            const selectedEls = [...document.querySelectorAll('.image-item.selected')];
            const prevById = new Map(selectedImageItems.map((x) => [x.id, x]));
            const selectedIdSet = new Set(
                selectedEls.map((el) => el.dataset.imageId || el.dataset.videoId)
            );

            // 先按「当前列表」顺序保留仍选中的项，避免 querySelectorAll 的 DOM 顺序覆盖排序面板里的顺序
            const next = [];
            for (const item of selectedImageItems) {
                if (selectedIdSet.has(item.id)) {
                    next.push(item);
                }
            }
            const seen = new Set(next.map((x) => x.id));

            for (const el of selectedEls) {
                const id = el.dataset.imageId || el.dataset.videoId;
                if (seen.has(id)) continue;
                const kind = el.dataset.videoId ? 'video' : 'image';
                const prev = prevById.get(id);
                const cat = imageCatalog.get(id);
                const imgEl = el.querySelector('img');
                const vidEl = el.querySelector('video.github-readme-video-thumb');
                next.push({
                    id,
                    kind: cat?.kind || kind,
                    duration: prev != null ? prev.duration : 3,
                    src: cat?.src || (vidEl?.src || imgEl?.src || ''),
                });
                seen.add(id);
            }

            selectedImageItems = next;
            const warning = document.getElementById('image-selection-warning');
            if (warning) {
                warning.style.display = selectedImageItems.length < 3 ? 'block' : 'none';
            }
        }

        function openGhLightbox(src, asVideo) {
            if (!src) return;
            const img = document.getElementById('ghLightboxImg');
            const vid = document.getElementById('ghLightboxVideo');
            const lb = document.getElementById('ghImageLightbox');
            if (!lb) return;
            if (asVideo && vid) {
                if (img) img.style.display = 'none';
                vid.style.display = 'block';
                vid.src = src;
                vid.play?.().catch(() => {});
            } else {
                if (vid) {
                    vid.style.display = 'none';
                    try { vid.pause(); } catch (e) {}
                    vid.src = '';
                }
                if (img) {
                    img.style.display = '';
                    img.src = src;
                }
            }
            lb.classList.add('is-open');
        }

        function closeGhLightbox() {
            const lb = document.getElementById('ghImageLightbox');
            const imgEl = document.getElementById('ghLightboxImg');
            const vid = document.getElementById('ghLightboxVideo');
            if (lb) lb.classList.remove('is-open');
            if (imgEl) {
                imgEl.src = '';
                imgEl.style.display = '';
            }
            if (vid) {
                try { vid.pause(); } catch (e) {}
                vid.src = '';
                vid.style.display = 'none';
            }
        }

        function closeGithubSortPanel() {
            const p = document.getElementById('githubSortPanel');
            if (p) {
                p.classList.remove('is-open');
                p.setAttribute('aria-hidden', 'true');
            }
        }

        function syncGithubOrderFromSortList() {
            const items = [...document.querySelectorAll('#githubSortableList .github-sort-item')];
            const order = items.map(el => el.dataset.id);
            const map = new Map(selectedImageItems.map(x => [x.id, x]));
            selectedImageItems = order.map(id => map.get(id)).filter(Boolean);
        }

        function ghUpdateOrderNumbers() {
            document.querySelectorAll('#githubSortableList .github-sort-item').forEach((el, i) => {
                const num = el.querySelector('.github-order-num');
                if (num) num.textContent = `${i + 1}.`;
            });
        }

        function ghHandleDragStart(e) {
            ghDragSrcEl = this;
            e.dataTransfer.effectAllowed = 'move';
            this.classList.add('dragging');
        }

        function ghHandleDragOver(e) {
            if (e.preventDefault) e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (this !== ghDragSrcEl) this.classList.add('over');
            return false;
        }

        function ghHandleDrop(e) {
            if (e.stopPropagation) e.stopPropagation();
            if (ghDragSrcEl && ghDragSrcEl !== this) {
                const parent = ghDragSrcEl.parentNode;
                const dragIndex = Array.from(parent.children).indexOf(ghDragSrcEl);
                const dropIndex = Array.from(parent.children).indexOf(this);
                if (dragIndex < dropIndex) {
                    parent.insertBefore(ghDragSrcEl, this.nextSibling);
                } else {
                    parent.insertBefore(ghDragSrcEl, this);
                }
                syncGithubOrderFromSortList();
                ghUpdateOrderNumbers();
            }
            return false;
        }

        function ghHandleDragEnd() {
            this.classList.remove('dragging');
            document.querySelectorAll('#githubSortableList .github-sort-item').forEach(el => {
                el.classList.remove('over');
            });
            ghDragSrcEl = null;
        }

        function initGithubSortableDrag() {
            document.querySelectorAll('#githubSortableList .github-sort-item').forEach(item => {
                item.addEventListener('dragstart', ghHandleDragStart);
                item.addEventListener('dragover', ghHandleDragOver);
                item.addEventListener('drop', ghHandleDrop);
                item.addEventListener('dragend', ghHandleDragEnd);
            });
        }

        function updateGithubSortPanel() {
            const container = document.getElementById('githubSortableList');
            if (!container) return;
            container.innerHTML = '';
            selectedImageItems.forEach((item, index) => {
                const div = document.createElement('div');
                div.className = 'github-sort-item';
                div.draggable = true;
                div.dataset.id = item.id;
                const shortId = item.id.length > 14 ? `${item.id.slice(0, 12)}…` : item.id;
                const thumb =
                    (item.kind || 'image') === 'video'
                        ? `<video src="${item.src}" muted playsinline preload="metadata" class="github-sort-thumb-video"></video>`
                        : `<img src="${item.src}" alt="" />`;
                div.innerHTML = `
                    <span class="github-order-num">${index + 1}.</span>
                    ${thumb}
                    <span class="github-sort-id" title="${item.id}">${shortId}</span>
                    <div class="github-duration-config">
                        <input type="number" class="github-duration-input" min="0.5" max="30" step="0.5" value="${item.duration}" data-id="${item.id}" />
                        <span>秒</span>
                    </div>
                `;
                container.appendChild(div);
            });
            container.querySelectorAll('.github-duration-input').forEach(inp => {
                inp.addEventListener('change', () => {
                    const id = inp.dataset.id;
                    const v = parseFloat(inp.value);
                    const found = selectedImageItems.find(x => x.id === id);
                    if (found && !isNaN(v)) {
                        found.duration = Math.min(30, Math.max(0.5, v));
                        inp.value = String(found.duration);
                    }
                });
            });
            initGithubSortableDrag();
        }

        // 通知函数
        function showNotification(message, type = 'info') {
            const notificationArea = document.getElementById('notifications');
            const notification = document.createElement('div');
            notification.className = `notification ${type}`;
            notification.innerHTML = message;
            notification.style.display = 'block';
            
            notificationArea.appendChild(notification);
            
            // 3秒后自动消失
            setTimeout(() => {
                notification.remove();
            }, 3000);
        }

        async function ensureGithubVoiceCloneAudioUploaded() {
            const fileInput = document.getElementById('voiceover-clone-audio');
            const pathInput = document.getElementById('voiceover-clone-audio-path');
            const status = document.getElementById('voiceover-clone-audio-status');
            const file = fileInput?.files?.[0];
            if (!file) return pathInput?.value || '';
            if (pathInput?.dataset.fileName === file.name && pathInput.value) {
                return pathInput.value;
            }
            if (status) status.textContent = '正在上传参考音频…';
            const formData = new FormData();
            formData.append('audio', file);
            const response = await fetch('/api/upload-voice-clone-audio', {
                method: 'POST',
                body: formData,
            });
            let data = {};
            try {
                data = await response.json();
            } catch (_) {
                data = {};
            }
            if (!response.ok || !data.success) {
                throw new Error(data.detail || data.message || '参考音频上传失败');
            }
            if (pathInput) {
                pathInput.value = data.path || '';
                pathInput.dataset.fileName = file.name;
            }
            if (status) status.textContent = `已上传：${file.name}`;
            return data.path || '';
        }

        // 更新步骤状态
        function updateStep(currentStep) {
            // 更新步骤指示器
            Object.keys(stepIndicators).forEach(stepNum => {
                const ind = stepIndicators[stepNum];
                if (!ind) return;
                if (parseInt(stepNum) <= currentStep) {
                    ind.classList.add('active');
                } else {
                    ind.classList.remove('active');
                }
            });

            // 更新步骤面板状态
            Object.keys(stepPanels).forEach(stepNum => {
                const panel = stepPanels[stepNum];
                if (!panel) return;
                if (parseInt(stepNum) < currentStep) {
                    panel.classList.add('completed');
                    panel.classList.remove('active');
                } else if (parseInt(stepNum) === currentStep) {
                    panel.classList.add('active');
                    panel.classList.remove('completed');
                } else {
                    panel.classList.remove('active', 'completed');
                }
            });
        }

        // 处理项目按钮点击事件
        document.getElementById('process-btn').addEventListener('click', async () => {
            const githubUrl = document.getElementById('github-url').value.trim();
            const includeScreenshots = document.getElementById('include-screenshots').checked;
            const maxImages = parseInt(document.getElementById('max-images').value);

            if (!githubUrl) {
                showNotification('请输入GitHub项目链接', 'error');
                return;
            }

            try {
                let useLocalCache = false;
                let cachedProjectId = null;
                try {
                    const cacheRes = await fetch(
                        `${API_BASE}/local-cache?github_url=${encodeURIComponent(githubUrl)}`
                    );
                    if (cacheRes.ok) {
                        const cacheJson = await cacheRes.json();
                        if (cacheJson.cached && cacheJson.project_id) {
                            const useCached = window.confirm(
                                '检测到该仓库此前已在本机下载过，本地已有素材与元数据。\n\n' +
                                    '· 点击「确定」：跳过重新抓取，直接进入第二步使用已有内容\n' +
                                    '· 点击「取消」：重新从网络处理（会更新 README、图片等）'
                            );
                            if (useCached) {
                                useLocalCache = true;
                                cachedProjectId = cacheJson.project_id;
                            }
                        }
                    }
                } catch (e) {
                    console.warn('本地缓存检查失败，继续完整处理', e);
                }

                if (useLocalCache && cachedProjectId) {
                    currentProjectId = cachedProjectId;
                    showNotification('已使用本机已下载的项目数据', 'success');
                    updateStep(2);
                    await loadProjectImages();
                    return;
                }

                // 显示加载状态
                document.getElementById('processing-loading').style.display = 'block';
                document.getElementById('process-btn').disabled = true;

                // 发送处理请求
                const response = await fetch(`${API_BASE}/process-project`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        github_url: githubUrl,
                        include_screenshots: includeScreenshots,
                        max_images: maxImages,
                        max_videos: Math.max(
                            0,
                            parseInt(document.getElementById('max-videos')?.value, 10) || 5
                        )
                    })
                });

                const result = await response.json();

                if (result.success) {
                    currentProjectId = result.project_id;
                    showNotification(`项目处理成功: ${result.project_id}`, 'success');
                    updateStep(2);
                    loadProjectImages();
                } else {
                    showNotification(`处理失败: ${result.message}`, 'error');
                }
            } catch (error) {
                showNotification(`请求失败: ${error.message}`, 'error');
            } finally {
                document.getElementById('processing-loading').style.display = 'none';
                document.getElementById('process-btn').disabled = false;
            }
        });

        // 加载项目图片
        async function loadProjectImages() {
            if (!currentProjectId) return;

            try {
                const response = await fetch(`${API_BASE}/projects/${currentProjectId}/images`);
                const imageData = await response.json();

                const imageGrid = document.getElementById('image-grid');
                imageGrid.innerHTML = '';
                imageCatalog.clear();
                selectedImageItems = [];
                closeGithubSortPanel();

                const avail = imageData.available_images || [];
                const availVideos = imageData.available_videos || [];
                const cacheBust = Date.now();

                function renderImageItem(image) {
                    const thumbSrc = `${API_BASE}/projects/${currentProjectId}/images/${image.id}?cb=${cacheBust}`;
                    imageCatalog.set(image.id, { src: thumbSrc, kind: 'image' });

                    const imageItem = document.createElement('div');
                    imageItem.className = 'image-item';
                    imageItem.dataset.imageId = image.id;

                    const sourceText = image.source === 'readme' ? 'README图片' :
                        image.source === 'screenshot' ? '主页截图' :
                        image.source === 'star_history' ? 'Star 历史曲线图' : '项目图片';
                    const sourceClass = image.source === 'screenshot' ? 'screenshot-source' :
                        image.source === 'star_history' ? 'star-history-source' : '';

                    imageItem.innerHTML = `
                        <button type="button" class="image-zoom-btn" aria-label="查看大图">🔍</button>
                        <img src="${thumbSrc}"
                             alt="${image.alt_text || '项目图片'}">
                        <div class="image-info ${sourceClass}">
                            <small>${sourceText}</small>
                        </div>
                        <div class="checkbox-overlay"></div>
                    `;

                    const zoomBtn = imageItem.querySelector('.image-zoom-btn');
                    zoomBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        openGhLightbox(thumbSrc, false);
                    });

                    imageItem.addEventListener('click', () => {
                        imageItem.classList.toggle('selected');
                        syncSelectedImageItemsFromDom();
                    });

                    imageGrid.appendChild(imageItem);
                }

                function renderVideoItem(video) {
                    const thumbSrc = `${API_BASE}/projects/${currentProjectId}/videos/${video.id}?cb=${cacheBust}`;
                    imageCatalog.set(video.id, { src: thumbSrc, kind: 'video' });

                    const imageItem = document.createElement('div');
                    imageItem.className = 'image-item image-item-video';
                    imageItem.dataset.videoId = video.id;

                    imageItem.innerHTML = `
                        <button type="button" class="image-zoom-btn" aria-label="预览视频">🔍</button>
                        <video class="github-readme-video-thumb" src="${thumbSrc}" muted playsinline preload="metadata"></video>
                        <div class="image-info video-source">
                            <small>README 视频（画中画）</small>
                        </div>
                        <div class="checkbox-overlay"></div>
                    `;

                    const zoomBtn = imageItem.querySelector('.image-zoom-btn');
                    zoomBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        openGhLightbox(thumbSrc, true);
                    });

                    imageItem.addEventListener('click', () => {
                        imageItem.classList.toggle('selected');
                        syncSelectedImageItemsFromDom();
                    });

                    imageGrid.appendChild(imageItem);
                }

                avail.forEach(renderImageItem);
                availVideos.forEach(renderVideoItem);

            } catch (error) {
                showNotification(`加载图片失败: ${error.message}`, 'error');
            }
        }

        // 确认图片选择
        document.getElementById('confirm-images-btn').addEventListener('click', async () => {
            syncSelectedImageItemsFromDom();
            if (getSelectedImageIds().length === 0) {
                showNotification('请至少选择一张图片或一段 README 视频', 'warning');
                return;
            }

            try {
                const imageIds = [...document.querySelectorAll('.image-item.selected[data-image-id]')].map(
                    (el) => el.dataset.imageId
                );
                const videoIds = [...document.querySelectorAll('.image-item.selected[data-video-id]')].map(
                    (el) => el.dataset.videoId
                );
                const response = await fetch(`${API_BASE}/projects/${currentProjectId}/select-images`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ image_ids: imageIds, video_ids: videoIds })
                });

                if (response.ok) {
                    showNotification('图片选择已保存', 'success');
                    updateStep(3);
                    generateContent();
                } else {
                    throw new Error('保存图片选择失败');
                }
            } catch (error) {
                showNotification(`操作失败: ${error.message}`, 'error');
            }
        });

        // 生成内容
        async function generateContent() {
            try {
                const response = await fetch(`${API_BASE}/generate-content`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        project_id: currentProjectId,
                        selected_images: getSelectedImageIds()
                    })
                });

                const result = await response.json();

                if (!response.ok) {
                    const detail =
                        result.detail ||
                        result.processing_details?.error ||
                        `HTTP ${response.status}`;
                    throw new Error(
                        typeof detail === 'string' ? detail : JSON.stringify(detail)
                    );
                }

                if (result.success) {
                    generatedContent = result.video_metadata;
                    updateContentPreview();
                    showNotification('内容生成成功', 'success');
                } else {
                    throw new Error(
                        result.processing_details?.error ||
                            result.message ||
                            '内容生成失败'
                    );
                }
            } catch (error) {
                showNotification(`生成内容失败: ${error.message}`, 'error');
                console.error('重新生成内容失败:', error);
            }
        }

        // 更新内容预览
        function updateContentPreview() {
            console.log('更新内容预览:', generatedContent);
            if (!generatedContent) return;

            const rawTitle = (generatedContent.title || '').trim();
            const nl = rawTitle.indexOf('\n');
            const line1El = document.getElementById('generated-main-line1');
            const line2El = document.getElementById('generated-main-line2');
            if (line1El && line2El) {
                if (nl >= 0) {
                    line1El.value = rawTitle.slice(0, nl).trim();
                    line2El.value = rawTitle.slice(nl + 1).trim();
                } else {
                    line1El.value = rawTitle;
                    line2El.value = '';
                }
            }
            document.getElementById('generated-subtitle').textContent = generatedContent.subtitle || '';
            const sub2El = document.getElementById('generated-subtitle2');
            if (sub2El) sub2El.textContent = generatedContent.subtitle2 || '';
            document.getElementById('generated-summary').textContent = generatedContent.summary;
            
            const tagsContainer = document.getElementById('generated-tags');
            tagsContainer.innerHTML = generatedContent.tags.map(tag =>
                `<span style="background: #0366d6; color: white; padding: 4px 8px; border-radius: 12px; margin: 2px; font-size: 12px;">${tag}</span>`
            ).join(' ');

            const insight = document.getElementById('github-methodology-insight');
            const audEl = document.getElementById('github-target-audience');
            const praiseEl = document.getElementById('github-praise-tags');
            const hookEl = document.getElementById('github-traffic-hook');
            const aud = (generatedContent.target_audience || '').toString().trim();
            const hook = (generatedContent.traffic_hook || '').toString().trim();
            const tags = Array.isArray(generatedContent.praise_tags)
                ? generatedContent.praise_tags.map(t => (t || '').toString().trim()).filter(Boolean)
                : [];
            if (audEl) audEl.textContent = aud || '—';
            if (praiseEl) praiseEl.textContent = tags.length ? tags.join(' · ') : '—';
            if (hookEl) hookEl.textContent = hook || '—';
            if (insight) insight.style.display = (aud || tags.length || hook) ? 'block' : 'none';
        }

        // 重新生成内容
        // 注意：这个监听器会在页面初始化时绑定
        if (document.getElementById('regenerate-btn')) {
            document.getElementById('regenerate-btn').addEventListener('click', async () => {
                console.log('重新生成按钮被点击');
                await generateContent();
            });
        }

        // 确认内容后进入第四步：选择 BGM、背景图后再生成
        document.getElementById('confirm-content-btn').addEventListener('click', async () => {
            updateStep(4);
            const step4Opts = document.getElementById('step4-options');
            const videoResult = document.getElementById('video-result');
            const loading = document.getElementById('video-generation-loading');
            if (step4Opts) step4Opts.classList.remove('hidden');
            if (videoResult) videoResult.classList.add('hidden');
            if (loading) loading.style.display = 'none';
            await loadGithubBGMList();
            await loadBackgroundImageList();
            await loadGithubTitleFontList();
        });

        // 实际的视频生成函数
        async function generateActualVideo() {
            const loading = document.getElementById('video-generation-loading');
            const result = document.getElementById('video-result');
            const step4Opts = document.getElementById('step4-options');
            if (step4Opts) step4Opts.classList.add('hidden');

            loading.style.display = 'block';
            result.classList.add('hidden');
            
            try {
                // 获取编辑后的内容（主标题两行 + 与内容生成一致的合并标题）
                const ml1 = document.getElementById('generated-main-line1')?.value.trim() || '';
                const ml2 = document.getElementById('generated-main-line2')?.value.trim() || '';
                const combinedTitle = [ml1, ml2].filter(Boolean).join('\n');
                const subtitle = document.getElementById('generated-subtitle').textContent.trim();
                const subtitle2 = (document.getElementById('generated-subtitle2')?.textContent || '').trim();
                const summary = document.getElementById('generated-summary').textContent.trim();
                const titleFontKey =
                    document.getElementById('github-title-font-select')?.value || 'msyhbd';
                
                const includeAudio = document.getElementById('include-audio').checked;
                const bgmSelect = document.getElementById('github-bgm-select');
                const selectedBgm =
                    bgmSelect && bgmSelect.value
                        ? bgmSelect.value.trim()
                        : 'static/music/background.mp3';
                const bgSelect = document.getElementById('github-background-select');
                const backgroundPath =
                    bgSelect && bgSelect.value
                        ? bgSelect.value.trim()
                        : 'static/imgs/bg.png';

                const requestData = {
                    project_id: currentProjectId,
                    custom_title: combinedTitle || undefined,
                    custom_summary: summary || undefined,
                    custom_main_line1: ml1,
                    custom_main_line2: ml2,
                    custom_subtitle2: subtitle2 || undefined,
                    title_font_key: titleFontKey,
                    include_audio: includeAudio,
                    background_image_path: backgroundPath,
                    image_sequence: selectedImageItems.map(({ id, duration }) => ({
                        id,
                        duration: Number(duration)
                    }))
                };
                if (includeAudio) {
                    requestData.audio_path = selectedBgm;
                }
                
                console.log('发送视频生成请求:', requestData);
                
                // 调用视频生成API
                const response = await fetch(`${API_BASE}/generate-video`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(requestData)
                });
                
                const data = await response.json();
                console.log('视频生成响应:', data);
                
                if (data.success) {
                    loading.style.display = 'none';
                    result.classList.remove('hidden');
                    showNotification('基底视频生成成功（画面不含摘要文字）', 'success');

                    baseVideoPath =
                        (data.processing_details && data.processing_details.video_path) || null;
                    window.__ghBaseVideoPath = baseVideoPath;
                    
                    // 显示视频信息和预览
                    const videoPlayer = document.getElementById('video-player');
                    videoPlayer.innerHTML = `
                        <div class="video-info">
                            <h3>生成的视频信息</h3>
                            <p><strong>标题:</strong> ${data.video_metadata.title}</p>
                            <p><strong>摘要:</strong> ${(data.video_metadata.summary || '').substring(0, 120)}${(data.video_metadata.summary || '').length > 120 ? '…' : ''}</p>
                            <p><strong>标签:</strong> ${data.video_metadata.tags.join(', ')}</p>
                            <p><strong>项目ID:</strong> ${data.project_id}</p>
                            <p class="github-hint" style="margin-top:8px;">摘要仅用于第五步口播；当前成片未在画面上叠加摘要。</p>
                        </div>
                    `;
                    
                    showVideoPreview(data.project_id, baseVideoPath);
                } else {
                    throw new Error(data.message || '视频生成失败');
                }
                
            } catch (error) {
                console.error('视频生成错误:', error);
                loading.style.display = 'none';
                showNotification(`视频生成失败: ${error.message}`, 'error');
                if (step4Opts) step4Opts.classList.remove('hidden');
                updateStep(4);
            }
        }

        // 显示视频预览（explicitUrl 为第四步返回的 /data/videos/... 时优先使用）
        function showVideoPreview(projectId, explicitUrl) {
            const previewArea = document.getElementById('video-preview-area');
            
            // 清空预览区域
            previewArea.innerHTML = `
                <div class="preview-placeholder">
                    <div class="spinner"></div>
                    <p>正在加载视频预览...</p>
                </div>
            `;
            
            // 创建视频元素
            const videoElement = document.createElement('video');
            videoElement.controls = true;
            videoElement.autoplay = false;
            videoElement.preload = 'metadata';
            videoElement.style.display = 'none';
            
            const videoUrl = explicitUrl || `${API_BASE}/projects/${projectId}/video`;
            videoElement.src = videoUrl;
            
            // 视频加载成功后显示
            videoElement.addEventListener('loadeddata', () => {
                previewArea.innerHTML = '';
                videoElement.style.display = 'block';
                previewArea.appendChild(videoElement);
                
                // 添加播放控制提示
                const controlsHint = document.createElement('div');
                controlsHint.className = 'video-controls-hint';
                controlsHint.innerHTML = '点击播放按钮开始观看';
                previewArea.appendChild(controlsHint);
            });
            
            // 视频加载失败处理
            videoElement.addEventListener('error', (e) => {
                console.error('视频加载失败:', e);
                previewArea.innerHTML = `
                    <div class="preview-placeholder">
                        <div class="preview-icon">❌</div>
                        <p>视频加载失败</p>
                        <small>请尝试重新生成或下载视频</small>
                        <button onclick="retryVideoPreview('${projectId}')" class="btn btn-outline" style="margin-top: 10px;">
                            重试加载
                        </button>
                    </div>
                `;
            });
        }
        
        // 重试视频预览
        function retryVideoPreview(projectId) {
            showVideoPreview(projectId, window.__ghBaseVideoPath || null);
        }
        function downloadGeneratedVideo(projectId) {
            const videoUrl = `${API_BASE}/projects/${projectId}/video`;
            
            // 创建下载链接
            const link = document.createElement('a');
            link.href = videoUrl;
            link.download = `github_project_${projectId}.mp4`;
            link.style.display = 'none';
            
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            showNotification('开始下载视频...', 'info');
        }

        // 下载基底视频
        document.getElementById('download-btn').addEventListener('click', () => {
            if (baseVideoPath) {
                const a = document.createElement('a');
                a.href = baseVideoPath;
                a.download = `github_base_${currentProjectId || 'video'}.mp4`;
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                showNotification('开始下载基底视频…', 'info');
            } else if (currentProjectId) {
                downloadGeneratedVideo(currentProjectId);
            } else {
                showNotification('暂无视频可下载', 'warning');
            }
        });

        document.getElementById('go-step5-btn').addEventListener('click', () => {
            const ta = document.getElementById('voiceover-script');
            if (ta && generatedContent && generatedContent.summary && !ta.value.trim()) {
                ta.value = generatedContent.summary;
            }
            updateStep(5);
        });

        document.getElementById('fill-summary-voiceover-btn').addEventListener('click', () => {
            const ta = document.getElementById('voiceover-script');
            const sumEl = document.getElementById('generated-summary');
            if (ta && sumEl) {
                ta.value = sumEl.textContent.trim();
                showNotification('已填入摘要', 'success');
            }
        });

        document.getElementById('voiceover-generate-btn').addEventListener('click', async () => {
            const script = document.getElementById('voiceover-script').value.trim();
            if (!script) {
                showNotification('请填写口播稿', 'warning');
                return;
            }
            if (!baseVideoPath) {
                showNotification('缺少基底视频路径，请先在第四步重新生成视频', 'error');
                return;
            }
            const loading = document.getElementById('voiceover-loading');
            const resBox = document.getElementById('voiceover-result');
            loading.style.display = 'block';
            resBox.classList.add('hidden');
            try {
                const voiceCloneAudioPath = await ensureGithubVoiceCloneAudioUploaded();
                const response = await fetch(`${API_BASE}/projects/${currentProjectId}/voiceover`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        base_video_path: baseVideoPath,
                        script,
                        voice_clone_audio_path: voiceCloneAudioPath,
                        mix_bgm: document.getElementById('voiceover-mix-bgm').checked,
                        bgm_gain_db: Math.min(
                            6,
                            Math.max(
                                -45,
                                parseFloat(document.getElementById('voiceover-bgm-gain')?.value) || -22
                            )
                        ),
                        narration_gain_db: Math.min(
                            24,
                            Math.max(
                                -24,
                                parseFloat(document.getElementById('voiceover-narration-gain')?.value) || 0
                            )
                        ),
                        burn_subtitles: document.getElementById('voiceover-burn').checked,
                        tts_rate: document.getElementById('voiceover-rate')?.value || '+25%',
                        subtitle_fontname:
                            document.getElementById('voiceover-subtitle-font')?.value?.trim() ||
                            'Microsoft YaHei',
                        subtitle_margin_bottom_percent: Math.min(
                            45,
                            Math.max(
                                8,
                                parseFloat(
                                    document.getElementById('voiceover-subtitle-margin-pct')?.value || '11'
                                ) || 11
                            )
                        ),
                        subtitle_margin_left_percent: Math.min(
                            45,
                            Math.max(
                                0,
                                (() => {
                                    const v = parseFloat(
                                        document.getElementById('voiceover-subtitle-left-pct')?.value ?? '4.5'
                                    );
                                    return Number.isFinite(v) ? v : 4.5;
                                })()
                            )
                        ),
                        subtitle_fontsize: Math.min(
                            36,
                            Math.max(
                                10,
                                parseInt(
                                    document.getElementById('voiceover-subtitle-size')?.value || '16',
                                    10
                                ) || 16
                            )
                        ),
                        subtitle_max_chars: Math.min(
                            40,
                            Math.max(
                                8,
                                parseInt(
                                    document.getElementById('voiceover-subtitle-max-chars')?.value || '20',
                                    10
                                ) || 20
                            )
                        )
                    })
                });
                let data = {};
                try {
                    data = await response.json();
                } catch (_) {
                    data = {};
                }
                if (!response.ok) {
                    const detail = data.detail;
                    const msg =
                        typeof detail === 'string'
                            ? detail
                            : Array.isArray(detail)
                              ? detail.map((x) => x.msg || JSON.stringify(x)).join('; ')
                              : data.message || JSON.stringify(data) || response.statusText;
                    throw new Error(msg);
                }
                if (data.success && data.final_video_path) {
                    finalVoiceoverUrl = data.final_video_path;
                    loading.style.display = 'none';
                    resBox.classList.remove('hidden');
                    const prev = document.getElementById('voiceover-preview-area');
                    prev.innerHTML = '';
                    const v = document.createElement('video');
                    v.controls = true;
                    v.style.maxWidth = '100%';
                    v.src = data.final_video_path;
                    prev.appendChild(v);
                    const dl = document.getElementById('voiceover-download-final');
                    dl.href = data.final_video_path;
                    dl.download = `github_voiceover_${currentProjectId}.mp4`;
                    const srtA = document.getElementById('voiceover-download-srt');
                    if (data.srt_path) {
                        srtA.href = data.srt_path;
                        srtA.download = `github_${currentProjectId}.srt`;
                        srtA.style.display = 'inline-block';
                    } else {
                        srtA.style.display = 'none';
                    }
                    showNotification('配音与字幕成片已生成', 'success');
                } else {
                    throw new Error(data.message || '生成失败');
                }
            } catch (e) {
                loading.style.display = 'none';
                showNotification(`配音生成失败: ${e.message}`, 'error');
            }
        });

        // 处理新项目
        document.getElementById('new-project-btn').addEventListener('click', () => {
            currentProjectId = null;
            imageCatalog.clear();
            selectedImageItems = [];
            generatedContent = null;
            baseVideoPath = null;
            window.__ghBaseVideoPath = null;
            finalVoiceoverUrl = null;
            closeGithubSortPanel();
            closeGhLightbox();

            document.getElementById('github-url').value = '';
            document.getElementById('image-grid').innerHTML = '';
            const voTa = document.getElementById('voiceover-script');
            if (voTa) voTa.value = '';
            const vor = document.getElementById('voiceover-result');
            if (vor) vor.classList.add('hidden');

            updateStep(1);
        });

        // 全选/取消全选功能
        document.getElementById('select-all-btn').addEventListener('click', () => {
            document.querySelectorAll('.image-item').forEach(item => {
                item.classList.add('selected');
            });
            syncSelectedImageItemsFromDom();
        });

        document.getElementById('select-none-btn').addEventListener('click', () => {
            document.querySelectorAll('.image-item').forEach(item => {
                item.classList.remove('selected');
            });
            syncSelectedImageItemsFromDom();
        });

        const refreshShotBtn = document.getElementById('refresh-github-screenshot-btn');
        if (refreshShotBtn) {
            refreshShotBtn.addEventListener('click', async () => {
                if (!currentProjectId) {
                    showNotification('请先完成第一步处理项目', 'warning');
                    return;
                }
                refreshShotBtn.disabled = true;
                const oldText = refreshShotBtn.textContent;
                refreshShotBtn.textContent = '正在截图…';
                try {
                    const response = await fetch(
                        `${API_BASE}/projects/${encodeURIComponent(currentProjectId)}/refresh-screenshot`,
                        { method: 'POST' }
                    );
                    let data = {};
                    try {
                        data = await response.json();
                    } catch (_) {
                        data = {};
                    }
                    if (!response.ok) {
                        const d = data.detail;
                        const msg =
                            typeof d === 'string'
                                ? d
                                : Array.isArray(d)
                                  ? d.map((x) => x.msg || JSON.stringify(x)).join('; ')
                                  : data.message || response.statusText;
                        throw new Error(msg);
                    }
                    if (data.success) {
                        showNotification(data.message || '主页截图已更新', 'success');
                        await loadProjectImages();
                    } else {
                        throw new Error(data.message || '刷新失败');
                    }
                } catch (e) {
                    showNotification(`刷新主页截图失败: ${e.message}`, 'error');
                } finally {
                    refreshShotBtn.disabled = false;
                    refreshShotBtn.textContent = oldText;
                }
            });
        }

        const openSortBtn = document.getElementById('open-sort-panel-btn');
        if (openSortBtn) {
            openSortBtn.addEventListener('click', () => {
                syncSelectedImageItemsFromDom();
                if (selectedImageItems.length === 0) {
                    showNotification('请先选择至少一段素材（图片或 README 视频）', 'warning');
                    return;
                }
                updateGithubSortPanel();
                const p = document.getElementById('githubSortPanel');
                if (p) {
                    p.classList.add('is-open');
                    p.setAttribute('aria-hidden', 'false');
                }
            });
        }

        const closeSortBtn = document.getElementById('close-github-sort-panel');
        if (closeSortBtn) {
            closeSortBtn.addEventListener('click', () => closeGithubSortPanel());
        }

        const ghLbClose = document.getElementById('ghLightboxClose');
        if (ghLbClose) {
            ghLbClose.addEventListener('click', () => closeGhLightbox());
        }
        const ghLb = document.getElementById('ghImageLightbox');
        if (ghLb) {
            ghLb.addEventListener('click', (e) => {
                if (e.target === ghLb) closeGhLightbox();
            });
        }
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeGhLightbox();
                closeGithubSortPanel();
            }
        });

        function syncGithubBgmSelectDisabled() {
            const cb = document.getElementById('include-audio');
            const sel = document.getElementById('github-bgm-select');
            if (cb && sel) sel.disabled = !cb.checked;
        }

        async function loadBackgroundImageList() {
            const sel = document.getElementById('github-background-select');
            if (!sel) return;
            const current = sel.value;
            try {
                const response = await fetch('/api/list-background-images');
                const data = await response.json();
                if (data.success && Array.isArray(data.files) && data.files.length) {
                    sel.innerHTML = '';
                    data.files.forEach((f) => {
                        const opt = document.createElement('option');
                        opt.value = f.path;
                        opt.textContent = f.name || f.path.split('/').pop();
                        sel.appendChild(opt);
                    });
                    if (current && [...sel.options].some((o) => o.value === current)) {
                        sel.value = current;
                    }
                }
            } catch (e) {
                console.error('加载背景图列表失败:', e);
            }
        }

        async function loadGithubBGMList() {
            const bgmSelect = document.getElementById('github-bgm-select');
            if (!bgmSelect) return;
            try {
                const response = await fetch('/api/list-music-files');
                const data = await response.json();
                if (data.success && Array.isArray(data.files)) {
                    while (bgmSelect.options.length > 1) {
                        bgmSelect.remove(1);
                    }
                    data.files.forEach(file => {
                        const option = document.createElement('option');
                        option.value = file.path;
                        option.textContent = file.name || file.path.split('/').pop();
                        bgmSelect.appendChild(option);
                    });
                }
            } catch (error) {
                console.error('加载 BGM 列表失败:', error);
                const fallbackFiles = [
                    { path: 'static/music/background.mp3', name: '🎵 默认背景音乐' },
                    { path: 'static/music/background3.mp3', name: '🎵 背景音乐 3' },
                    { path: 'static/music/background4.mp3', name: '🎵 背景音乐 4' }
                ];
                while (bgmSelect.options.length > 1) {
                    bgmSelect.remove(1);
                }
                fallbackFiles.forEach(file => {
                    const option = document.createElement('option');
                    option.value = file.path;
                    option.textContent = file.name;
                    bgmSelect.appendChild(option);
                });
            }
        }

        const includeAudioCb = document.getElementById('include-audio');
        if (includeAudioCb) {
            includeAudioCb.addEventListener('change', syncGithubBgmSelectDisabled);
        }
        async function loadGithubTitleFontList() {
            const sel = document.getElementById('github-title-font-select');
            if (!sel) return;
            const current = sel.value;
            try {
                const response = await fetch('/api/list-title-fonts');
                const data = await response.json();
                if (data.success && Array.isArray(data.fonts) && data.fonts.length) {
                    sel.innerHTML = '';
                    data.fonts.forEach((f) => {
                        const opt = document.createElement('option');
                        opt.value = f.key;
                        opt.textContent = f.label || f.key;
                        sel.appendChild(opt);
                    });
                    if (current && [...sel.options].some((o) => o.value === current)) {
                        sel.value = current;
                    }
                }
            } catch (e) {
                console.error('加载主标题字体列表失败:', e);
            }
        }

        loadGithubBGMList();
        loadBackgroundImageList();
        loadGithubTitleFontList();
        syncGithubBgmSelectDisabled();

        const startGenBtn = document.getElementById('start-generate-video-btn');
        if (startGenBtn) {
            startGenBtn.addEventListener('click', () => generateActualVideo());
        }
        const step4RegenBtn = document.getElementById('step4-regenerate-settings-btn');
        if (step4RegenBtn) {
            step4RegenBtn.addEventListener('click', () => {
                const vr = document.getElementById('video-result');
                const so = document.getElementById('step4-options');
                if (vr) vr.classList.add('hidden');
                if (so) so.classList.remove('hidden');
                updateStep(4);
            });
        }
        const bgUpBtn = document.getElementById('github-background-upload-btn');
        if (bgUpBtn) {
            bgUpBtn.addEventListener('click', async () => {
                const input = document.getElementById('github-background-file');
                if (!input || !input.files || !input.files[0]) {
                    showNotification('请先选择图片文件', 'warning');
                    return;
                }
                const fd = new FormData();
                fd.append('image', input.files[0]);
                try {
                    const res = await fetch('/api/upload-background-image', {
                        method: 'POST',
                        body: fd
                    });
                    const data = await res.json();
                    if (!res.ok) {
                        const d = data.detail;
                        throw new Error(typeof d === 'string' ? d : JSON.stringify(d));
                    }
                    if (data.success && data.path) {
                        showNotification('背景图已上传', 'success');
                        await loadBackgroundImageList();
                        const s = document.getElementById('github-background-select');
                        if (s) s.value = data.path;
                    } else {
                        throw new Error(data.message || '上传失败');
                    }
                } catch (e) {
                    showNotification(`上传失败: ${e.message}`, 'error');
                }
            });
        }

        async function loadGithubSubtitleFonts() {
            const sel = document.getElementById('voiceover-subtitle-font');
            if (!sel) return;
            const fallback = [
                { fontname: 'Microsoft YaHei', label: '微软雅黑（系统）' },
                { fontname: 'SimHei', label: '黑体 SimHei（系统）' },
                { fontname: 'SimSun', label: '宋体 SimSun（系统）' },
                { fontname: 'KaiTi', label: '楷体 KaiTi（系统）' },
                { fontname: 'Microsoft JhengHei', label: '微软正黑（系统）' },
                { fontname: 'DengXian', label: '等线 DengXian（系统）' },
            ];
            const current = sel.value;
            try {
                const response = await fetch('/api/list-subtitle-fonts');
                const data = await response.json();
                if (data.success && Array.isArray(data.fonts) && data.fonts.length) {
                    sel.innerHTML = '';
                    data.fonts.forEach((f) => {
                        const opt = document.createElement('option');
                        opt.value = f.fontname;
                        opt.textContent = f.label || f.fontname;
                        sel.appendChild(opt);
                    });
                    if (current && [...sel.options].some((o) => o.value === current)) {
                        sel.value = current;
                    } else {
                        sel.value = 'Microsoft YaHei';
                    }
                    return;
                }
            } catch (e) {
                console.error('加载字幕字体列表失败:', e);
            }
            sel.innerHTML = '';
            fallback.forEach((f) => {
                const opt = document.createElement('option');
                opt.value = f.fontname;
                opt.textContent = f.label;
                sel.appendChild(opt);
            });
        }
        loadGithubSubtitleFonts();

        // 初始化
        updateStep(1);
