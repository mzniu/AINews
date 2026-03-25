// video_editor3.js - 视频文字编辑器主逻辑

class VideoTextEditor {
    constructor() {
        this.videoFile = null;
        this.videoElement = null;
        this.canvas = null;
        this.ctx = null;
        this.textSettings = {};
        this.animationFrame = null;
        this.isPlaying = false;
        this.init();
    }

    init() {
        this.bindEvents();
        this.setupCanvas();
        console.log('🎬 视频文字编辑器已初始化');
    }

    bindEvents() {
        // 文件上传事件
        const videoInput = document.getElementById('videoInput');
        const uploadArea = document.getElementById('videoUploadArea');
        
        videoInput.addEventListener('change', (e) => {
            this.handleVideoUpload(e.target.files[0]);
        });

        // 拖拽上传
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        });

        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            this.handleVideoUpload(e.dataTransfer.files[0]);
        });

        // 点击上传区域触发文件选择
        uploadArea.addEventListener('click', () => {
            if (!this.videoFile) {
                videoInput.click();
            }
        });

        // 移除视频
        document.getElementById('removeVideo').addEventListener('click', () => {
            this.removeVideo();
        });

        // 位置选择变化
        document.getElementById('textPosition').addEventListener('change', (e) => {
            const customPos = document.getElementById('customPosition');
            customPos.style.display = e.target.value === 'custom' ? 'block' : 'none';
            this.updatePreview();
        });

        // 时长滑块
        document.getElementById('displayDuration').addEventListener('input', (e) => {
            document.getElementById('durationValue').textContent = e.target.value + '秒';
            this.updatePreview();
        });

        // 其他设置变化时更新预览
        const settingsElements = [
            'textContent', 'fontSize', 'fontColor', 'textAlign', 
            'backgroundEffect', 'animationEffect', 'positionX', 'positionY'
        ];
        
        settingsElements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('input', () => this.updatePreview());
                element.addEventListener('change', () => this.updatePreview());
            }
        });

        // 生成按钮
        document.getElementById('generateBtn').addEventListener('click', () => {
            this.generateVideo();
        });

        // 预览控制
        document.getElementById('playPreview').addEventListener('click', () => {
            this.playPreview();
        });

        document.getElementById('pausePreview').addEventListener('click', () => {
            this.pausePreview();
        });

        // 新建编辑
        document.getElementById('newEditBtn').addEventListener('click', () => {
            this.resetEditor();
        });
    }

    setupCanvas() {
        this.canvas = document.getElementById('overlayCanvas');
        this.ctx = this.canvas.getContext('2d');
        console.log('🎨 Canvas已初始化');
    }

    async handleVideoUpload(file) {
        console.log('📥 处理视频上传:', file?.name);
        
        if (!file || !file.type.startsWith('video/')) {
            this.showToast('请选择有效的视频文件！', 'error');
            return;
        }

        // 检查文件大小（限制100MB）
        if (file.size > 100 * 1024 * 1024) {
            this.showToast('视频文件过大，请选择小于100MB的文件', 'error');
            return;
        }

        this.videoFile = file;
        
        // 显示文件信息
        const videoInfo = document.getElementById('videoInfo');
        const uploadPlaceholder = document.getElementById('uploadPlaceholder');
        const videoName = document.getElementById('videoName');
        const videoSize = document.getElementById('videoSize');
        
        videoName.textContent = file.name;
        videoSize.textContent = (file.size / 1024 / 1024).toFixed(2) + ' MB';
        
        uploadPlaceholder.style.display = 'none';
        videoInfo.style.display = 'block';
        
        // 创建视频预览
        const videoUrl = URL.createObjectURL(file);
        const videoPreview = document.getElementById('videoPreview');
        videoPreview.src = videoUrl;
        videoPreview.style.display = 'block';
        
        // 获取视频时长和尺寸信息
        videoPreview.onloadedmetadata = () => {
            const duration = document.getElementById('videoDuration');
            duration.textContent = `时长: ${Math.floor(videoPreview.duration)}秒`;
            
            // 设置画布尺寸
            this.canvas.width = videoPreview.videoWidth;
            this.canvas.height = videoPreview.videoHeight;
            console.log(`📹 视频尺寸: ${videoPreview.videoWidth}x${videoPreview.videoHeight}`);
        };
        
        // 视频加载完成后启用生成按钮
        videoPreview.addEventListener('loadeddata', () => {
            document.getElementById('generateBtn').disabled = false;
            this.updatePreview();
            this.showToast('视频上传成功！', 'success');
        });
        
        // 错误处理
        videoPreview.addEventListener('error', (e) => {
            console.error('视频加载失败:', e);
            this.showToast('视频文件无法播放，请检查文件格式', 'error');
            this.removeVideo();
        });
    }

    removeVideo() {
        console.log('🗑️ 移除视频');
        
        // 重置状态
        this.videoFile = null;
        this.videoElement = null;
        
        // 清理UI
        document.getElementById('videoPreview').style.display = 'none';
        document.getElementById('uploadPlaceholder').style.display = 'block';
        document.getElementById('videoInfo').style.display = 'none';
        document.getElementById('generateBtn').disabled = true;
        
        // 清理画布
        if (this.ctx) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
        
        // 重置文件输入
        document.getElementById('videoInput').value = '';
        
        this.showToast('视频已移除', 'info');
    }

    collectTextSettings() {
        this.textSettings = {
            content: document.getElementById('textContent').value.trim(),
            fontSize: parseInt(document.getElementById('fontSize').value),
            fontColor: document.getElementById('fontColor').value,
            position: document.getElementById('textPosition').value,
            align: document.getElementById('textAlign').value,
            background: document.getElementById('backgroundEffect').value,
            animation: document.getElementById('animationEffect').value,
            duration: parseInt(document.getElementById('displayDuration').value),
            posX: parseInt(document.getElementById('positionX').value) || 0,
            posY: parseInt(document.getElementById('positionY').value) || 0
        };
        
        console.log('📝 文字设置:', this.textSettings);
        return this.textSettings;
    }

    updatePreview() {
        if (!this.videoFile) return;
        
        this.collectTextSettings();
        this.drawPreview();
    }

    drawPreview() {
        if (!this.ctx || !this.textSettings.content) {
            return;
        }

        // 清除画布
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 绘制文字
        this.drawTextOnCanvas(this.textSettings);
    }

    drawTextOnCanvas(settings) {
        const { content, fontSize, fontColor, position, align, background } = settings;
        
        // 设置字体和颜色
        this.ctx.font = `bold ${fontSize}px Arial, Microsoft YaHei, sans-serif`;
        this.ctx.fillStyle = fontColor;
        this.ctx.textAlign = align;
        this.ctx.textBaseline = 'middle';
        
        // 计算文字位置
        let x, y;
        switch (position) {
            case 'top':
                x = this.canvas.width / 2;
                y = fontSize + 30;
                break;
            case 'center':
                x = this.canvas.width / 2;
                y = this.canvas.height / 2;
                break;
            case 'bottom':
                x = this.canvas.width / 2;
                y = this.canvas.height - fontSize - 30;
                break;
            case 'custom':
                x = settings.posX;
                y = settings.posY;
                break;
        }
        
        // 绘制背景
        if (background !== 'none') {
            const textMetrics = this.ctx.measureText(content);
            const textWidth = textMetrics.width;
            const padding = 15;
            
            // 根据背景类型设置样式
            if (background === 'solid') {
                this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            } else if (background === 'gradient') {
                const gradient = this.ctx.createLinearGradient(x - textWidth/2 - padding, y - fontSize, 
                                                              x + textWidth/2 + padding, y + fontSize);
                gradient.addColorStop(0, 'rgba(0, 0, 0, 0.8)');
                gradient.addColorStop(1, 'rgba(50, 50, 50, 0.6)');
                this.ctx.fillStyle = gradient;
            } else if (background === 'outline') {
                // 描边效果在后面处理
            }
            
            if (background !== 'outline') {
                this.ctx.fillRect(
                    x - textWidth/2 - padding, 
                    y - fontSize - padding,
                    textWidth + padding * 2, 
                    fontSize * 2 + padding * 2
                );
                this.ctx.fillStyle = fontColor; // 恢复文字颜色
            }
        }
        
        // 绘制描边（如果选择了描边效果）
        if (background === 'outline') {
            this.ctx.strokeStyle = 'rgba(0, 0, 0, 0.8)';
            this.ctx.lineWidth = 3;
            this.ctx.strokeText(content, x, y);
        }
        
        // 绘制主文字
        this.ctx.fillText(content, x, y);
    }

    playPreview() {
        const video = document.getElementById('videoPreview');
        if (video && video.readyState >= 2) {
            video.play();
            this.isPlaying = true;
            this.animateTextOverlay();
            console.log('▶️ 开始预览');
        } else {
            this.showToast('请先上传并加载视频', 'info');
        }
    }

    pausePreview() {
        const video = document.getElementById('videoPreview');
        if (video) {
            video.pause();
            this.isPlaying = false;
            if (this.animationFrame) {
                cancelAnimationFrame(this.animationFrame);
            }
            console.log('⏸️ 暂停预览');
        }
    }

    animateTextOverlay() {
        if (!this.isPlaying) return;
        
        const video = document.getElementById('videoPreview');
        if (video.paused || video.ended) {
            this.isPlaying = false;
            return;
        }
        
        // 更新画布尺寸（如果视频尺寸改变）
        if (this.canvas.width !== video.videoWidth || this.canvas.height !== video.videoHeight) {
            this.canvas.width = video.videoWidth;
            this.canvas.height = video.videoHeight;
        }
        
        // 清除并重新绘制
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.drawTextOnCanvas(this.textSettings);
        
        this.animationFrame = requestAnimationFrame(() => this.animateTextOverlay());
    }

    async generateVideo() {
        console.log('🎬 开始生成视频...');
        
        this.collectTextSettings();
        
        if (!this.videoFile) {
            this.showToast('请先上传视频文件！', 'error');
            return;
        }
        
        if (!this.textSettings.content) {
            this.showToast('请输入要添加的文字内容！', 'error');
            return;
        }

        // 显示加载状态
        const generateBtn = document.getElementById('generateBtn');
        const originalText = generateBtn.innerHTML;
        generateBtn.innerHTML = '⏳ 处理中...';
        generateBtn.disabled = true;

        try {
            const formData = new FormData();
            formData.append('video', this.videoFile);
            formData.append('settings', JSON.stringify(this.textSettings));

            const response = await fetch('/api/add-text-to-video', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            console.log('✅ 生成结果:', result);
            
            if (result.success) {
                this.showResult(result);
                this.showToast('视频生成成功！', 'success');
            } else {
                throw new Error(result.message || '生成失败');
            }
            
        } catch (error) {
            console.error('❌ 生成视频失败:', error);
            this.showToast(`生成失败: ${error.message}`, 'error');
        } finally {
            // 恢复按钮状态
            generateBtn.innerHTML = originalText;
            generateBtn.disabled = false;
        }
    }

    showResult(result) {
        const resultSection = document.getElementById('resultSection');
        const resultVideo = document.getElementById('resultVideo');
        const resultDuration = document.getElementById('resultDuration');
        const resultSize = document.getElementById('resultSize');
        const downloadBtn = document.getElementById('downloadBtn');
        
        // 设置结果信息
        resultVideo.src = result.video_path;
        resultDuration.textContent = result.duration + '秒';
        resultSize.textContent = result.file_size_mb + 'MB';
        downloadBtn.href = result.video_path;
        
        // 显示结果区域
        resultSection.style.display = 'block';
        
        // 滚动到结果区域
        resultSection.scrollIntoView({ behavior: 'smooth' });
    }

    resetEditor() {
        // 重置所有状态
        this.removeVideo();
        this.textSettings = {};
        
        // 清空表单
        document.getElementById('textContent').value = '';
        document.getElementById('fontSize').value = '36';
        document.getElementById('fontColor').value = '#FFFFFF';
        document.getElementById('textPosition').value = 'center';
        document.getElementById('textAlign').value = 'center';
        document.getElementById('backgroundEffect').value = 'solid';
        document.getElementById('animationEffect').value = 'fade_in';
        document.getElementById('displayDuration').value = '5';
        document.getElementById('durationValue').textContent = '5秒';
        document.getElementById('positionX').value = '';
        document.getElementById('positionY').value = '';
        document.getElementById('customPosition').style.display = 'none';
        
        // 隐藏结果区域
        document.getElementById('resultSection').style.display = 'none';
        
        this.showToast('编辑器已重置', 'info');
        console.log('🔄 编辑器已重置');
    }

    showToast(message, type = 'info') {
        // 创建toast通知
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        // 添加样式
        Object.assign(toast.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 24px',
            borderRadius: '8px',
            color: 'white',
            fontWeight: '500',
            zIndex: '10000',
            transform: 'translateX(120%)',
            transition: 'transform 0.3s ease-in-out',
            maxWidth: '400px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
        });

        // 设置背景色
        const colors = {
            success: '#28a745',
            error: '#dc3545',
            info: '#17a2b8',
            warning: '#ffc107'
        };
        toast.style.backgroundColor = colors[type] || colors.info;

        document.body.appendChild(toast);
        
        // 显示动画
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 100);
        
        // 自动隐藏
        setTimeout(() => {
            toast.style.transform = 'translateX(120%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 3000);
        
        console.log(`🔔 Toast [${type}]: ${message}`);
    }
}

// 页面加载完成后初始化编辑器
document.addEventListener('DOMContentLoaded', () => {
    window.videoEditor = new VideoTextEditor();
    console.log('🚀 视频文字编辑器启动完成');
});