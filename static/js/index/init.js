        // 页面加载完成后初始化
        document.addEventListener('DOMContentLoaded', function() {
            // 初始化事件监听器
            initializeEventListeners();
            // 加载 BGM 列表
            loadBGMList();
            loadBackgroundImageList();
            loadTitleFontList();
            loadIndexSubtitleFonts();
            // 背景图选择 change 时同步预览
            const _bgSel = document.getElementById('bgSelect');
            if (_bgSel) {
                _bgSel.onchange = () => {
                    const p = document.getElementById('bgPreview');
                    if (p) p.src = '/' + _bgSel.value;
                };
            }
            // 开发模式：URL 含 ?dev=1 时显示 .dev-only 面板
            applyDevMode();
            importIngestedArticleFromSession();
        });

        async function importIngestedArticleFromSession() {
            const params = new URLSearchParams(location.search);
            if (params.get('from') !== 'ingestion') return;

            const loadingEl = document.getElementById('loading');
            if (loadingEl) loadingEl.classList.add('active');

            try {
                const articleId = params.get('article_id');
                let data = null;

                if (articleId) {
                    const resp = await fetch(`/api/ingestion/articles/${encodeURIComponent(articleId)}/prepare-video?auto_select=true&sort_by_relevance=true`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                    });
                    const prep = await resp.json().catch(() => ({}));
                    if (!resp.ok) {
                        throw new Error(prep.detail || prep.message || `HTTP ${resp.status}`);
                    }
                    data = {
                        url: prep.metadata?.url || prep.metadata?.canonical_url,
                        title: prep.title || prep.metadata?.title || '',
                        content: prep.content || '',
                        ingested_article_id: prep.article_id || articleId,
                        images: prep.images || [],
                        video_draft: prep.video_draft || prep.metadata?.video_draft || null,
                        generated_video_path: prep.generated_video_path || prep.metadata?.generated_video_path || null,
                        source: 'ingestion',
                    };
                } else {
                    const raw = sessionStorage.getItem('ainews_ingested_import');
                    if (!raw) return;
                    data = JSON.parse(raw);
                    sessionStorage.removeItem('ainews_ingested_import');
                }

                const urlInput = document.getElementById('urlInput');
                if (urlInput && data.url) urlInput.value = data.url;

                const normalizedImages = (data.images || []).map((img, index) => {
                    if (typeof window.ImageScoreUI !== 'undefined') {
                        return window.ImageScoreUI.normalizeIngestionImage(img, index);
                    }
                    if (typeof img === 'string') {
                        return { url: img, local_path: img, success: true };
                    }
                    const localPath = img.local_path || '';
                    const remoteUrl = img.url || localPath;
                    return {
                        url: remoteUrl,
                        local_path: localPath || remoteUrl,
                        success: img.success !== false,
                        alt: img.alt || `图片 ${index + 1}`,
                        source: img.source || 'ingestion',
                        auto_selected: img.auto_selected === true,
                    };
                });

                const resultPayload = {
                    url: data.url,
                    title: data.title || '',
                    content: data.content || '',
                    timestamp: new Date().toISOString(),
                    content_length: (data.content || '').length,
                    images_count: normalizedImages.length,
                    images: normalizedImages,
                    content_preview: (data.content || '').substring(0, 500),
                    ingested_article_id: data.ingested_article_id,
                    source: data.source || 'ingestion',
                };

                if (typeof displayResult === 'function') {
                    displayResult(resultPayload);
                } else {
                    const contentEditor = document.getElementById('contentEditor');
                    if (contentEditor) contentEditor.value = data.content || '';
                    const resultEl = document.getElementById('result');
                    if (resultEl) resultEl.classList.add('active');
                    const editSection = document.getElementById('editSection');
                    if (editSection) editSection.classList.add('active');
                }

                if (data.video_draft && data.video_draft.success) {
                    applyIngestionVideoDraft(data.video_draft);
                }

                if (data.generated_video_path) {
                    const videoResult = document.getElementById('videoResult');
                    const generatedVideo = document.getElementById('generatedVideo');
                    const generatedImage = document.getElementById('generatedImage');
                    if (generatedImage) generatedImage.style.display = 'block';
                    if (videoResult) videoResult.style.display = 'block';
                    if (generatedVideo) {
                        generatedVideo.src = data.generated_video_path;
                        generatedVideo.style.display = 'block';
                    }
                    const downloadBtn = document.getElementById('downloadVideoBtn');
                    if (downloadBtn) downloadBtn.href = data.generated_video_path;
                }

                if (typeof showToast === 'function') {
                    const imgNote = normalizedImages.length ? `、${normalizedImages.length} 张图片` : '';
                    const scoredNote = (typeof window.ImageScoreUI !== 'undefined' && window.ImageScoreUI.hasImageScores(normalizedImages))
                        ? '（含配图评分，已按相关度排序）'
                        : '';
                    const draftNote = (data.video_draft && data.video_draft.success) ? '、已填入 AI 标题摘要' : '';
                    showToast(`已从资讯库导入文章（正文 ${(data.content || '').length} 字${imgNote}）${scoredNote}${draftNote}`, 'success', 4000);
                }

                if (window.history && window.history.replaceState) {
                    const clean = new URL(window.location.href);
                    clean.searchParams.delete('from');
                    clean.searchParams.delete('article_id');
                    window.history.replaceState({}, '', clean.pathname + clean.search);
                }
            } catch (e) {
                console.warn('import ingested failed', e);
                if (typeof showToast === 'function') {
                    showToast('资讯库导入失败：' + (e.message || '未知错误'), 'error', 5000);
                }
            } finally {
                if (loadingEl) loadingEl.classList.remove('active');
            }
        }

        function applyIngestionVideoDraft(draft) {
            if (!draft || !draft.success) return;
            const line1 = draft.main_line1 != null ? draft.main_line1 : (draft.main_title || (draft.title || '').split('|')[0] || '');
            const line2 = draft.main_line2 != null ? draft.main_line2 : '';
            const subT = draft.sub_title != null ? draft.sub_title : '';
            const subT2 = draft.sub_title2 != null ? draft.sub_title2 : '';
            const summaryText = draft.summary || '';
            const voText = draft.voiceover_script != null ? draft.voiceover_script : '';

            generatedTitle = draft.title || '';
            generatedSummary = summaryText;

            const el1 = document.getElementById('editableMainLine1');
            const el2 = document.getElementById('editableMainLine2');
            const elSub = document.getElementById('editableSubTitle');
            const elSub2 = document.getElementById('editableSubTitle2');
            const elSummary = document.getElementById('editableAiSummary');
            const elVo = document.getElementById('editableVoiceoverScript');
            const elTags = document.getElementById('editableAiTags');
            const elMeta = document.getElementById('aiMeta');

            if (el1) el1.value = line1;
            if (el2) el2.value = line2;
            if (elSub) elSub.value = subT;
            if (elSub2) elSub2.value = subT2;
            if (elSummary) elSummary.value = summaryText;
            if (elVo) elVo.value = voText;
            if (elTags) elTags.value = draft.tags || '';
            editedHighlightKeywords = Array.isArray(draft.highlight_keywords) ? draft.highlight_keywords.slice() : [];

            window.lastPublishDraft = {
                main_line1: line1,
                main_line2: line2,
                sub_title: subT,
                sub_title2: subT2,
                praise_tags: draft.praise_tags || [],
                tags: draft.tags || [],
                source_type: 'ingestion',
            };

            if (typeof setAiMethodologyInsight === 'function') {
                setAiMethodologyInsight(draft.target_audience, draft.praise_tags, draft.traffic_hook);
            }
            if (typeof renderComplianceWarning === 'function' && draft.compliance) {
                renderComplianceWarning(draft.compliance);
            }
            if (elMeta) {
                elMeta.textContent =
                    `主L1:${line1.length}字 L2:${line2.length}字 副1:${subT.length}字 副2:${subT2.length}字 | ` +
                    `摘要:${summaryText.length}字 口播:${voText.length}字 | ${draft.model || 'ingestion'}`;
            }
            const aiSummarySection = document.getElementById('aiSummary');
            if (aiSummarySection) aiSummarySection.style.display = 'block';
            if (typeof saveEditedContent === 'function') saveEditedContent();
        }

        function applyDevMode() {
            try {
                const params = new URLSearchParams(location.search);
                const dev = params.get('dev') === '1' || localStorage.getItem('devMode') === '1';
                if (dev) {
                    document.querySelectorAll('.dev-only').forEach(el => el.classList.add('is-visible'));
                }
            } catch (e) { /* ignore */ }
        }
        
        function initializeEventListeners() {
            // 排序面板相关事件
            const closeBtn = document.getElementById('closeSortPanel');
            const resetBtn = document.getElementById('resetOrder');
            
            if (closeBtn) {
                closeBtn.addEventListener('click', hideSortPanel);
            }
            
            if (resetBtn) {
                resetBtn.addEventListener('click', resetImageOrder);
            }

            // 图片/视频选择器：悬停原图/原视频预览
            _attachMediaSelectorHover();
        }
        
        /**
         * 动态加载 BGM 列表
         */
        /**
         * 动态加载背景图列表并初始化预览
         */
        async function loadBackgroundImageList() {
            const sel = document.getElementById('bgSelect');
            const preview = document.getElementById('bgPreview');
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
            } finally {
                if (preview) preview.src = '/' + (sel.value || 'static/imgs/bg.png');
            }
        }

        async function loadBGMList() {
            try {
                // 读取 static/music 目录下的所有 mp3 文件
                const response = await fetch('/api/list-music-files');
                const data = await response.json();
                
                if (data.success && Array.isArray(data.files)) {
                    const bgmSelect = document.getElementById('bgmSelect');
                    
                    // 保留第一个默认选项，清空其他选项
                    while (bgmSelect.options.length > 1) {
                        bgmSelect.remove(1);
                    }
                    
                    // 添加所有音乐文件到下拉框
                    data.files.forEach(file => {
                        const option = document.createElement('option');
                        option.value = file.path;
                        option.textContent = file.name || file.path.split('/').pop();
                        bgmSelect.appendChild(option);
                    });
                    
                    console.log(`已加载 ${data.files.length} 个 BGM 文件`);
                }
            } catch (error) {
                console.error('加载 BGM 列表失败:', error);
                // 如果 API 调用失败，使用硬编码的备用列表
                loadFallbackBGMList();
            }
        }
        
        /**
         * 备用 BGM 列表（当 API 不可用时）
         */
        async function loadTitleFontList() {
            try {
                const response = await fetch('/api/list-title-fonts');
                const data = await response.json();
                const sel = document.getElementById('titleFontSelect');
                if (!sel || !data.success || !Array.isArray(data.fonts)) return;
                while (sel.options.length) sel.remove(0);
                data.fonts.forEach((f) => {
                    const opt = document.createElement('option');
                    opt.value = f.key;
                    opt.textContent = f.label || f.key;
                    sel.appendChild(opt);
                });
            } catch (e) {
                console.warn('加载主标题字体列表失败', e);
            }
        }

        async function loadIndexSubtitleFonts() {
            const sel = document.getElementById('indexVoiceoverSubtitleFont');
            if (!sel) return;
            const fallback = [
                { fontname: 'Microsoft YaHei', label: '微软雅黑（系统）' },
                { fontname: 'SimHei', label: '黑体 SimHei（系统）' },
                { fontname: 'SimSun', label: '宋体 SimSun（系统）' },
                { fontname: 'KaiTi', label: '楷体 KaiTi（系统）' },
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
                console.warn('加载字幕字体列表失败', e);
            }
            sel.innerHTML = '';
            fallback.forEach((f) => {
                const opt = document.createElement('option');
                opt.value = f.fontname;
                opt.textContent = f.label;
                sel.appendChild(opt);
            });
            sel.value = 'Microsoft YaHei';
        }

        function loadFallbackBGMList() {
            const bgmSelect = document.getElementById('bgmSelect');
            const fallbackFiles = [
                { path: 'static/music/background.mp3', name: '🎵 默认背景音乐' },
                { path: 'static/music/background3.mp3', name: '🎵 背景音乐 3' },
                { path: 'static/music/background4.mp3', name: '🎵 背景音乐 4' }
            ];
            
            // 保留第一个默认选项
            while (bgmSelect.options.length > 1) {
                bgmSelect.remove(1);
            }
            
            // 添加备用列表
            fallbackFiles.forEach(file => {
                const option = document.createElement('option');
                option.value = file.path;
                option.textContent = file.name;
                bgmSelect.appendChild(option);
            });
        }
        
        /** 主标题两行 + 副标题（供调试或扩展使用） */
        function getAnimatedTitlePayload() {
            return {
                main_line1: document.getElementById('editableMainLine1')?.value.trim() || '',
                main_line2: document.getElementById('editableMainLine2')?.value.trim() || '',
                main_line1_color: (document.querySelector('input[name="mainLine1Color"]:checked') || {}).value || '#FFFFFF',
                main_line2_color: (document.querySelector('input[name="mainLine2Color"]:checked') || {}).value || '#FFFFFF',
                title_font_size: (() => { const v = parseInt(document.getElementById('titleFontSizeInput')?.value, 10); return (v >= 28 && v <= 120) ? v : null; })(),
                ...getLayoutPositionPayload(),
                subtitle: document.getElementById('editableSubTitle')?.value.trim() || ''
            };
        }
        
        // ==================== 视频查看功能 ====================
        
        function openVideoModal(videoPath) {
            console.log('打开视频模态框:', videoPath);
            
            const overlay = document.getElementById('videoModalOverlay');
            const videoPlayer = document.getElementById('videoPlayer');
            const videoInfo = document.getElementById('videoInfo');
            
            if (!overlay || !videoPlayer || !videoInfo) {
                console.error('视频模态框元素缺失');
                return;
            }
            
            // 设置视频源
            videoPlayer.src = videoPath;
            videoPlayer.load();
            
            // 显示基本信息
            const filename = videoPath.split('/').pop();
            videoInfo.innerHTML = `
                <strong>文件:</strong> ${filename}<br>
                <strong>状态:</strong> 加载中...
            `;
            
            // 视频加载事件
            videoPlayer.onloadedmetadata = function() {
                const duration = videoPlayer.duration;
                const minutes = Math.floor(duration / 60);
                const seconds = Math.floor(duration % 60);
                videoInfo.innerHTML = `
                    <strong>文件:</strong> ${filename}<br>
                    <strong>时长:</strong> ${minutes}:${seconds.toString().padStart(2, '0')}<br>
                    <strong>分辨率:</strong> ${videoPlayer.videoWidth}×${videoPlayer.videoHeight}
                `;
            };
            
            videoPlayer.onerror = function(e) {
                videoInfo.innerHTML = `
                    <strong>文件:</strong> ${filename}<br>
                    <strong style="color: #e74c3c;">错误:</strong> 视频加载失败
                `;
                console.error('视频加载错误:', e);
            };
            
            // 显示模态框
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
        
        function closeVideoModal() {
            const overlay = document.getElementById('videoModalOverlay');
            const videoPlayer = document.getElementById('videoPlayer');
            
            if (overlay) {
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }
            
            if (videoPlayer) {
                videoPlayer.pause();
                videoPlayer.currentTime = 0;
            }
        }
        
        function downloadCurrentVideo() {
            const videoPlayer = document.getElementById('videoPlayer');
            if (videoPlayer && videoPlayer.src) {
                const link = document.createElement('a');
                link.href = videoPlayer.src;
                link.download = 'video_' + new Date().getTime() + '.mp4';
                link.click();
            }
        }
        
        // 点击模态框外部关闭
        document.addEventListener('click', function(e) {
            if (e.target.id === 'videoModalOverlay') {
                closeVideoModal();
            }
        });
