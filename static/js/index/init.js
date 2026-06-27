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
        });

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
