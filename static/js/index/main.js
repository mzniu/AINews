        function showToast(message, type = 'success', duration = 3500) {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            
            const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
            toast.innerHTML = `<div class="toast-title">${icon} ${type === 'success' ? '成功' : type === 'error' ? '失败' : '提示'}</div><div class="toast-body">${message}</div>`;
            
            container.appendChild(toast);
            requestAnimationFrame(() => toast.classList.add('show'));
            
            setTimeout(() => {
                toast.classList.remove('show');
                toast.classList.add('hiding');
                setTimeout(() => toast.remove(), 400);
            }, duration);
        }

        function getTitleFontKey() {
            const el = document.getElementById('titleFontSelect');
            return el && el.value ? el.value : 'msyhbd';
        }

        function getShowSummaryOnVideo() {
            const el = document.getElementById('indexShowSummaryOnVideo');
            return el ? el.checked : true;
        }

        function getVoiceoverLengthParams() {
            const minEl = document.getElementById('voiceoverMinChars');
            const maxEl = document.getElementById('voiceoverMaxChars');
            let min = parseInt(minEl && minEl.value, 10);
            let max = parseInt(maxEl && maxEl.value, 10);
            if (!Number.isFinite(min)) min = 120;
            if (!Number.isFinite(max)) max = 400;
            min = Math.max(20, Math.min(4000, min));
            max = Math.max(20, Math.min(8000, max));
            if (min > max) {
                const t = min;
                min = max;
                max = t;
            }
            return { voiceover_min_chars: min, voiceover_max_chars: max };
        }

        function onIndexBaseVideoReady(videoPath) {
            if (!videoPath) return;
            window.__indexBaseVideoPath = videoPath;
            const sec = document.getElementById('indexVoiceoverSection');
            if (sec) sec.style.display = 'block';
            const ta = document.getElementById('indexVoiceoverScript');
            if (ta && !ta.value.trim()) {
                const voEl = document.getElementById('editableVoiceoverScript');
                const sumEl = document.getElementById('editableAiSummary');
                if (voEl && voEl.value.trim()) ta.value = voEl.value.trim();
                else if (sumEl && sumEl.value.trim()) ta.value = sumEl.value.trim();
            }
        }

        function fillIndexVoiceoverFromSummary() {
            const ta = document.getElementById('indexVoiceoverScript');
            const voEl = document.getElementById('editableVoiceoverScript');
            const sumEl = document.getElementById('editableAiSummary');
            if (!ta) return;
            if (voEl && voEl.value.trim()) {
                ta.value = voEl.value.trim();
                showToast('已填入口播稿', 'success');
            } else if (sumEl && sumEl.value.trim()) {
                ta.value = sumEl.value.trim();
                showToast('已填入摘要', 'success');
            } else {
                showToast('请先在上方生成或填写口播稿/摘要', 'error');
            }
        }

        async function ensureIndexVoiceCloneAudioUploaded() {
            const fileInput = document.getElementById('indexVoiceoverCloneAudio');
            const pathInput = document.getElementById('indexVoiceoverCloneAudioPath');
            const status = document.getElementById('indexVoiceoverCloneAudioStatus');
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

        async function generateIndexVoiceover() {
            const script = document.getElementById('indexVoiceoverScript')?.value.trim();
            if (!script) {
                showToast('请填写口播稿', 'error');
                return;
            }
            const base = window.__indexBaseVideoPath;
            if (!base) {
                showToast('请先生成基底视频', 'error');
                return;
            }
            const loading = document.getElementById('indexVoiceoverLoading');
            const resBox = document.getElementById('indexVoiceoverResult');
            const btn = document.getElementById('indexVoiceoverGenerateBtn');
            if (loading) loading.style.display = 'block';
            if (resBox) resBox.style.display = 'none';
            if (btn) btn.disabled = true;
            try {
                const voiceCloneAudioPath = await ensureIndexVoiceCloneAudioUploaded();
                const response = await fetch('/api/render-voiceover', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        base_video_path: base,
                        script,
                        voice_clone_audio_path: voiceCloneAudioPath,
                        mix_bgm: document.getElementById('indexVoiceoverMixBgm').checked,
                        bgm_gain_db: Math.min(
                            6,
                            Math.max(
                                -45,
                                parseFloat(document.getElementById('indexVoiceoverBgmGain')?.value) || -22
                            )
                        ),
                        narration_gain_db: Math.min(
                            24,
                            Math.max(
                                -24,
                                parseFloat(document.getElementById('indexVoiceoverNarrationGain')?.value) || 0
                            )
                        ),
                        burn_subtitles: document.getElementById('indexVoiceoverBurn').checked,
                        tts_rate: document.getElementById('indexVoiceoverRate')?.value || '+25%',
                        subtitle_fontname:
                            document.getElementById('indexVoiceoverSubtitleFont')?.value?.trim() ||
                            'Microsoft YaHei',
                        subtitle_margin_bottom_percent: Math.min(
                            45,
                            Math.max(
                                8,
                                parseFloat(
                                    document.getElementById('indexVoiceoverSubtitleMarginPct')?.value || '11'
                                ) || 11
                            )
                        ),
                        subtitle_fontsize: Math.min(
                            36,
                            Math.max(
                                10,
                                parseInt(
                                    document.getElementById('indexVoiceoverSubtitleSize')?.value || '16',
                                    10
                                ) || 16
                            )
                        ),
                        subtitle_max_chars: Math.min(
                            40,
                            Math.max(
                                8,
                                parseInt(
                                    document.getElementById('indexVoiceoverSubtitleMaxChars')?.value || '20',
                                    10
                                ) || 20
                            )
                        ),
                    }),
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
                    if (loading) loading.style.display = 'none';
                    if (resBox) resBox.style.display = 'block';
                    const prev = document.getElementById('indexVoiceoverPreviewArea');
                    if (prev) {
                        prev.innerHTML = '';
                        const v = document.createElement('video');
                        v.controls = true;
                        v.style.maxWidth = '100%';
                        v.src = data.final_video_path;
                        prev.appendChild(v);
                    }
                    const dl = document.getElementById('indexVoiceoverDownloadFinal');
                    if (dl) {
                        dl.href = data.final_video_path;
                        dl.download = `ainews_voiceover_${Date.now()}.mp4`;
                    }
                    const srtA = document.getElementById('indexVoiceoverDownloadSrt');
                    if (data.srt_path && srtA) {
                        srtA.href = data.srt_path;
                        srtA.download = `ainews_${Date.now()}.srt`;
                        srtA.style.display = 'inline-block';
                    } else if (srtA) {
                        srtA.style.display = 'none';
                    }
                    showToast('配音与字幕成片已生成', 'success');
                } else {
                    throw new Error(data.message || '生成失败');
                }
            } catch (e) {
                if (loading) loading.style.display = 'none';
                showToast(`配音生成失败: ${e.message}`, 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        function isVideoPath(p) {
            if (!p || typeof p !== 'string') return false;
            return /\.(mp4|webm|mov|avi|mkv)$/i.test(p);
        }

        /** 识别 GIF 路径（忽略 ?query / #hash，大小写不敏感） */
        function isGifPath(p) {
            if (!p || typeof p !== 'string') return false;
            const pathOnly = p.split(/[?#]/)[0];
            return /\.gif$/i.test(pathOnly);
        }

        /** WebP（含动画与静态；预转 MP4 时一并处理） */
        function isWebpPath(p) {
            if (!p || typeof p !== 'string') return false;
            const pathOnly = p.split(/[?#]/)[0];
            return /\.webp$/i.test(pathOnly);
        }

        /** 需先转 MP4 再参与画中画：GIF 或 WebP（与后端 batch-process 一致） */
        function needsAnimationPreconvertPath(p) {
            return isGifPath(p) || isWebpPath(p);
        }

        /** 与后端返回的 data/... 路径对齐，便于 URL 与比对 */
        function normalizeServerMediaPath(p) {
            if (p == null || p === '') return p;
            let s = String(p).replace(/\\/g, '/');
            if (s.startsWith('/')) return s;
            return '/' + s;
        }

        /**
         * GIF/WebP 批量转 MP4 成功后，必须把 selectedImages 中的原路径换成 .mp4，
         * 否则成片仍走服务端多帧动画分支；转 MP4 后走画中画（is_video）。
         */
        function applyGifBatchResultsToSelectedImages(results) {
            if (!Array.isArray(results)) return;
            for (const r of results) {
                if (!r || r.status !== 'success' || !r.video_path || !r.original_path) continue;
                const newPath = normalizeServerMediaPath(r.video_path);
                const origNorm = normalizeServerMediaPath(r.original_path);
                const idx = selectedImages.findIndex(
                    (o) => normalizeServerMediaPath(o.path) === origNorm
                );
                if (idx >= 0) {
                    selectedImages[idx] = {
                        ...selectedImages[idx],
                        path: newPath,
                        type: 'video',
                    };
                }
            }
        }

        /** 与 GitHub 成片排序面板一致：视频默认 3s，图片默认 2s；时长限制 0.5～30s */
        function normalizeSelectedClipDurations() {
            selectedImages.forEach((o) => {
                const vid = (o.type === 'video') || isVideoPath(o.path);
                const fallback = vid ? 3 : 2;
                let d = o.duration;
                if (d == null || d === '' || isNaN(Number(d))) {
                    o.duration = fallback;
                } else {
                    o.duration = Math.min(30, Math.max(0.5, Number(d)));
                }
            });
        }

        function buildClipPayloadForAnimatedVideo() {
            normalizeSelectedClipDurations();
            // 从排序面板输入框同步时长：仅 onchange 时用户改完数字未失焦就生成，仍会带默认约 2s，导致成片片段时长偏短
            document.querySelectorAll('.image-duration-input').forEach((inp) => {
                const path = inp.dataset.path;
                if (!path) return;
                const imgObj = selectedImages.find((img) => img.path === path);
                if (!imgObj) return;
                const raw = parseFloat(inp.value);
                if (!isNaN(raw)) {
                    imgObj.duration = Math.min(30, Math.max(0.5, raw));
                }
            });
            return selectedImages.map((imgObj) => ({
                path: imgObj.path,
                duration: Number(imgObj.duration),
            }));
        }

        
        // 排序面板功能
        function initSortPanel() {
            const panel = document.getElementById('sortPanel');
            if (selectedImages.length > 0) {
                panel.style.display = 'block';
                updateSortPanel();
            } else {
                panel.style.display = 'none';
            }
        }
        
        function updateSortPanel() {
            normalizeSelectedClipDurations();
            const container = document.getElementById('sortableList');
            container.innerHTML = '';
            
            selectedImages.forEach((imgObj, index) => {
                const item = createSortableItem(imgObj, index + 1);
                container.appendChild(item);
            });
            
            // 初始化拖拽功能
            initDragAndDrop();
        }
        
        function createSortableItem(imgObj, order) {
            const div = document.createElement('div');
            div.className = 'sortable-item';
            div.draggable = true;
            div.dataset.path = imgObj.path;
            
            // 提取文件名
            const fileName = imgObj.path.split('/').pop() || '媒体文件';
            const displayName = fileName.length > 15 ? fileName.substring(0, 12) + '...' : fileName;
            
            const isGif = isGifPath(imgObj.path);
            const isWebp = isWebpPath(imgObj.path);
            const isVideo = (imgObj.type === 'video') || isVideoPath(imgObj.path);
            
            let indicator = '';
            let fileType = 'image';
            
            if (isGif) {
                indicator = '<span class="sortable-gif-indicator">🎞️</span>';
                fileType = 'gif';
            } else if (isWebp) {
                indicator = '<span class="sortable-gif-indicator" title="WebP（动画会先转 MP4）">🖼️</span>';
                fileType = 'webp';
            } else if (isVideo) {
                indicator = '<span class="sortable-gif-indicator">🎥</span>';
                fileType = 'video';
            }
            
            const vid = isVideo;
            const fallback = vid ? 3 : 2;
            let durationVal = imgObj.duration;
            if (durationVal == null || durationVal === '' || isNaN(Number(durationVal))) {
                durationVal = fallback;
            } else {
                durationVal = Math.min(30, Math.max(0.5, Number(durationVal)));
            }

            const durationHtml = `
                    <div class="duration-config">
                        <input type="number" 
                               class="image-duration-input" 
                               value="${durationVal}" 
                               min="0.5" 
                               max="30" 
                               step="0.5"
                               data-path="${imgObj.path}"
                               oninput="updateImageDuration('${imgObj.path}', this.value)"
                               onchange="updateImageDuration('${imgObj.path}', this.value)">
                        <span class="duration-label">秒</span>
                    </div>
                `;

            const thumbHtml = isVideo
                ? `<video src="${imgObj.path}" muted playsinline preload="metadata" class="index-sort-thumb-video"></video>`
                : `<img src="${imgObj.path}" alt="选中媒体" 
                     onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22currentColor%22 stroke-width=%222%22><rect x=%223%22 y=%223%22 width=%2218%22 height=%2218%22 rx=%222%22/><circle cx=%228.5%22 cy=%228.5%22 r=%221.5%22/><path d=%22M21 15l-5-5L5 21%22/></svg>'">`;
            
            div.innerHTML = `
                <span class="order-number">${order}.</span>
                ${thumbHtml}
                ${indicator}
                <span class="filename" title="${fileName} (${fileType})">${displayName}</span>
                ${durationHtml}
            `;
            
            return div;
        }
        
        function initDragAndDrop() {
            const items = document.querySelectorAll('.sortable-item');
            
            items.forEach(item => {
                item.addEventListener('dragstart', handleDragStart);
                item.addEventListener('dragover', handleDragOver);
                item.addEventListener('drop', handleDrop);
                item.addEventListener('dragend', handleDragEnd);
            });
        }
        
        function handleDragStart(e) {
            dragSrcEl = this;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/html', this.outerHTML);
            this.classList.add('dragging');
        }
        
        function handleDragOver(e) {
            if (e.preventDefault) {
                e.preventDefault();
            }
            e.dataTransfer.dropEffect = 'move';
            
            // 添加视觉指示器
            if (this !== dragSrcEl) {
                this.classList.add('over');
            }
            
            return false;
        }
        
        function handleDrop(e) {
            if (e.stopPropagation) {
                e.stopPropagation();
            }
            
            if (dragSrcEl !== this) {
                // 交换元素位置
                const parent = dragSrcEl.parentNode;
                const dragIndex = Array.from(parent.children).indexOf(dragSrcEl);
                const dropIndex = Array.from(parent.children).indexOf(this);
                
                if (dragIndex < dropIndex) {
                    parent.insertBefore(dragSrcEl, this.nextSibling);
                } else {
                    parent.insertBefore(dragSrcEl, this);
                }
                
                // 更新selectedImages数组
                updateSelectedImagesFromSort();
                // 更新序号显示
                updateOrderNumbers();
                // 更新主图片区域序号
                updateMainImageNumbers();
            }
            
            return false;
        }
        
        function handleDragEnd() {
            this.classList.remove('dragging');
            document.querySelectorAll('.sortable-item').forEach(item => {
                item.classList.remove('over');
            });
            dragSrcEl = null;
        }
        
        function updateSelectedImagesFromSort() {
            const items = document.querySelectorAll('.sortable-item');
            // 保持对象结构，只更新路径顺序
            const newPathOrder = Array.from(items).map(item => item.dataset.path);
            
            // 根据新的路径顺序重新排列 selectedImages 数组
            const newSelectedImages = [];
            newPathOrder.forEach(path => {
                const imgObj = selectedImages.find(img => img.path === path);
                if (imgObj) {
                    newSelectedImages.push(imgObj);
                }
            });
            
            selectedImages = newSelectedImages;
            console.log('排序已更新:', selectedImages);
        }
        
        /**
         * 更新片段显示时长（与 GitHub 排序面板一致：0.5～30 秒）
         */
        function updateImageDuration(path, value) {
            const v = parseFloat(value);
            const imgObj = selectedImages.find(img => img.path === path);
            if (!imgObj || isNaN(v)) return;
            const clamped = Math.min(30, Math.max(0.5, v));
            imgObj.duration = clamped;
            document.querySelectorAll('.image-duration-input').forEach((inp) => {
                if (inp.dataset.path === path && String(clamped) !== inp.value) {
                    inp.value = String(clamped);
                }
            });
        }
        
        function updateOrderNumbers() {
            const items = document.querySelectorAll('.sortable-item');
            items.forEach((item, index) => {
                const numberSpan = item.querySelector('.order-number');
                if (numberSpan) {
                    numberSpan.textContent = `${index + 1}.`;
                }
            });
            
            // 同时更新主图片区域的序号
            updateMainImageNumbers();
        }
        
        function updateMainImageNumbers() {
            const selectedEls = document.querySelectorAll('.selectable-image.selected, .selectable-video.selected');
            selectedEls.forEach((mediaEl) => {
                const orderNumber = mediaEl.querySelector('.image-order-number');
                if (orderNumber) {
                    const p = mediaEl.dataset.path;
                    const arrayIndex = selectedImages.findIndex((img) => img.path === p);
                    if (arrayIndex !== -1) {
                        orderNumber.textContent = arrayIndex + 1;
                    }
                }
            });
        }
        
        function hideSortPanel() {
            const panel = document.getElementById('sortPanel');
            panel.style.display = 'none';
        }
        
        function resetImageOrder() {
            // 这里可以添加重置逻辑，比如按原始顺序重新排列
            showToast('顺序重置功能待实现', 'info');
        }
        
        function saveEditedContent() {
            // 保存用户编辑的内容
            editedMainLine1 = document.getElementById('editableMainLine1').value.trim();
            editedMainLine2 = document.getElementById('editableMainLine2').value.trim();
            editedSubTitle = document.getElementById('editableSubTitle').value.trim();
            editedSummary = document.getElementById('editableAiSummary').value.trim();
            const voEl = document.getElementById('editableVoiceoverScript');
            editedVoiceover = voEl ? voEl.value.trim() : '';
            editedTags = document.getElementById('editableAiTags').value.trim();
            
            if (!editedMainLine1 || !editedSummary) {
                showToast('请填写主标题第一行和摘要后再保存', 'error');
                return;
            }
            
            showToast('✅ 内容已保存，将在视频生成时使用', 'success');
            console.log('保存的编辑内容:', { editedMainLine1, editedMainLine2, editedSubTitle, editedSummary, editedVoiceover, editedTags });
        }
        
        // GIF 处理相关函数
        async function analyzeSelectedGIFs() {
            const gifImages = selectedImages.filter((imgObj) => isGifPath(imgObj.path));

            if (gifImages.length === 0) {
                showToast('没有选中的 GIF 图片', 'info');
                return;
            }
                    
            try {
                const analyses = [];
                for (const imgObj of gifImages) {
                    const response = await fetch(`/api/gif/analyze-gif?gif_path=${encodeURIComponent(imgObj.path)}`);
                    const result = await response.json();
                    if (result.success) {
                        analyses.push({
                            path: imgObj.path,
                            ...result
                        });
                    }
                }
                
                // 显示分析结果
                showGIFAnalysis(analyses);
                
            } catch (error) {
                console.error('GIF分析失败:', error);
                showToast('GIF分析失败: ' + error.message, 'error');
            }
        }
        
        function showGIFAnalysis(analyses) {
            let content = '<h3>🎞️ GIF分析结果</h3>';
            
            analyses.forEach(analysis => {
                const props = analysis.properties;
                const compat = analysis.analysis;
                
                content += `
                    <div style="margin: 15px 0; padding: 10px; border: 1px solid #eee; border-radius: 5px;">
                        <strong>${analysis.path.split('/').pop()}</strong><br>
                        帧数: ${props.frame_count || '未知'}<br>
                        时长: ${(props.duration ? props.duration/1000 : 0).toFixed(2)}秒<br>
                        尺寸: ${props.size ? `${props.size[0]}×${props.size[1]}` : '未知'}<br>
                        兼容性: ${compat.is_valid ? '✅ 良好' : '⚠️ 存在问题'}
                        ${compat.issues ? `<br>问题: ${compat.issues.join(', ')}` : ''}
                    </div>
                `;
            });
            
            showToast(content, 'info', 5000);
        }
        
        async function processSelectedGIFs(durationPerFrame = 2.5, options = {}) {
            const { silentIfEmpty = true } = options;
            const gifImages = selectedImages.filter((imgObj) =>
                needsAnimationPreconvertPath(imgObj.path)
            );

            if (gifImages.length === 0) {
                if (!silentIfEmpty) {
                    showToast('没有需要预转换的 GIF/WebP', 'info');
                }
                return [];
            }
                    
            try {
                // 批量处理 GIF
                const formData = new FormData();
                gifImages.forEach((imgObj) => formData.append('gif_paths', imgObj.path));
                formData.append('target_duration', durationPerFrame.toString());
                
                const response = await fetch('/api/gif/batch-process-gifs', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    applyGifBatchResultsToSelectedImages(result.results);
                    const successfulVideos = result.results
                        .filter(r => r.status === 'success')
                        .map(r => r.video_path);
                    
                    showToast(
                        `✅ 成功处理 ${successfulVideos.length}/${gifImages.length} 个 GIF/WebP`,
                        'success'
                    );
                    return successfulVideos;
                } else {
                    throw new Error(result.detail || '处理失败');
                }
                
            } catch (error) {
                console.error('GIF处理失败:', error);
                showToast('GIF处理失败: ' + error.message, 'error');
                return [];
            }
        }
        
        function copyAiContent(elementId) {
            const el = document.getElementById(elementId);
            if (!el) {
                showToast('未找到要复制的元素', 'error');
                return;
            }
            
            // 根据元素类型获取内容
            let text = '';
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                text = el.value.trim();
            } else {
                text = el.textContent.trim();
            }
            
            if (!text) {
                showToast('没有可复制的内容', 'info');
                return;
            }
            
            navigator.clipboard.writeText(text).then(() => {
                showToast('已复制到剪贴板', 'success', 2000);
            }).catch(() => {
                // fallback for older browsers
                const range = document.createRange();
                range.selectNodeContents(el);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('copy');
                sel.removeAllRanges();
                showToast('已复制到剪贴板', 'success', 2000);
            });
        }

        function toggleCollapse(header) {
            const body = header.nextElementSibling;
            header.classList.toggle('collapsed');
            body.classList.toggle('hidden');
        }

        function fillExample(url) {
            event.preventDefault();
            document.getElementById('urlInput').value = url;
        }

        // 视频列表：改为懒加载 —— 仅在用户首次展开「视频列表」折叠区时再请求 /api/list-videos，
        // 避免每次打开首页都扫描 data/videos/ 下数百个文件。
        window.addEventListener('DOMContentLoaded', function () {
            const section = document.getElementById('videosSection');
            if (!section) return;
            const header = section.previousElementSibling;
            if (!header || !header.classList.contains('collapsible-header')) return;
            let loaded = false;
            header.addEventListener('click', async () => {
                if (loaded) return;
                if (section.classList.contains('hidden')) return; // 仍处于收起状态（toggle 由 onclick 完成）
                loaded = true;
                await scanVideos();
            });
        });

        async function scanVideos() {
            try {
                const response = await fetch('/api/list-videos');
                const data = await response.json();
                
                if (data.success && data.videos && data.videos.length > 0) {
                    displayVideos(data.videos);
                }
            } catch (error) {
                console.error('扫描视频文件失败:', error);
            }
        }

        function displayVideos(videos) {
            const videosSection = document.getElementById('videosSection');
            const videosGrid = document.getElementById('videosGrid');
            
            if (!videosSection || !videosGrid) return;
            
            // 显示视频区域
            videosSection.style.display = 'block';
            videosGrid.innerHTML = '';
            
            videos.forEach(async (video, index) => {
                const videoCard = document.createElement('div');
                videoCard.className = 'video-card';
                videoCard.style.cssText = `
                    position: relative;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    transition: transform 0.2s;
                    background: white;
                `;
                
                // 构建初始HTML
                let videoHtml = `
                    <div style="position: relative; cursor: pointer;" onclick="openVideoModal('${video.local_path}')">
                `;
                
                // 根据是否有缩略图显示不同内容
                if (video.has_thumbnail && video.thumbnail_path) {
                    videoHtml += `
                        <img src="${video.thumbnail_path}" 
                             alt="视频封面" 
                             style="width: 100%; height: 150px; object-fit: cover; display: block;"
                             onerror="this.parentElement.innerHTML='<div style=\'width:100%;height:150px;background:linear-gradient(45deg,#667eea,#764ba2);display:flex;align-items:center;justify-content:center;\'><span style=\'color:white;font-size:48px;\'>🎬</span></div>'">
                        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.7); color: white; padding: 8px 12px; border-radius: 50%; font-size: 16px;">▶️</div>
                    `;
                } else {
                    // 默认渐变背景
                    videoHtml += `
                        <div style="width: 100%; height: 150px; background: linear-gradient(45deg, #667eea, #764ba2); display: flex; align-items: center; justify-content: center;">
                            <span style="color: white; font-size: 48px;">🎬</span>
                        </div>
                        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.7); color: white; padding: 8px 12px; border-radius: 50%; font-size: 16px;">▶️</div>
                    `;
                }
                
                videoHtml += `</div>`;
                
                // 信息部分
                videoHtml += `
                    <div style="padding: 10px;">
                        <div style="font-size: 13px; color: #666; margin-bottom: 4px; font-weight: 500;">${video.filename}</div>
                        <div style="font-size: 12px; color: #888; display: flex; justify-content: space-between;">
                            <span>${video.size_mb ? video.size_mb.toFixed(1) + 'MB' : '未知大小'}</span>
                            <span>${new Date(video.created_time).toLocaleDateString('zh-CN')}</span>
                        </div>
                    </div>
                    <div style="padding: 6px 10px; font-size: 12px; text-align: center; background: #d4edda; color: #155724; border-top: 1px solid #c3e6cb; display: flex; justify-content: space-between; align-items: center;">
                        <span>✓ 已生成</span>
                        <button onclick="event.stopPropagation(); openVideoModal('${video.local_path}')" 
                                style="background: #667eea; color: white; border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer;">
                            👁️ 查看
                        </button>
                    </div>
                `;
                
                videoCard.innerHTML = videoHtml;
                videosGrid.appendChild(videoCard);
                
                // 如果没有缩略图，尝试生成一个
                if (!video.has_thumbnail) {
                    try {
                        const response = await fetch(`/api/extract-thumbnail/${encodeURIComponent(video.filename)}`);
                        const result = await response.json();
                        if (result.success && result.thumbnail_path) {
                            // 更新卡片显示真实缩略图
                            const imgContainer = videoCard.querySelector('[onclick^="openVideoModal"]');
                            if (imgContainer) {
                                imgContainer.innerHTML = `
                                    <img src="${result.thumbnail_path}" 
                                         alt="视频封面" 
                                         style="width: 100%; height: 150px; object-fit: cover; display: block;"
                                         onerror="this.outerHTML='<div style=\\'width:100%;height:150px;background:linear-gradient(45deg,#667eea,#764ba2);display:flex;align-items:center;justify-content:center;\\'><span style=\\'color:white;font-size:48px;\\'>🎬</span></div>'">
                                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.7); color: white; padding: 8px 12px; border-radius: 50%; font-size: 16px;">▶️</div>
                                `;
                            }
                        }
                    } catch (error) {
                        console.log('缩略图生成失败:', error);
                    }
                }
            });
            
            console.log(`✅ 已显示 ${videos.length} 个视频文件`);
        }

        // 视频播放模态框
        function openVideoModal(videoPath) {
            const modal = document.createElement('div');
            modal.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.9);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
                backdrop-filter: blur(5px);
            `;
            
            modal.innerHTML = `
                <div style="position: relative; max-width: 90%; max-height: 90%;">
                    <button onclick="this.parentElement.parentElement.remove()" style="position: absolute; top: -40px; right: 0; background: white; border: none; border-radius: 50%; width: 30px; height: 30px; cursor: pointer; font-size: 18px; display: flex; align-items: center; justify-content: center;">×</button>
                    <video src="${videoPath}" controls autoplay style="max-width: 100%; max-height: 80vh; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);"></video>
                    <div style="text-align: center; margin-top: 15px; color: white; font-size: 14px;">
                        <a href="${videoPath}" download style="color: #667eea; text-decoration: none;">📥 下载视频</a>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // 点击背景关闭
            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    modal.remove();
                }
            });
        }

        // 模式切换功能
        function toggleFetchMode() {
            const checkbox = document.getElementById('fetchModeToggle');
            const manualSection = document.getElementById('manualInputSection');
            const urlInput = document.getElementById('urlInput');
            
            if (checkbox.checked) {
                // 手动粘贴模式
                manualSection.style.display = 'block';
                urlInput.disabled = true;
                urlInput.placeholder = '已切换到手动模式，请在下方粘贴内容...';
            } else {
                // 自动抓取模式
                manualSection.style.display = 'none';
                urlInput.disabled = false;
                urlInput.placeholder = '请输入网页 URL，例如：https://www.36kr.com/p/123456';
            }
        }
        
        // 处理手动粘贴的内容
        async function processManualContent() {
            const content = document.getElementById('manualContent').value.trim();
            
            if (!content) {
                alert('请先粘贴文章内容！');
                return;
            }
            
            // 显示加载状态
            document.getElementById('loading').style.display = 'block';
            document.getElementById('error').style.display = 'none';
            document.getElementById('result').classList.remove('active');
            
            try {
                // 调用后端 API 处理手动内容
                const response = await fetch('/api/process-manual-content', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        content: content,
                        url: '' // 可以提供原始 URL
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    displayResult(result);
                } else {
                    throw new Error(result.message || '处理失败');
                }
                
            } catch (error) {
                console.error('处理失败:', error);
                document.getElementById('error').textContent = `❌ 处理失败：${error.message}`;
                document.getElementById('error').style.display = 'block';
            } finally {
                document.getElementById('loading').style.display = 'none';
            }
        }
        
        async function fetchUrl() {
            const urlInput = document.getElementById('urlInput');
            const url = urlInput.value.trim();

            if (!url) {
                showError('请输入有效的URL');
                return;
            }

            // 验证URL格式
            try {
                new URL(url);
            } catch (e) {
                showError('URL格式不正确');
                return;
            }

            // 检查是否为VentureBeat URL，使用专门的API端点
            let apiUrl = '/api/fetch-url';
            if (url.includes('venturebeat.com')) {
                apiUrl = '/api/fetch-venturebeat';
                console.log('检测到VentureBeat URL，使用专门的API端点');
            }

            // 显示加载状态
            document.getElementById('loading').classList.add('active');
            document.getElementById('result').classList.remove('active');
            document.getElementById('error').classList.remove('active');
            document.getElementById('fetchBtn').disabled = true;

            try {
                const response = await fetch(apiUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ url: url })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || '抓取失败');
                }

                if (data.success) {
                    displayResult(data.data);
                } else {
                    showError(data.message);
                }

            } catch (error) {
                showError('抓取失败: ' + error.message);
            } finally {
                document.getElementById('loading').classList.remove('active');
                document.getElementById('fetchBtn').disabled = false;
            }
        }

        function displayResult(data) {
            currentData = data;
            selectedImages = [];

            // 显示结果区域
            document.getElementById('result').classList.add('active');

            // 填充基本信息（添加安全检查）
            const resultTitleEl = document.getElementById('resultTitle');
            const crawlTimeEl = document.getElementById('crawlTime');
            const contentLengthEl = document.getElementById('contentLength');
            const imagesCountEl = document.getElementById('imagesCount');
            const contentPreviewEl = document.getElementById('contentPreview');
            const downloadContentEl = document.getElementById('downloadContent');
            const downloadMetadataEl = document.getElementById('downloadMetadata');
            
            if (resultTitleEl) resultTitleEl.textContent = data.title || '未命名文章';
            if (crawlTimeEl) crawlTimeEl.textContent = data.timestamp ? new Date(data.timestamp).toLocaleString('zh-CN') : new Date().toLocaleString('zh-CN');
            if (contentLengthEl) contentLengthEl.textContent = (data.content ? data.content.length : 0).toLocaleString();
            if (imagesCountEl) imagesCountEl.textContent = (data.images ? data.images.length : 0);
            if (contentPreviewEl) contentPreviewEl.textContent = data.content ? data.content.substring(0, 500) + (data.content.length > 500 ? '...' : '') : '';
            // 手动模式不提供下载文件链接
            if (downloadContentEl) downloadContentEl.style.display = 'none';
            if (downloadMetadataEl) downloadMetadataEl.style.display = 'none';

            // 显示图片
            const imagesGrid = document.getElementById('imagesGrid');
            imagesGrid.innerHTML = '';

            if (data.images && data.images.length > 0) {
                data.images.forEach((img, index) => {
                    const imageCard = document.createElement('div');
                    imageCard.className = 'image-card';

                    // 手动模式下，图片只有 url，没有 local_path
                    const imgSrc = img.local_path || img.url || '';
                    const isDownloaded = !!img.local_path;
                    
                    imageCard.innerHTML = `
                        <img src="${imgSrc}" alt="${img.alt || '图片 ' + (index + 1)}" 
                             style="cursor:pointer;" 
                             onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22><rect fill=%22%23ddd%22 width=%22200%22 height=%22200%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%23999%22>加载失败</text></svg>'"
                             onclick="openImageModal(this.src, this)">
                        <div class="status ${isDownloaded ? 'success' : 'info'}" style="background: ${isDownloaded ? 'rgba(76, 175, 80, 0.9)' : 'rgba(33, 150, 243, 0.9)'}">
                            ${isDownloaded ? '✓ 已下载' : '🔗 URL'}
                        </div>
                    `;

                    imagesGrid.appendChild(imageCard);
                });
            } else {
                imagesGrid.innerHTML = '<p style="color: #999; text-align: center; padding: 40px;">未找到图片</p>';
            }
            
            // 显示视频（如果有的话）
            const videosSection = document.getElementById('videosSection');
            const videosGrid = document.getElementById('videosGrid');
            
            if (data.videos && data.videos.length > 0 && videosSection && videosGrid) {
                videosSection.style.display = 'block';
                videosGrid.innerHTML = '';
                
                data.videos.forEach((video, index) => {
                    const videoCard = document.createElement('div');
                    videoCard.className = 'video-card';
                    videoCard.style.cssText = `
                        position: relative;
                        border-radius: 8px;
                        overflow: hidden;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                        transition: transform 0.2s;
                    `;
                    
                    const videoSrc = video.local_path || video.url || '';
                    const isDownloaded = !!video.local_path;
                    
                    if (videoSrc) {
                        videoCard.innerHTML = `
                            <div style="position: relative; cursor: pointer;" onclick="${isDownloaded ? `openVideoModal('${videoSrc}')` : 'window.open(\'' + videoSrc + '\', \'_blank\')'}">
                                ${isDownloaded ? `<video src="${videoSrc}" muted style="width: 100%; height: 150px; object-fit: cover; display: block;"></video>` : `<div style="width: 100%; height: 150px; background: linear-gradient(45deg, #667eea, #764ba2); display: flex; align-items: center; justify-content: center;"><span style="color: white; font-size: 48px;">🎬</span></div>`}
                                <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.7); color: white; padding: 8px 12px; border-radius: 50%; font-size: 16px;">▶️</div>
                            </div>
                            <div style="padding: 10px;">
                                <div style="font-size: 13px; color: #666; margin-bottom: 4px; font-weight: 500;">视频 ${index + 1}</div>
                                <div style="font-size: 12px; color: #888; display: flex; justify-content: space-between;">
                                    <span>${video.type || 'external'}</span>
                                    <span>${isDownloaded ? '✓ 已下载' : '🔗 外部链接'}</span>
                                </div>
                            </div>
                        `;
                        videosGrid.appendChild(videoCard);
                    }
                });
            } else if (videosSection) {
                videosSection.style.display = 'none';
            }

            // 显示编辑区域
            setupEditSection(data);
        }

        function setupEditSection(data) {
            // 检查是否为手动模式（没有 content_file 字段）
            if (!data.content_file) {
                // 手动模式：直接设置内容
                document.getElementById('contentEditor').value = data.content || '';
                
                // 手动模式：显示提取到的图片列表（只读模式）
                const imageSelector = document.getElementById('imageSelector');
                imageSelector.innerHTML = '';
                
                if (data.images && data.images.length > 0) {
                    // 创建图片列表展示区
                    const listContainer = document.createElement('div');
                    listContainer.style.cssText = `
                        padding: 20px;
                        max-height: 400px;
                        overflow-y: auto;
                    `;
                    
                    listContainer.innerHTML = `
                        <h3 style="margin-bottom: 15px; color: #333;">📸 已提取 ${data.images.length} 张图片</h3>
                        <p style="color: #666; margin-bottom: 15px; font-size: 14px;">
                            💡 以下是从文章中提取的图片，您可以点击查看原图或下载。
                        </p>
                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 15px;">
                    `;
                    
                    data.images.forEach((img, index) => {
                        const imgCard = document.createElement('div');
                        imgCard.style.cssText = `
                            border: 2px solid #e0e0e0;
                            border-radius: 8px;
                            overflow: hidden;
                            transition: transform 0.2s;
                            cursor: pointer;
                        `;
                        imgCard.onmouseover = () => imgCard.style.transform = 'scale(1.05)';
                        imgCard.onmouseout = () => imgCard.style.transform = 'scale(1)';
                        
                        const imgSrc = img.url || '';
                        const imgAlt = img.alt || `图片 ${index + 1}`;
                        
                        imgCard.innerHTML = `
                            <div style="position: relative;" onclick="openImageModal('${imgSrc}', null)">
                                <img src="${imgSrc}" alt="${imgAlt}" 
                                     style="width: 100%; height: 150px; object-fit: cover; display: block;"
                                     onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22><rect fill=%22%23ddd%22 width=%22200%22 height=%22200%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%23999%22>加载失败</text></svg>'"
                                     crossorigin="anonymous">
                                <div style="position: absolute; top: 5px; right: 5px; background: rgba(0,0,0,0.7); color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px;">
                                    👁️ 查看/去水印
                                </div>
                            </div>
                            <div style="padding: 8px;">
                                <div style="font-size: 12px; color: #666; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                    ${imgAlt}
                                </div>
                                <a href="${imgSrc}" target="_blank" download style="display: block; text-align: center; background: #667eea; color: white; padding: 5px; border-radius: 4px; text-decoration: none; font-size: 12px;">
                                    📥 下载原图
                                </a>
                            </div>
                        `;
                        
                        listContainer.querySelector('[style*="grid"]').appendChild(imgCard);
                    });
                    
                    listContainer.innerHTML += '</div>';
                    imageSelector.appendChild(listContainer);
                } else {
                    imageSelector.innerHTML = `
                        <p style="color: #999; text-align: center; padding: 40px;">
                            📄 未从内容中提取到图片
                        </p>
                    `;
                }
                return;
            }
            
            // 自动模式：原有逻辑
            fetch(data.content_file)
                .then(response => response.text())
                .then(content => {
                    // 移除前面的元数据行
                    const lines = content.split('\n');
                    const contentStart = lines.findIndex(line => line.includes('===='));
                    const actualContent = lines.slice(contentStart + 2).join('\n').trim();
                    document.getElementById('contentEditor').value = actualContent;
                })
                .catch(err => console.error('加载内容失败:', err));

            // 创建可选择的图片和视频
            const imageSelector = document.getElementById('imageSelector');
            imageSelector.innerHTML = '';

            // 处理图片
            const successImages = data.images.filter(img => img.success);
            successImages.forEach((img, index) => {
                const imgDiv = document.createElement('div');
                imgDiv.className = 'selectable-image';
                imgDiv.dataset.index = index;
                imgDiv.dataset.path = img.local_path;
                imgDiv.dataset.type = 'image';
                
                imgDiv.innerHTML = `
                    <img src="${img.local_path}" alt="图片 ${index + 1}">
                    <div class="checkbox"></div>
                    <div class="image-order-number">${index + 1}</div>
                    ${img.local_path.toLowerCase().endsWith('.gif') ? '<div class="gif-badge">🎞️ GIF</div>' : ''}
                    <div class="image-effects">
                        <button class="effect-btn" onclick="processImage(this.closest('.selectable-image').dataset.path, 'enhance', event)">增强</button>
                        <button class="effect-btn" onclick="processImage(this.closest('.selectable-image').dataset.path, 'sharpen', event)">锐化</button>
                        <button class="effect-btn" onclick="openEditorForImage(this.closest('.selectable-image').dataset.path, this.closest('.selectable-image').querySelector('img')); event.stopPropagation();">🛠️ 编辑/去水印</button>
                    </div>
                `;

                imgDiv.onclick = (e) => {
                    if (!e.target.classList.contains('effect-btn')) {
                        toggleMediaSelection(imgDiv);
                    }
                };

                imageSelector.appendChild(imgDiv);
            });

            // 处理视频（如果有的话）
            if (data.videos && data.videos.length > 0) {
                const successVideos = data.videos.filter(video => video.success);
                successVideos.forEach((video, index) => {
                    const videoIndex = successImages.length + index;
                    const videoDiv = document.createElement('div');
                    videoDiv.className = 'selectable-video';
                    videoDiv.dataset.index = videoIndex;
                    videoDiv.dataset.path = video.local_path;
                    videoDiv.dataset.type = 'video';
                    videoDiv.dataset.size = video.size_mb || 0;
                    
                    // 从文件名提取简洁名称
                    const fileName = video.filename || video.local_path.split('/').pop() || '视频';
                    const displayName = fileName.length > 15 ? fileName.substring(0, 12) + '...' : fileName;
                    
                    videoDiv.innerHTML = `
                        ${video.thumbnail_path ? 
                            `<img src="${video.thumbnail_path}" alt="视频缩略图" style="width: 100%; height: 100%; object-fit: cover; display: block;">` :
                            `<div class="video-preview">🎬</div>`
                        }
                        <div class="video-info">
                            <div>${displayName}</div>
                            <div>${video.size_mb ? video.size_mb.toFixed(1) + 'MB' : '未知大小'}</div>
                        </div>
                        <div class="checkbox"></div>
                        <div class="image-order-number">${videoIndex + 1}</div>
                        <div class="gif-badge">🎥 视频</div>
                    `;

                    videoDiv.onclick = (e) => {
                        toggleMediaSelection(videoDiv);
                    };

                    imageSelector.appendChild(videoDiv);
                });
            }

            // 显示编辑区域
            document.getElementById('editSection').classList.add('active');
            document.getElementById('aiSummary').style.display = 'none';
        }

        function toggleMediaSelection(mediaDiv) {
            const index = parseInt(mediaDiv.dataset.index);
            const path = mediaDiv.dataset.path;
            const type = mediaDiv.dataset.type;

            if (mediaDiv.classList.contains('selected')) {
                // 取消选择
                mediaDiv.classList.remove('selected');
                selectedImages = selectedImages.filter(img => img.path !== path);
                console.log(`取消选择${type}:`, path);
            } else {
                // 选择 - 添加为对象
                mediaDiv.classList.add('selected');
                const isVideo = type === 'video' || isVideoPath(path);
                selectedImages.push({
                    path: path,
                    duration: isVideo ? 3 : 2.0,
                    type: isVideo ? 'video' : type
                });
                console.log(`选择${type}:`, path);
            }

            console.log('当前已选择媒体:', selectedImages.length);
            
            // 更新排序面板
            initSortPanel();
            // 更新主图片区域序号
            setTimeout(updateMainImageNumbers, 100);
        }

        function toggleImageSelection(imgDiv) {
            // 保持向后兼容
            toggleMediaSelection(imgDiv);
        }

        function classifyLocalMediaFile(file) {
            const mime = (file.type || '').toLowerCase();
            if (mime.startsWith('video/')) return 'video';
            if (mime.startsWith('image/')) return 'image';
            const n = (file.name || '').toLowerCase();
            if (/\.(mp4|webm|mov|avi|mkv)$/.test(n)) return 'video';
            if (/\.(jpe?g|png|gif|webp|bmp)$/.test(n)) return 'image';
            return null;
        }

        function apiErrorMessage(body) {
            if (!body || typeof body !== 'object') return '上传失败';
            const d = body.detail;
            if (typeof d === 'string') return d;
            if (Array.isArray(d) && d[0] && d[0].msg) return d.map((x) => x.msg).join('; ');
            return body.message || JSON.stringify(body);
        }

        // 处理本地上传（图片 + 视频）
        async function handleLocalImageUpload(event) {
            const files = event.target.files;
            const uploadStatus = document.getElementById('uploadStatus');
            
            if (files.length === 0) return;
            
            uploadStatus.innerHTML = `正在上传 ${files.length} 个文件...`;
            
            try {
                const uploadedItems = [];
                
                for (let i = 0; i < files.length; i++) {
                    const file = files[i];
                    const kind = classifyLocalMediaFile(file);
                    if (!kind) {
                        showToast(`文件 ${file.name} 不是支持的图片或视频格式`, 'error');
                        continue;
                    }

                    if (kind === 'image') {
                        if (file.size > 10 * 1024 * 1024) {
                            showToast(`图片 ${file.name} 太大（超过10MB）`, 'error');
                            continue;
                        }
                        const formData = new FormData();
                        formData.append('image', file);
                        try {
                            const response = await fetch('/upload-local-image', {
                                method: 'POST',
                                body: formData
                            });
                            const result = await response.json();
                            if (response.ok && result.success) {
                                uploadedItems.push({ path: result.image_path, type: 'image' });
                                showToast(`✅ ${file.name} 上传成功`, 'success', 2000);
                            } else {
                                showToast(`❌ ${file.name} 上传失败: ${apiErrorMessage(result)}`, 'error');
                            }
                        } catch (error) {
                            showToast(`❌ ${file.name} 上传出错: ${error.message}`, 'error');
                        }
                    } else {
                        if (file.size > 200 * 1024 * 1024) {
                            showToast(`视频 ${file.name} 太大（超过200MB）`, 'error');
                            continue;
                        }
                        const formData = new FormData();
                        formData.append('video', file);
                        try {
                            const response = await fetch('/upload-local-video', {
                                method: 'POST',
                                body: formData
                            });
                            const result = await response.json();
                            if (response.ok && result.success) {
                                const vp = result.video_path || result.image_path;
                                uploadedItems.push({
                                    path: vp,
                                    type: 'video',
                                    name: file.name,
                                    sizeMb: file.size / (1024 * 1024)
                                });
                                showToast(`✅ ${file.name} 上传成功`, 'success', 2000);
                            } else {
                                showToast(`❌ ${file.name} 上传失败: ${apiErrorMessage(result)}`, 'error');
                            }
                        } catch (error) {
                            showToast(`❌ ${file.name} 上传出错: ${error.message}`, 'error');
                        }
                    }
                }
                
                if (uploadedItems.length > 0) {
                    addUploadedMediaToSelector(uploadedItems);
                    uploadStatus.innerHTML = `✅ 成功上传 ${uploadedItems.length} 个文件`;
                    setTimeout(() => {
                        uploadStatus.innerHTML = '';
                    }, 3000);
                } else {
                    uploadStatus.innerHTML = '❌ 没有文件成功上传';
                }
                
            } catch (error) {
                console.error('上传过程中发生错误:', error);
                showToast('上传过程中发生错误: ' + error.message, 'error');
                uploadStatus.innerHTML = '❌ 上传失败';
            }
            
            event.target.value = '';
        }

        function addUploadedMediaToSelector(items) {
            items.forEach((item) => {
                if (item.type === 'video') {
                    addUploadedVideoToSelector(item);
                } else {
                    addUploadedImageToSelector(item.path);
                }
            });
        }

        function addUploadedVideoToSelector(item) {
            const imageSelector = document.getElementById('imageSelector');
            const path = item.path;
            const existing = Array.from(imageSelector.querySelectorAll('.selectable-video'))
                .find((el) => el.dataset.path === path);
            if (existing) return;

            const idx = imageSelector.querySelectorAll('.selectable-image, .selectable-video').length;
            const fileName = item.name || path.split('/').pop() || '视频';
            const displayName = fileName.length > 15 ? fileName.substring(0, 12) + '...' : fileName;
            const sizeMb = item.sizeMb != null ? item.sizeMb.toFixed(1) + 'MB' : '未知大小';

            const videoDiv = document.createElement('div');
            videoDiv.className = 'selectable-video';
            videoDiv.dataset.index = idx;
            videoDiv.dataset.path = path;
            videoDiv.dataset.type = 'video';
            videoDiv.dataset.source = 'local';
            videoDiv.innerHTML = `
                <div class="video-preview">🎬</div>
                <div class="video-info">
                    <div>${displayName}</div>
                    <div>${sizeMb}</div>
                </div>
                <div class="checkbox"></div>
                <div class="image-order-number">${idx + 1}</div>
                <div class="gif-badge">🎥 视频</div>
                <div class="local-upload-badge">📱 本地上传</div>
            `;
            videoDiv.onclick = (e) => {
                toggleMediaSelection(videoDiv);
            };
            imageSelector.appendChild(videoDiv);
        }

        function addUploadedImageToSelector(imagePath, options) {
            const opts = options || {};
            const source = opts.source || 'local';
            const imageSelector = document.getElementById('imageSelector');
            
            const existingImage = Array.from(imageSelector.querySelectorAll('.selectable-image'))
                .find(img => img.dataset.path === imagePath);
            
            if (existingImage) {
                return;
            }

            const imgDiv = document.createElement('div');
            imgDiv.className = 'selectable-image';
            imgDiv.dataset.path = imagePath;
            imgDiv.dataset.type = 'image';
            imgDiv.dataset.source = source;

            const slotIndex = imageSelector.querySelectorAll('.selectable-image, .selectable-video').length;
            imgDiv.dataset.index = slotIndex;

            imgDiv.innerHTML = `
                    <img src="${imagePath}" alt="本地上传图片 ${slotIndex + 1}" 
                         onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22><rect fill=%22%23f5f5f5%22 width=%22200%22 height=%22200%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%23999%22>加载失败</text></svg>'">
                    <div class="checkbox"></div>
                    <div class="image-order-number">${slotIndex + 1}</div>
                    
                    <div class="local-upload-badge">${
                        source === 'web_search'
                            ? '🔍 搜图'
                                                        : source === 'related_image'
                                                            ? '🌐 补充图'
                            : source === 'ai_cover'
                              ? '🎨 AI封面'
                              : '📱 本地上传'
                    }</div>
                    <div class="image-effects">
                        <button class="effect-btn" onclick="processImage(this.closest('.selectable-image').dataset.path, 'enhance', event)">增强</button>
                        <button class="effect-btn" onclick="processImage(this.closest('.selectable-image').dataset.path, 'sharpen', event)">锐化</button>
                        <button class="effect-btn" onclick="processImage(this.closest('.selectable-image').dataset.path, 'grayscale', event)">黑白</button>
                        <button class="effect-btn" onclick="processImage(this.closest('.selectable-image').dataset.path, 'blur', event)">模糊</button>
                        <button class="effect-btn" onclick="openEditorForImage(this.closest('.selectable-image').dataset.path, this.closest('.selectable-image').querySelector('img')); event.stopPropagation();">🛠️ 编辑/去水印</button>
                    </div>
                `;

            imgDiv.onclick = (e) => {
                if (e.target.classList.contains('effect-btn')) return;
                toggleMediaSelection(imgDiv);
            };

            imageSelector.appendChild(imgDiv);
        }

        async function generateCoverFromPageContent() {
            const contentEl = document.getElementById('contentEditor');
            const content = contentEl && contentEl.value ? contentEl.value.trim() : '';
            if (!content) {
                showToast('请先在正文中保留或填写网页内容', 'error');
                return;
            }
            const l1 = document.getElementById('editableMainLine1');
            const title =
                (l1 && l1.value.trim()) ||
                (typeof currentData !== 'undefined' && currentData && currentData.title
                    ? currentData.title
                    : '');
            const hintEl = document.getElementById('coverGenExtraHint');
            const extra_hint = hintEl && hintEl.value ? hintEl.value.trim() : '';
            const statusEl = document.getElementById('coverGenStatus');
            const btn = document.getElementById('coverGenBtn');
            if (btn) btn.disabled = true;
            if (statusEl) statusEl.textContent = '正在调用文生图 API（约 30～120 秒）…';
            try {
                const res = await fetch('/api/generate-cover-image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content, title, extra_hint }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    const msg = data.detail || data.message || '生成失败';
                    const errText =
                        typeof msg === 'string' ? msg : Array.isArray(msg) ? JSON.stringify(msg) : JSON.stringify(msg);
                    throw new Error(errText);
                }
                if (data.image_path) {
                    addUploadedImageToSelector(data.image_path, { source: 'ai_cover' });
                    showToast('封面已加入选区', 'success');
                    if (statusEl) statusEl.textContent = '已加入选图区（可在下方点击选择）';
                } else {
                    throw new Error(data.message || '未返回图片路径');
                }
            } catch (err) {
                console.error(err);
                const msg = '封面生成失败: ' + (err && err.message ? err.message : String(err));
                if (statusEl) statusEl.textContent = msg;
                showToast(msg, 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        let _webImageSearchResults = [];

        function _ensureWebImageSearchHoverPreview() {
            let wrap = document.getElementById('webImageSearchHoverPreview');
            if (!wrap) {
                wrap = document.createElement('div');
                wrap.id = 'webImageSearchHoverPreview';
                wrap.style.cssText = [
                    'display:none',
                    'position:fixed',
                    'z-index:99999',
                    'pointer-events:none',
                    'padding:0',
                    'margin:0',
                    'border-radius:10px',
                    'overflow:hidden',
                    'box-shadow:0 12px 40px rgba(15,23,42,0.35)',
                    'border:2px solid #fff',
                    'background:#fff',
                ].join(';');
                const img = document.createElement('img');
                img.alt = '';
                img.style.cssText =
                    'display:block;max-width:min(420px,92vw);max-height:min(380px,72vh);width:auto;height:auto;object-fit:contain;';
                img.referrerPolicy = 'no-referrer';
                wrap.appendChild(img);
                document.body.appendChild(wrap);
            }
            return wrap;
        }

        function _positionWebImageHoverPreview(wrap, clientX, clientY) {
            const pad = 18;
            const margin = 8;
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            let w = wrap.offsetWidth || 320;
            let h = wrap.offsetHeight || 280;
            let left = clientX + pad;
            let top = clientY + pad;
            if (left + w > vw - margin) {
                left = clientX - w - pad;
            }
            if (left < margin) left = margin;
            if (top + h > vh - margin) {
                top = clientY - h - pad;
            }
            if (top < margin) top = margin;
            if (left + w > vw - margin) left = Math.max(margin, vw - w - margin);
            if (top + h > vh - margin) top = Math.max(margin, vh - h - margin);
            wrap.style.left = `${left}px`;
            wrap.style.top = `${top}px`;
        }

        function _showWebImageHoverPreview(url, title, clientX, clientY) {
            if (!url) return;
            const wrap = _ensureWebImageSearchHoverPreview();
            const img = wrap.querySelector('img');
            if (img) {
                img.alt = title || '';
                if (img.src !== url) {
                    img.src = url;
                }
            }
            wrap.style.display = 'block';
            const place = () => _positionWebImageHoverPreview(wrap, clientX, clientY);
            requestAnimationFrame(place);
            if (img) {
                img.onload = place;
                if (img.complete) place();
            }
        }

        function _hideWebImageHoverPreview() {
            const wrap = document.getElementById('webImageSearchHoverPreview');
            if (wrap) wrap.style.display = 'none';
        }

        async function runWebImageSearch() {
            const q = (document.getElementById('webImageSearchQuery') || {}).value;
            const query = (q || '').trim();
            const statusEl = document.getElementById('webImageSearchStatus');
            const grid = document.getElementById('webImageSearchGrid');
            const btn = document.getElementById('webImageSearchBtn');
            if (!query) {
                showToast('请输入搜索词', 'error');
                return;
            }
            _hideWebImageHoverPreview();
            if (btn) btn.disabled = true;
            if (statusEl) statusEl.textContent = '搜索中…';
            if (grid) grid.innerHTML = '';
            _webImageSearchResults = [];
            try {
                const res = await fetch('/api/search-images', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query,
                        engine: 'baidu',
                        page: 0,
                        page_size: 24,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    const msg = data.detail || data.message || '请求失败';
                    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
                }
                _webImageSearchResults = data.items || [];
                if (!_webImageSearchResults.length) {
                    if (statusEl) statusEl.textContent = '未找到图片，请换关键词重试';
                    return;
                }
                if (statusEl) {
                    statusEl.textContent = `找到 ${_webImageSearchResults.length} 张，悬停可看大图，点击加入下方选区`;
                }
                _webImageSearchResults.forEach((item, i) => {
                    const cell = document.createElement('div');
                    cell.style.cssText =
                        'position:relative;cursor:pointer;border-radius:8px;overflow:hidden;border:2px solid #e2e8f0;aspect-ratio:1;';
                    cell.dataset.index = String(i);
                    const img = document.createElement('img');
                    img.src = item.thumb_url;
                    img.alt = item.title || '';
                    img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
                    img.loading = 'lazy';
                    img.referrerPolicy = 'no-referrer';
                    cell.appendChild(img);
                    const previewUrl = item.image_url || item.thumb_url;
                    cell.addEventListener('mouseenter', (e) => {
                        _showWebImageHoverPreview(previewUrl, item.title, e.clientX, e.clientY);
                    });
                    cell.addEventListener('mousemove', (e) => {
                        const wrap = document.getElementById('webImageSearchHoverPreview');
                        if (wrap && wrap.style.display !== 'none') {
                            _positionWebImageHoverPreview(wrap, e.clientX, e.clientY);
                        }
                    });
                    cell.addEventListener('mouseleave', () => {
                        _hideWebImageHoverPreview();
                    });
                    cell.onclick = () => importWebSearchImage(i);
                    if (grid) grid.appendChild(cell);
                });
            } catch (err) {
                console.error(err);
                const msg = '搜索失败: ' + (err && err.message ? err.message : String(err));
                if (statusEl) statusEl.textContent = msg;
                showToast(msg, 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        async function importWebSearchImage(index) {
            const item = _webImageSearchResults[index];
            if (!item) return;
            const statusEl = document.getElementById('webImageSearchStatus');
            const url = item.image_url || item.thumb_url;
            if (statusEl) statusEl.textContent = '正在导入…';
            try {
                const res = await fetch('/api/import-remote-image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url, referer: item.referer || '' }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    const msg = data.detail || data.message || '导入失败';
                    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
                }
                if (data.image_path) {
                    addUploadedImageToSelector(data.image_path, { source: 'web_search' });
                    showToast('已加入选图', 'success');
                    if (statusEl) statusEl.textContent = '已加入选图区（可继续点选其他缩略图）';
                }
            } catch (err) {
                console.error(err);
                const msg = '导入失败: ' + (err && err.message ? err.message : String(err));
                if (statusEl) statusEl.textContent = msg;
                showToast(msg, 'error');
            }
        }

        let _relatedImageResults = [];

        function _getRelatedImageNumber(id, fallback, min, max) {
            const el = document.getElementById(id);
            let value = parseInt(el && el.value, 10);
            if (!Number.isFinite(value)) value = fallback;
            return Math.max(min, Math.min(max, value));
        }

        function _getRelatedImagePayload() {
            const queryEl = document.getElementById('relatedImageQuery');
            const contentEl = document.getElementById('contentEditor');
            const titleEl = document.getElementById('resultTitle');
            const sourceInputs = Array.from(document.querySelectorAll('.related-image-source'));
            const searchSources = sourceInputs
                .filter((el) => el.checked)
                .map((el) => el.value)
                .filter(Boolean);
            const title =
                (currentData && currentData.title) ||
                (titleEl && titleEl.textContent ? titleEl.textContent.trim() : '');
            const content = contentEl && contentEl.value ? contentEl.value.trim() : (currentData && currentData.content) || '';
            const sourceUrl = (currentData && currentData.url) || (document.getElementById('urlInput') || {}).value || '';
            return {
                title,
                content,
                source_url: sourceUrl,
                query: queryEl && queryEl.value ? queryEl.value.trim() : '',
                search_sources: searchSources.length ? searchSources : ['baidu'],
                max_pages: _getRelatedImageNumber('relatedImageMaxPages', 5, 1, 10),
                max_crawl_pages: 18,
                max_images_per_page: _getRelatedImageNumber('relatedImageMaxPerPage', 6, 1, 12),
            };
        }

        function _renderRelatedPages(pages) {
            const wrap = document.getElementById('relatedImagePages');
            if (!wrap) return;
            wrap.innerHTML = '';
            if (!pages || !pages.length) {
                wrap.style.display = 'none';
                return;
            }
            wrap.style.display = 'block';
            pages.forEach((page, index) => {
                const row = document.createElement('div');
                row.style.cssText = 'padding:6px 0;border-bottom:1px solid #e2e8f0;line-height:1.45;';
                const title = document.createElement('div');
                title.style.cssText = 'font-weight:600;color:#334155;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
                title.textContent = `${index + 1}. ${page.title || page.url || '相关页面'}${page.images_count != null ? `（${page.images_count} 张）` : ''}`;
                const meta = document.createElement('div');
                meta.style.cssText = page.success === false ? 'color:#b91c1c;' : 'color:#64748b;';
                const sourceLabel = page.search_source ? `${page.search_source_label || page.search_source} 第${page.search_page || 1}页 · ` : '';
                meta.textContent = page.success === false ? (page.error || page.url || '') : `${sourceLabel}${page.source || page.url || ''}`;
                row.appendChild(title);
                row.appendChild(meta);
                wrap.appendChild(row);
            });
        }

        function _renderRelatedImages(images) {
            const grid = document.getElementById('relatedImageGrid');
            if (!grid) return;
            grid.innerHTML = '';
            _relatedImageResults = images || [];
            if (!_relatedImageResults.length) {
                grid.innerHTML = '<p style="grid-column:1/-1;color:#999;text-align:center;padding:24px;">未抓取到可用图片</p>';
                return;
            }
            _relatedImageResults.forEach((item, index) => {
                const cell = document.createElement('div');
                cell.style.cssText = 'position:relative;cursor:pointer;border-radius:8px;overflow:hidden;border:2px solid #e2e8f0;background:#fff;';
                cell.title = item.source_title || item.source_page || '';
                const img = document.createElement('img');
                img.src = item.local_path || item.url;
                img.alt = item.alt || `补充图片 ${index + 1}`;
                img.loading = 'lazy';
                img.referrerPolicy = 'no-referrer';
                img.style.cssText = 'width:100%;aspect-ratio:1;object-fit:cover;display:block;';
                img.onerror = () => {
                    img.src = 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22><rect fill=%22%23f5f5f5%22 width=%22200%22 height=%22200%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%23999%22>加载失败</text></svg>';
                };
                const badge = document.createElement('div');
                badge.style.cssText = 'position:absolute;left:6px;bottom:6px;right:6px;background:rgba(15,23,42,0.78);color:#fff;border-radius:5px;padding:4px 6px;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
                badge.textContent = item.source_title || item.source_page || '相关页面';
                cell.appendChild(img);
                cell.appendChild(badge);
                const previewUrl = item.local_path || item.url;
                cell.addEventListener('mouseenter', (e) => {
                    _showWebImageHoverPreview(previewUrl, item.source_title || item.alt || '', e.clientX, e.clientY);
                });
                cell.addEventListener('mousemove', (e) => {
                    const wrap = document.getElementById('webImageSearchHoverPreview');
                    if (wrap && wrap.style.display !== 'none') {
                        _positionWebImageHoverPreview(wrap, e.clientX, e.clientY);
                    }
                });
                cell.addEventListener('mouseleave', () => {
                    _hideWebImageHoverPreview();
                });
                cell.onclick = () => importRelatedImage(index);
                grid.appendChild(cell);
            });
        }

        async function runRelatedImageCrawl() {
            const statusEl = document.getElementById('relatedImageStatus');
            const btn = document.getElementById('relatedImageBtn');
            const grid = document.getElementById('relatedImageGrid');
            const pagesEl = document.getElementById('relatedImagePages');
            const payload = _getRelatedImagePayload();
            if (!payload.title && !payload.content && !payload.query) {
                showToast('请先抓取页面，或手动输入搜索词', 'error');
                return;
            }
            if (!payload.search_sources || !payload.search_sources.length) {
                showToast('请至少选择一个搜索源', 'error');
                return;
            }
            if (btn) btn.disabled = true;
            _hideWebImageHoverPreview();
            if (statusEl) statusEl.textContent = `正在调用 DeepSeek 生成搜索词，并从 ${payload.search_sources.join('、')} 每源搜索 ${payload.max_pages} 页后抓图…`;
            if (grid) grid.innerHTML = '';
            if (pagesEl) {
                pagesEl.innerHTML = '';
                pagesEl.style.display = 'none';
            }
            _relatedImageResults = [];
            try {
                const res = await fetch('/api/related-images/crawl', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    const msg = data.detail || data.message || '请求失败';
                    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
                }
                _renderRelatedPages(data.pages || []);
                _renderRelatedImages(data.images || []);
                const keywordText = data.keywords && data.keywords.length ? `；关键词：${data.keywords.join('、')}` : '';
                const sourceText = data.search_sources && data.search_sources.length ? `；来源：${data.search_sources.join('、')}×每源${data.search_pages_per_source || payload.max_pages}页` : '';
                const crawlText = data.candidate_pages_count != null ? `；候选页 ${data.candidate_pages_count}，已打开 ${data.crawled_pages_count || 0}` : '';
                if (statusEl) statusEl.textContent = `搜索词：${data.query || payload.query || '未返回'}；抓到 ${(data.images || []).length} 张候选图片${sourceText}${crawlText}${keywordText}`;
                if (data.images && data.images.length) {
                    showToast('已抓到补充图片，点击缩略图可加入选区', 'success');
                } else {
                    showToast(data.message || '没有抓到可用图片', 'info');
                }
            } catch (err) {
                console.error(err);
                const msg = '补充图片失败: ' + (err && err.message ? err.message : String(err));
                if (statusEl) statusEl.textContent = msg;
                showToast(msg, 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        function importRelatedImage(index) {
            const item = _relatedImageResults[index];
            if (!item || !item.local_path) {
                showToast('图片尚未保存成功，无法加入选区', 'error');
                return;
            }
            addUploadedImageToSelector(item.local_path, { source: 'related_image' });
            showToast('已加入选图', 'success');
            const statusEl = document.getElementById('relatedImageStatus');
            if (statusEl) statusEl.textContent = '已加入选图区（可继续点选其他补充图片）';
        }

        async function processImage(imagePath, effect, event) {
            event.stopPropagation();
            
            try {
                const response = await fetch('/api/process-image', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        image_path: imagePath,
                        effect: effect
                    })
                });

                const data = await response.json();

                if (data.success) {
                    showToast(`✅ 图片处理成功！效果：${effect}`, 'success');
                    const imgDiv = Array.from(document.querySelectorAll('.selectable-image')).find(
                        (el) => el.dataset.path === imagePath
                    );
                    if (imgDiv) {
                        const thumb = imgDiv.querySelector('img');
                        if (thumb) thumb.src = data.processed_path + '?t=' + Date.now();
                    }
                } else {
                    showToast('❌ 图片处理失败：' + data.message, 'error');
                }
            } catch (error) {
                showToast('❌ 图片处理失败：' + error.message, 'error');
            }
        }
                
        /**
         * 为指定图片打开编辑器（用于「编辑/去水印」按钮；需传入缩略图 img 以便保存后更新列表）
         */
        function openEditorForImage(imagePath, sourceEl) {
            console.log('\n=== 打开编辑器 ===');
            console.log('   - 图片路径:', imagePath);
                    
            // 打开图片查看器
            openImageModal(imagePath, sourceEl);
                    
            console.log('   - 模态框已打开，currentPath:', modalState.currentPath);
                    
            // 立即进入编辑模式
            console.log('⏰ 准备进入编辑模式...');
            enterEditMode(imagePath);
        }
                
        /**
         * 进入编辑模式
         */
        function enterEditMode(imagePath) {
            const overlay = document.getElementById('imageModalOverlay');
            const modalTitle = document.getElementById('modalTitle');
            const editTools = document.getElementById('editTools');
            const saveEditBtn = document.getElementById('saveEditBtn');
                    
            if (!overlay || !modalTitle) {
                console.error('❌ 模态框元素不存在');
                return;
            }
                    
            // 修改标题
            modalTitle.textContent = '🛠️ 图片编辑器';
                    
            // 显示编辑工具栏
            if (editTools) {
                editTools.style.display = 'flex';
            }
                    
            // 重置保存按钮状态
            if (saveEditBtn) {
                saveEditBtn.disabled = true;
                saveEditBtn.textContent = '💾 保存修改';
            }
                    
            // 关键修复：确保有正确的编辑路径
            // 优先级：传入的 imagePath > modalState.currentPath
            let editingPath = imagePath;
            if (!editingPath && modalState.currentPath) {
                editingPath = modalState.currentPath;
                console.log('   ℹ️ 使用 modalState.currentPath:', editingPath);
            }
                    
            window.currentEditingImagePath = editingPath;
            window.editModified = false; // 标记是否进行了修改
                    
            console.log('✅ 进入编辑模式成功！');
            console.log('   - 传入的 imagePath:', imagePath);
            console.log('   - modalState.currentPath:', modalState.currentPath);
            console.log('   - 最终使用的 editingPath:', editingPath);
            console.log('   - window.currentEditingImagePath:', window.currentEditingImagePath);
                            
            // showToast('💡 提示：点击"框选水印"工具，框选水印区域后点击"去除水印"', 'info', 5000);
        }

        async function generateSummary() {
            const content = document.getElementById('contentEditor').value;
            
            if (!content.trim()) {
                alert('请先输入或编辑文章内容');
                return;
            }

            // 显示加载状态（添加安全检查）
            const summaryDiv = document.getElementById('aiSummary');
            if (summaryDiv) summaryDiv.style.display = 'block';
            
            const aiMainLine1El = document.getElementById('editableMainLine1');
            const aiMainLine2El = document.getElementById('editableMainLine2');
            const aiSubTitleEl = document.getElementById('editableSubTitle');
            const aiSummaryEl = document.getElementById('editableAiSummary');
            const aiVoiceoverEl = document.getElementById('editableVoiceoverScript');
            const aiTagsEl = document.getElementById('editableAiTags');
            const aiMetaEl = document.getElementById('aiMeta');
            
            if (aiMainLine1El) aiMainLine1El.value = '正在生成…';
            if (aiMainLine2El) aiMainLine2El.value = '正在生成…';
            if (aiSubTitleEl) aiSubTitleEl.value = '正在生成…';
            if (aiSummaryEl) aiSummaryEl.value = '正在生成摘要...';
            if (aiVoiceoverEl) aiVoiceoverEl.value = '正在生成口播稿...';
            if (aiTagsEl) aiTagsEl.value = '';
            if (aiMetaEl) aiMetaEl.textContent = '';

            try {
                const voLen = getVoiceoverLengthParams();
                const response = await fetch('/api/generate-summary', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        content: content,
                        // 只传递图片路径字符串数组，不需要时长信息
                        images: selectedImages.map(imgObj => imgObj.path),
                        title: currentData.title,
                        voiceover_min_chars: voLen.voiceover_min_chars,
                        voiceover_max_chars: voLen.voiceover_max_chars
                    })
                });

                const data = await response.json();

                if (data.success) {
                    generatedTitle = data.title;
                    generatedSummary = data.summary;
                    
                    const line1 = data.main_line1 != null ? data.main_line1 : (data.main_title || (data.title || '').split('|')[0] || '');
                    const line2 = data.main_line2 != null ? data.main_line2 : '';
                    const subT = data.sub_title != null ? data.sub_title : '';
                    
                    document.getElementById('editableMainLine1').value = line1;
                    document.getElementById('editableMainLine2').value = line2;
                    document.getElementById('editableSubTitle').value = subT;
                    document.getElementById('editableAiSummary').value = data.summary;
                    const voText = data.voiceover_script != null ? data.voiceover_script : '';
                    if (document.getElementById('editableVoiceoverScript')) {
                        document.getElementById('editableVoiceoverScript').value = voText;
                    }
                    document.getElementById('editableAiTags').value = data.tags || '';
                    editedHighlightKeywords = Array.isArray(data.highlight_keywords)
                        ? data.highlight_keywords.slice()
                        : [];
                    document.getElementById('aiMeta').textContent = 
                        `主L1:${line1.length}字 L2:${line2.length}字 副:${subT.length}字 | 摘要:${(data.summary || '').length}字 口播:${voText.length}字 高亮:${editedHighlightKeywords.length}词 | ${data.model} | tokens:${data.tokens_used}`;
                    
                    // 自动保存初始内容
                    saveEditedContent();
                } else {
                    if (aiMainLine1El) aiMainLine1El.value = '';
                    if (aiMainLine2El) aiMainLine2El.value = '';
                    if (aiSubTitleEl) aiSubTitleEl.value = '';
                    if (aiSummaryEl) aiSummaryEl.value = '生成失败: ' + data.message;
                    if (aiVoiceoverEl) aiVoiceoverEl.value = '';
                    if (aiTagsEl) aiTagsEl.value = '';
                    editedHighlightKeywords = [];
                    if (aiMetaEl) aiMetaEl.textContent = '';
                }
            } catch (error) {
                if (aiMainLine1El) aiMainLine1El.value = '';
                if (aiMainLine2El) aiMainLine2El.value = '';
                if (aiSubTitleEl) aiSubTitleEl.value = '';
                if (aiSummaryEl) aiSummaryEl.value = '生成失败: ' + error.message;
                if (aiVoiceoverEl) aiVoiceoverEl.value = '';
                if (aiTagsEl) aiTagsEl.value = '';
                editedHighlightKeywords = [];
                if (aiMetaEl) aiMetaEl.textContent = '';
            }
        }

        async function generateVideoDirectly() {
            // 检查必要条件
            const mainLine1 = document.getElementById('editableMainLine1')?.value.trim();
            const mainLine2 = document.getElementById('editableMainLine2')?.value.trim();
            const subTitle = document.getElementById('editableSubTitle')?.value.trim();
            const editedSummary = document.getElementById('editableAiSummary')?.value.trim();
            
            if (!mainLine1 || !editedSummary) {
                showToast('请先生成AI标题和摘要，或手动填写主标题第一行与摘要', 'error');
                return;
            }
            
            const editedTitle = [mainLine1, mainLine2, subTitle].filter(Boolean).join('|');
            
            if (selectedImages.length === 0) {
                showToast('请至少选择一张图片', 'error');
                return;
            }
            
            // 检查是否有 GIF 或视频需要特殊处理
            const gifImages = selectedImages.filter((imgObj) =>
                needsAnimationPreconvertPath(imgObj.path)
            );
            const videoFiles = selectedImages.filter(imgObj => 
                imgObj.path.toLowerCase().endsWith('.mp4') || 
                imgObj.path.toLowerCase().endsWith('.webm') || 
                imgObj.path.toLowerCase().endsWith('.mov')
            );
            
            // 不再过滤视频文件，现在支持视频嵌入
            const mediaFiles = selectedImages;
            
            if (mediaFiles.length === 0) {
                showToast('请至少选择一个媒体文件（图片或视频）', 'error');
                return;
            }
            
            if (gifImages.length > 0 || videoFiles.length > 0) {
                let message = '';
                if (gifImages.length > 0) {
                    message += `检测到 ${gifImages.length} 个 GIF/WebP`;
                }
                if (videoFiles.length > 0) {
                    message += `${message ? ' 和 ' : '检测到 '}${videoFiles.length} 个视频文件`;
                }
                message += '，正在处理...';
                showToast(message, 'info');
                
                if (gifImages.length > 0) {
                    const gifVideos = await processSelectedGIFs(2.7); // 2.7秒每帧
                    if (gifVideos.length > 0) {
                        showToast(`✅ 已处理 ${gifVideos.length} 个 GIF/WebP 为视频片段`, 'success');
                    }
                }
                
                // 视频文件现在可以直接使用
                if (videoFiles.length > 0) {
                    showToast(`🎬 ${videoFiles.length} 个视频文件将作为画中画效果嵌入`, 'success');
                }
            }
            
            showToast('🚀 正在生成视频，请稍候...', 'info');
            
            // 显示进度条
            const progressContainer = document.createElement('div');
            progressContainer.id = 'videoProgress';
            progressContainer.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                z-index: 10000;
                text-align: center;
                min-width: 300px;
            `;
            
            progressContainer.innerHTML = `
                <div style="font-size: 18px; font-weight: bold; margin-bottom: 15px; color: #667eea;">🎬 正在生成视频</div>
                <div style="font-size: 14px; color: #666; margin-bottom: 20px;">请耐心等待，这可能需要几十秒...</div>
                <div style="width: 100%; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden;">
                    <div id="progressBar" style="width: 0%; height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 4px; transition: width 0.3s ease;"></div>
                </div>
                <div id="progressText" style="font-size: 12px; color: #888; margin-top: 10px;">准备中...</div>
                <button id="cancelVideoBtn" style="margin-top: 15px; padding: 8px 16px; background: #ff6b6b; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 12px;">取消</button>
            `;
            
            document.body.appendChild(progressContainer);
            
            // 模拟进度更新
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress = Math.min(progress + Math.random() * 15, 90);
                const progressBar = document.getElementById('progressBar');
                const progressText = document.getElementById('progressText');
                if (progressBar) progressBar.style.width = `${progress}%`;
                if (progressText) {
                    if (progress < 30) {
                        progressText.textContent = '正在处理图片...';
                    } else if (progress < 60) {
                        progressText.textContent = '正在合成视频...';
                    } else if (progress < 90) {
                        progressText.textContent = '正在添加音频...';
                    } else {
                        progressText.textContent = '即将完成...';
                    }
                }
            }, 800);
            
            // 取消按钮事件
            document.getElementById('cancelVideoBtn').onclick = () => {
                clearInterval(progressInterval);
                document.body.removeChild(progressContainer);
                showToast('视频生成已取消', 'info');
            };
            
            try {
                const clipPayload = buildClipPayloadForAnimatedVideo();
                
                // 获取用户选择的 BGM
                const bgmSelect = document.getElementById('bgmSelect');
                const selectedBGM = bgmSelect ? bgmSelect.value : 'static/music/background.mp3';
                            
                // 与 GitHub 第四步相同：POST /api/create-animated-video，画中画由 video_embedding_service 处理
                const response = await fetch('/api/create-animated-video', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: '',
                        main_line1: mainLine1,
                        main_line2: mainLine2 || '',
                        subtitle: subTitle || '',
                        summary: editedSummary,
                        images: clipPayload,
                        audio_path: selectedBGM,
                        title_font_key: getTitleFontKey(),
                        show_summary: getShowSummaryOnVideo(),
                        tags: (document.getElementById('editableAiTags') && document.getElementById('editableAiTags').value.trim()) || '',
                        summary_highlight_keywords: Array.isArray(editedHighlightKeywords) ? editedHighlightKeywords : []
                    })
                });
                
                const data = await response.json();
                console.log('API响应数据:', data);
                console.log('视频路径:', data.video_path);
                
                if (data.success) {
                    // 隐藏进度条
                    clearInterval(progressInterval);
                    const progressBarFinal = document.getElementById('progressBar');
                    if (progressBarFinal) progressBarFinal.style.width = '100%';
                    const progressTextFinal = document.getElementById('progressText');
                    if (progressTextFinal) progressTextFinal.textContent = '完成!';
                    
                    setTimeout(() => {
                        if (document.getElementById('videoProgress')) {
                            document.body.removeChild(document.getElementById('videoProgress'));
                        }
                    }, 1000);
                    
                    // 显示视频结果
                    const videoResultEl = document.getElementById('videoResult');
                    const videoInfoEl = document.getElementById('videoInfo');
                    const generatedVideoEl = document.getElementById('generatedVideo');
                    const downloadBtnEl = document.getElementById('downloadVideoBtn');
                    const generatedImageEl = document.getElementById('generatedImage'); // 获取父容器
                    
                    console.log('DOM元素检查:');
                    console.log('- videoResultEl:', videoResultEl);
                    console.log('- videoInfoEl:', videoInfoEl);
                    console.log('- generatedVideoEl:', generatedVideoEl);
                    console.log('- downloadBtnEl:', downloadBtnEl);
                    console.log('- generatedImageEl:', generatedImageEl);
                    
                    // 首先显示父容器
                    if (generatedImageEl) {
                        generatedImageEl.style.display = 'block';
                        console.log('✅ 父容器 generatedImage 已显示');
                    }
                    
                    if (videoResultEl) {
                        videoResultEl.style.display = 'block';
                        console.log('视频结果区域已显示');
                        
                        // 强制刷新样式
                        videoResultEl.style.visibility = 'visible';
                        videoResultEl.style.opacity = '1';
                        videoResultEl.style.height = 'auto';
                        
                        // 添加明显的视觉标记
                        videoResultEl.style.border = '3px solid #667eea';
                        videoResultEl.style.boxShadow = '0 0 20px rgba(102, 126, 234, 0.5)';
                        videoResultEl.style.zIndex = '9999';
                        videoResultEl.style.position = 'relative';
                        
                        // 检查容器尺寸
                        console.log('视频容器尺寸:', {
                            offsetWidth: videoResultEl.offsetWidth,
                            offsetHeight: videoResultEl.offsetHeight,
                            clientWidth: videoResultEl.clientWidth,
                            clientHeight: videoResultEl.clientHeight
                        });
                        
                        // 检查父元素
                        let parent = videoResultEl.parentElement;
                        let level = 0;
                        while (parent && level < 5) {
                            console.log(`父元素${level}:`, parent.tagName, parent.style.display, parent.style.visibility);
                            parent = parent.parentElement;
                            level++;
                        }
                        
                        // 滚动到结果区域
                        videoResultEl.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                    if (videoInfoEl) {
                        videoInfoEl.innerHTML = `
                            <span>🎬 时长: ${data.duration.toFixed(1)}秒</span>
                            <span>📦 大小: ${data.file_size_mb}MB</span>
                            <span>🖼️ 媒体: ${mediaFiles.length}个文件</span>
                            ${videoFiles.length > 0 ? `<span style="color: #4CAF50;">✅ 包含${videoFiles.length}个视频画中画</span>` : ''}
                        `;
                        console.log('视频信息已更新');
                    }
                    
                    if (generatedVideoEl) {
                        console.log('设置视频源:', data.video_path);
                        generatedVideoEl.src = data.video_path;
                        generatedVideoEl.load();
                        onIndexBaseVideoReady(data.video_path);
                        
                        // 强制设置视频元素样式
                        generatedVideoEl.style.display = 'block';
                        generatedVideoEl.style.visibility = 'visible';
                        generatedVideoEl.style.opacity = '1';
                        
                        // 添加视觉标记
                        generatedVideoEl.style.border = '2px dashed #764ba2';
                        
                        // 添加额外的调试信息
                        console.log('视频元素完整信息:', {
                            tagName: generatedVideoEl.tagName,
                            id: generatedVideoEl.id,
                            className: generatedVideoEl.className,
                            src: generatedVideoEl.src,
                            currentSrc: generatedVideoEl.currentSrc,
                            readyState: generatedVideoEl.readyState,
                            networkState: generatedVideoEl.networkState,
                            videoWidth: generatedVideoEl.videoWidth,
                            videoHeight: generatedVideoEl.videoHeight
                        });
                        
                        console.log('视频元素样式:', {
                            display: generatedVideoEl.style.display,
                            visibility: generatedVideoEl.style.visibility,
                            opacity: generatedVideoEl.style.opacity,
                            width: generatedVideoEl.style.width,
                            maxWidth: generatedVideoEl.style.maxWidth
                        });
                        
                        // 添加事件监听器来调试
                        generatedVideoEl.addEventListener('loadeddata', function() {
                            console.log('✅ 视频数据加载完成');
                            console.log('视频元素状态:', generatedVideoEl.readyState);
                        });
                        
                        generatedVideoEl.addEventListener('canplay', function() {
                            console.log('✅ 视频可以播放');
                        });
                        
                        generatedVideoEl.addEventListener('error', function(e) {
                            console.error('❌ 视频加载错误:', e);
                            console.error('视频元素错误信息:', generatedVideoEl.error);
                            if (generatedVideoEl.error) {
                                console.error('错误代码:', generatedVideoEl.error.code);
                                console.error('错误信息:', generatedVideoEl.error.message);
                            }
                        });
                        
                        // 测试是否能播放
                        setTimeout(() => {
                            if (generatedVideoEl.readyState >= 2) {
                                console.log('✅ 视频准备就绪，可以播放');
                                // 尝试播放测试
                                try {
                                    generatedVideoEl.play().then(() => {
                                        console.log('✅ 视频开始播放');
                                        setTimeout(() => {
                                            generatedVideoEl.pause();
                                            console.log('⏹️ 视频暂停测试');
                                        }, 1000);
                                    }).catch(e => {
                                        console.log('ℹ️ 自动播放被阻止（正常）:', e);
                                    });
                                } catch(e) {
                                    console.log('ℹ️ 播放测试异常:', e);
                                }
                            } else {
                                console.warn('⚠️ 视频还未准备好播放，当前状态:', generatedVideoEl.readyState);
                            }
                        }, 2000);
                    }
                    
                    if (downloadBtnEl) {
                        downloadBtnEl.href = data.video_path;
                        downloadBtnEl.download = `video_${new Date().getTime()}.mp4`;
                    }
                    
                    // 滚动到结果区域
                    if (videoResultEl) {
                        videoResultEl.scrollIntoView({ behavior: 'smooth' });
                    }
                    
                    showToast(`🎉 视频生成成功！时长 ${data.duration.toFixed(1)}秒`, 'success', 5000);
                } else {
                    // 隐藏进度条
                    clearInterval(progressInterval);
                    if (document.getElementById('videoProgress')) {
                        document.body.removeChild(document.getElementById('videoProgress'));
                    }
                    
                    showToast('视频生成失败: ' + data.message, 'error');
                }
            } catch (error) {
                // 隐藏进度条
                clearInterval(progressInterval);
                if (document.getElementById('videoProgress')) {
                    document.body.removeChild(document.getElementById('videoProgress'));
                }
                
                console.error('视频生成错误:', error);
                showToast('视频生成失败: ' + error.message, 'error');
            }
        }

        async function generateVideoImage() {
            if (!generatedTitle || !generatedSummary) {
                alert('请先生成AI标题和摘要');
                return;
            }

            if (selectedImages.length === 0) {
                alert('请至少选择一张图片');
                return;
            }
            
            // 检查是否有 GIF 需要特殊处理
            const gifImages = selectedImages.filter((imgObj) =>
                needsAnimationPreconvertPath(imgObj.path)
            );

            if (gifImages.length > 0) {
                showToast(`检测到 ${gifImages.length} 个 GIF/WebP，正在预处理...`, 'info');
                
                // 处理GIF为视频片段
                const gifVideos = await processSelectedGIFs(2.5); // 默认2.5秒
                if (gifVideos.length > 0) {
                    showToast(`✅ 已处理 ${gifVideos.length} 个GIF为视频片段`, 'success');
                    // 这里可以将处理后的视频路径合并到selectedImages中
                    // 或者单独处理它们
                }
            }

            try {
                const ml1 = document.getElementById('editableMainLine1')?.value.trim() || '';
                const ml2 = document.getElementById('editableMainLine2')?.value.trim() || '';
                const st = document.getElementById('editableSubTitle')?.value.trim() || '';
                const response = await fetch('/api/generate-image', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        title: '',
                        main_line1: ml1,
                        main_line2: ml2,
                        subtitle: st,
                        summary: editedSummary || generatedSummary,
                        images: selectedImages,
                        title_font_key: getTitleFontKey()
                    })
                });

                const data = await response.json();

                if (data.success) {
                    // 显示生成的关键帧（添加安全检查）
                    const generatedImageEl = document.getElementById('generatedImage');
                    const framesInfoEl = document.getElementById('framesInfo');
                    const framesContainer = document.getElementById('framesContainer');
                    const createVideoBtn = document.getElementById('createVideoBtn');
                    
                    if (generatedImageEl) generatedImageEl.style.display = 'block';
                    if (framesInfoEl) framesInfoEl.textContent = 
                        `✅ ${data.message} | 标题: ${data.title} | 摘要: ${data.summary.substring(0, 30)}...`;
                    
                    if (framesContainer) {
                        framesContainer.innerHTML = '';
                        
                        // 保存生成的帧目录路径，用于后续视频合成
                        window.generatedFramesDir = data.output_dir;
                        
                        // 显示每一帧
                        data.frames.forEach(frame => {
                            const frameCard = document.createElement('div');
                            frameCard.style.cssText = 'background: white; border-radius: 8px; padding: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);';
                            
                            frameCard.innerHTML = `
                                <div style="font-weight: bold; color: #667eea; margin-bottom: 8px;">
                                    关键帧 ${frame.frame_index}
                                </div>
                                <img src="${frame.image_path}" 
                                     style="width: 100%; border-radius: 4px; cursor: pointer;" 
                                     onclick="openImageModal(this.src, this)">
                                <div style="margin-top: 8px; display: flex; gap: 8px;">
                                    <a href="${frame.image_path}" download="frame_${frame.frame_index}.png" 
                                       class="download-btn" style="flex: 1; text-align: center; padding: 8px 12px; font-size: 13px;">
                                        📥 下载
                                    </a>
                                </div>
                            `;
                            
                            framesContainer.appendChild(frameCard);
                        });
                    }
                    
                    // 显示合成视频按钮
                    if (createVideoBtn) createVideoBtn.style.display = 'inline-block';
                    
                    showToast(`视频关键帧生成成功！共 ${data.total} 帧`, 'success');
                } else {
                    showToast('关键帧生成失败: ' + data.message, 'error');
                }
            } catch (error) {
                showToast('关键帧生成失败: ' + error.message, 'error');
            }
        }

        async function createVideo() {
            // 检查是否已有生成的视频帧目录
            if (!window.generatedFramesDir) {
                showToast('请先生成视频关键帧', 'error');
                console.error('window.generatedFramesDir is undefined');
                return;
            }
            
            console.log('使用的关键帧目录:', window.generatedFramesDir);
            
            const btn = document.getElementById('createVideoBtn');
            btn.disabled = true;
            btn.textContent = '🎬 正在合成视频...';
            
            try {
                // 获取用户选择的 BGM
                const bgmSelect = document.getElementById('bgmSelect');
                const selectedBGM = bgmSelect ? bgmSelect.value : 'static/music/background.mp3';
                
                const response = await fetch('/api/create-video', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        frames_dir: window.generatedFramesDir,
                        duration_per_frame: 2.5,
                        audio_path: selectedBGM  // 使用用户选择的 BGM
                    })
                });
                
                const data = await response.json();
                console.log('视频生成响应:', data);
                
                if (data.success) {
                    // 显示视频结果（添加安全检查）
                    const videoResult = document.getElementById('videoResult');
                    const videoInfo = document.getElementById('videoInfo');
                    const videoPlayer = document.getElementById('generatedVideo');
                    const downloadBtn = document.getElementById('downloadVideoBtn');
                    
                    if (videoInfo) videoInfo.textContent = `🎬 关键帧: ${data.frames_count} | 时长: ${data.duration.toFixed(1)}秒 | 大小: ${data.file_size_mb}MB`;
                    if (videoPlayer) videoPlayer.src = data.video_path;
                    if (downloadBtn) {
                        downloadBtn.href = data.video_path;
                        downloadBtn.download = data.video_path.split('/').pop();
                    }
                    if (videoResult) videoResult.style.display = 'block';
                    const genImgEl = document.getElementById('generatedImage');
                    if (genImgEl) genImgEl.style.display = 'block';
                    onIndexBaseVideoReady(data.video_path);
                    
                    showToast(`视频生成成功！时长 ${data.duration.toFixed(1)}秒，大小 ${data.file_size_mb}MB`, 'success', 4500);
                } else {
                    showToast('视频生成失败: ' + data.message, 'error');
                }
            } catch (error) {
                console.error('视频生成错误:', error);
                showToast('视频生成失败: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '🎬 合成视频 (带背景音乐)';
            }
        }

        async function oneClickGenerate() {
            const btn = document.getElementById('oneClickBtn');
            const originalText = btn.textContent;
            btn.disabled = true;

            const content = document.getElementById('contentEditor').value;
            if (!content.trim()) {
                showToast('请先抓取网页内容', 'error');
                btn.disabled = false;
                return;
            }

            // 如果没有手动选择图片，自动选择前5张
            if (selectedImages.length === 0) {
                const allImgs = document.querySelectorAll('.selectable-image, .selectable-video');
                const maxAuto = Math.min(allImgs.length, 5);
                for (let i = 0; i < maxAuto; i++) {
                    if (!allImgs[i].classList.contains('selected')) {
                        toggleImageSelection(allImgs[i]);
                    }
                }
                if (selectedImages.length === 0) {
                    showToast('没有可用的图片', 'error');
                    btn.disabled = false;
                    return;
                }
                showToast(`已自动选择 ${selectedImages.length} 张图片`, 'info');
            }

            try {
                const hadAnimRaster = selectedImages.some((o) =>
                    needsAnimationPreconvertPath(o.path)
                );
                if (hadAnimRaster) {
                    btn.textContent = '🚀 [1/3] 转换 GIF/WebP 为视频…';
                    showToast(
                        '检测到 GIF 或 WebP：先转为 MP4（画中画），再生成摘要与成片…',
                        'info',
                        4500
                    );
                    await processSelectedGIFs(2.7, { silentIfEmpty: true });
                }

                // 第1步（无预转换时为第1步）：生成AI标题和摘要
                btn.textContent = hadAnimRaster ? '🚀 [2/3] 生成标题摘要…' : '🚀 [1/2] 生成标题摘要…';
                showToast('开始一键生成：正在生成AI标题和摘要...', 'info');

                const summaryDiv = document.getElementById('aiSummary');
                if (summaryDiv) summaryDiv.style.display = 'block';
                
                // 使用新的可编辑输入框ID（避免变量名冲突）
                const oneClickL1 = document.getElementById('editableMainLine1');
                const oneClickL2 = document.getElementById('editableMainLine2');
                const oneClickSubTitleEl = document.getElementById('editableSubTitle');
                const oneClickSummaryEl = document.getElementById('editableAiSummary');
                const oneClickVoiceoverEl = document.getElementById('editableVoiceoverScript');
                
                if (oneClickL1) oneClickL1.value = '正在生成…';
                if (oneClickL2) oneClickL2.value = '正在生成…';
                if (oneClickSubTitleEl) oneClickSubTitleEl.value = '正在生成…';
                if (oneClickSummaryEl) oneClickSummaryEl.value = '正在生成摘要...';
                if (oneClickVoiceoverEl) oneClickVoiceoverEl.value = '正在生成口播稿...';

                const oneClickVoLen = getVoiceoverLengthParams();
                const summaryResp = await fetch('/api/generate-summary', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        content: content,
                        images: selectedImages.map((imgObj) => imgObj.path),
                        title: currentData ? currentData.title : '',
                        voiceover_min_chars: oneClickVoLen.voiceover_min_chars,
                        voiceover_max_chars: oneClickVoLen.voiceover_max_chars
                    })
                });
                const summaryData = await summaryResp.json();

                if (!summaryData.success) {
                    showToast('标题摘要生成失败: ' + summaryData.message, 'error');
                    if (oneClickVoiceoverEl) oneClickVoiceoverEl.value = '';
                    btn.disabled = false;
                    btn.textContent = originalText;
                    return;
                }

                generatedTitle = summaryData.title;
                generatedSummary = summaryData.summary;
                const l1 = summaryData.main_line1 != null ? summaryData.main_line1 : (summaryData.main_title || (summaryData.title || '').split('|')[0] || '');
                const l2 = summaryData.main_line2 != null ? summaryData.main_line2 : '';
                const subT2 = summaryData.sub_title != null ? summaryData.sub_title : '';
                const voOne = summaryData.voiceover_script != null ? summaryData.voiceover_script : '';
                
                // 填充到可编辑输入框（添加安全检查）
                const aiMainLine1El = document.getElementById('editableMainLine1');
                const aiMainLine2El = document.getElementById('editableMainLine2');
                const aiSubTitleEl = document.getElementById('editableSubTitle');
                const aiSummaryEl = document.getElementById('editableAiSummary');
                const aiVoiceoverFillEl = document.getElementById('editableVoiceoverScript');
                const aiTagsEl = document.getElementById('editableAiTags');
                const aiMetaEl = document.getElementById('aiMeta');
                
                if (aiMainLine1El) aiMainLine1El.value = l1;
                if (aiMainLine2El) aiMainLine2El.value = l2;
                if (aiSubTitleEl) aiSubTitleEl.value = subT2;
                if (aiSummaryEl) aiSummaryEl.value = summaryData.summary;
                if (aiVoiceoverFillEl) aiVoiceoverFillEl.value = voOne;
                if (aiTagsEl) aiTagsEl.value = summaryData.tags || '';
                editedHighlightKeywords = Array.isArray(summaryData.highlight_keywords)
                    ? summaryData.highlight_keywords.slice()
                    : [];
                if (aiMetaEl) aiMetaEl.textContent =
                    `L1:${l1.length} L2:${l2.length} 副:${subT2.length} | 摘要:${(summaryData.summary || '').length}字 口播:${voOne.length}字 高亮:${editedHighlightKeywords.length}词 | ${summaryData.model} | tokens:${summaryData.tokens_used}`;
                
                // 自动保存内容
                saveEditedContent();

                showToast('✅ 标题摘要已生成，开始合成动画视频...', 'success');

                // 第2步：合成动画视频（带弹入特效）
                btn.textContent = hadAnimRaster ? '🚀 [3/3] 合成动画视频…' : '🚀 [2/2] 合成动画视频…';

                const videoResp = await fetch('/api/create-animated-video', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: '',
                        main_line1: l1,
                        main_line2: l2 || '',
                        subtitle: subT2 || '',
                        summary: editedSummary || generatedSummary,
                        images: buildClipPayloadForAnimatedVideo(),
                        audio_path: 'static/music/background.mp3',
                        title_font_key: getTitleFontKey(),
                        show_summary: getShowSummaryOnVideo(),
                        tags: (document.getElementById('editableAiTags') && document.getElementById('editableAiTags').value.trim()) || '',
                        summary_highlight_keywords: Array.isArray(editedHighlightKeywords) ? editedHighlightKeywords : []
                    })
                });
                const videoData = await videoResp.json();

                if (videoData.success) {
                    // 显示预览帧（添加安全检查）
                    const generatedImageEl = document.getElementById('generatedImage');
                    const framesInfoEl = document.getElementById('framesInfo');
                    
                    if (generatedImageEl) generatedImageEl.style.display = 'block';
                    if (framesInfoEl) framesInfoEl.textContent =
                        `✅ 动画视频已生成 | 片段: ${videoData.preview_frames.length} | 标题: ${generatedTitle}`;
                    
                    // 显示预览帧
                    if (videoData.preview_frames && videoData.preview_frames.length > 0) {
                        const framesContainer = document.getElementById('framesContainer');
                        if (framesContainer) {
                            framesContainer.innerHTML = '';
                            videoData.preview_frames.forEach((framePath, i) => {
                                const frameCard = document.createElement('div');
                                frameCard.style.cssText = 'background: white; border-radius: 8px; padding: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);';
                                frameCard.innerHTML = `
                                    <div style="font-weight: bold; color: #667eea; margin-bottom: 8px;">片段 ${i + 1} 预览</div>
                                    <img src="${framePath}" style="width: 100%; border-radius: 4px; cursor: pointer;" onclick="openImageModal(this.src, this)">
                                `;
                                framesContainer.appendChild(frameCard);
                            });
                        }
                    }

                    const videoResult = document.getElementById('videoResult');
                    const videoInfo = document.getElementById('videoInfo');
                    const videoPlayer = document.getElementById('generatedVideo');
                    const downloadBtn = document.getElementById('downloadVideoBtn');

                    if (videoInfo) videoInfo.textContent = `🎬 片段: ${videoData.preview_frames ? videoData.preview_frames.length : '?'} | 时长: ${videoData.duration.toFixed(1)}秒 | 大小: ${videoData.file_size_mb}MB`;
                    if (videoPlayer) videoPlayer.src = videoData.video_path;
                    if (downloadBtn) {
                        downloadBtn.href = videoData.video_path;
                        downloadBtn.download = videoData.video_path.split('/').pop();
                    }
                    if (videoResult) videoResult.style.display = 'block';
                    onIndexBaseVideoReady(videoData.video_path);

                    showToast(`🎉 一键生成完成！时长 ${videoData.duration.toFixed(1)}秒，大小 ${videoData.file_size_mb}MB`, 'success', 5000);
                } else {
                    showToast('视频合成失败: ' + videoData.message, 'error');
                }
            } catch (error) {
                showToast('一键生成失败: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }

        function resetSelection() {
            // 清除所有选择
            document.querySelectorAll('.selectable-image, .selectable-video').forEach(img => {
                img.classList.remove('selected');
            });
            selectedImages = [];
            
            // 重置内容
            if (currentData && currentData.content_file) {
                fetch(currentData.content_file)
                    .then(response => response.text())
                    .then(content => {
                        const lines = content.split('\n');
                        const contentStart = lines.findIndex(line => line.includes('===='));
                        const actualContent = lines.slice(contentStart + 2).join('\n').trim();
                        document.getElementById('contentEditor').value = actualContent;
                    });
            }
            
            // 隐藏排序面板
            hideSortPanel();
            
            // 隐藏AI摘要
            document.getElementById('aiSummary').style.display = 'none';
            
            alert('已重置所有选择');
        }

        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = '❌ ' + message;
            errorDiv.classList.add('active');
        }

        // 支持回车键提交
        document.getElementById('urlInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                fetchUrl();
            }
        });

