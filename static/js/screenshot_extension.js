/**
 * 图片查看器截图功能扩展
 * 添加到 index.html 的 script 标签之前
 */

// 扩展 modalState 对象
if (typeof modalState !== 'undefined') {
    modalState.screenshotMode = false;
    modalState.screenshotStart = null;
    modalState.screenshotEnd = null;
}

/**
 * 启用/禁用截图模式
 */
function enableScreenshotMode() {
    modalState.screenshotMode = !modalState.screenshotMode;
    const btn = document.getElementById('screenshotBtn');
    const canvas = document.getElementById('modalCanvas');
    
    if (modalState.screenshotMode) {
        // 进入截图模式
        if (btn) {
            btn.classList.add('active');
            btn.textContent = '✂️ 截图中...';
        }
        if (canvas) {
            canvas.style.pointerEvents = 'auto';
            canvas.style.cursor = 'crosshair';
        }
        resetZoom();
        
        // 临时退出框选模式
        if(modalState.drawMode) {
            toggleDrawMode();
        }
    } else {
        // 退出截图模式
        if (btn) {
            btn.classList.remove('active');
            btn.textContent = '✂️ 截图';
        }
        if (canvas) {
            canvas.style.pointerEvents = 'none';
            canvas.style.cursor = 'default';
        }
        clearCanvas();
    }
}

/**
 * 获取 canvas 坐标
 */
function getCanvasCoords(e) {
    const canvas = document.getElementById('modalCanvas');
    const rect = canvas.getBoundingClientRect();
    return {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
    };
}

/**
 * 执行截图并下载
 */
function takeScreenshot() {
    if (!modalState.screenshotStart || !modalState.screenshotEnd) return;
    
    const img = document.getElementById('modalImage');
    const startX = modalState.screenshotStart;
    const endX = modalState.screenshotEnd;
    
    // 计算截图区域（转换为原图坐标）
    const x1 = Math.min(startX.x, endX.x);
    const y1 = Math.min(startX.y, endX.y);
    const x2 = Math.max(startX.x, endX.x);
    const y2 = Math.max(startX.y, endX.y);
    
    // 转换为原图像素坐标
    const imgCoords1 = canvasToImageCoords(x1, y1);
    const imgCoords2 = canvasToImageCoords(x2, y2);
    
    const sx = Math.max(0, imgCoords1.x);
    const sy = Math.max(0, imgCoords1.y);
    const sw = Math.abs(imgCoords2.x - imgCoords1.x);
    const sh = Math.abs(imgCoords2.y - imgCoords1.y);
    
    // 创建临时 canvas 进行截图
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = sw;
    tempCanvas.height = sh;
    const ctx = tempCanvas.getContext('2d');
    
    // 绘制截取的区域
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
    
    // 下载截图
    tempCanvas.toBlob(function(blob) {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const timestamp = new Date().getTime();
        link.download = `screenshot_${timestamp}.png`;
        link.href = url;
        link.click();
        URL.revokeObjectURL(url);
        
        // 退出截图模式
        enableScreenshotMode();
        
        if (typeof showToast !== 'undefined') {
            showToast('✅ 截图已保存', 'success');
        } else {
           alert('截图已保存！');
        }
    }, 'image/png');
}

console.log('📸 截图功能已加载');

// 添加 canvas 事件监听器（在 DOM 加载后）
document.addEventListener('DOMContentLoaded', function() {
    const canvas = document.getElementById('modalCanvas');
    if (!canvas) return;
    
    // 鼠标按下 - 开始框选
    canvas.addEventListener('mousedown', function(e) {
        if (!modalState.screenshotMode) return;
        e.preventDefault();
        const coords = getCanvasCoords(e);
        modalState.screenshotStart = coords;
        modalState.screenshotEnd = coords;
    });
    
    // 鼠标移动 - 绘制框选区域
    canvas.addEventListener('mousemove', function(e) {
        if (!modalState.screenshotMode || !modalState.screenshotStart) return;
        e.preventDefault();
        const coords = getCanvasCoords(e);
        modalState.screenshotEnd = coords;
        
        // 重绘已有区域 + 当前正在画的框
        clearCanvas();
        redrawScreenshotBox();
    });
    
    // 鼠标释放 - 完成截图
    canvas.addEventListener('mouseup', function(e) {
        if (!modalState.screenshotMode || !modalState.screenshotStart) return;
        e.preventDefault();
        
        const coords = getCanvasCoords(e);
        modalState.screenshotEnd = coords;
        
        // 检查是否有效框选（忽略太小的点击）
        const x1 = Math.min(modalState.screenshotStart.x, modalState.screenshotEnd.x);
        const y1 = Math.min(modalState.screenshotStart.y, modalState.screenshotEnd.y);
        const x2 = Math.max(modalState.screenshotStart.x, modalState.screenshotEnd.x);
        const y2 = Math.max(modalState.screenshotStart.y, modalState.screenshotEnd.y);
        const w = x2 - x1;
        const h = y2 - y1;
        
        if (w < 5 || h < 5) {
            clearCanvas();
            return;
        }
        
        // 执行截图
        takeScreenshot();
    });
});

/**
 * 重绘截图框
 */
function redrawScreenshotBox() {
    if (!modalState.screenshotStart || !modalState.screenshotEnd) return;
    
    const canvas = document.getElementById('modalCanvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const x1 = Math.min(modalState.screenshotStart.x, modalState.screenshotEnd.x);
    const y1 = Math.min(modalState.screenshotStart.y, modalState.screenshotEnd.y);
    const x2 = Math.max(modalState.screenshotStart.x, modalState.screenshotEnd.x);
    const y2 = Math.max(modalState.screenshotStart.y, modalState.screenshotEnd.y);
    const w = x2 - x1;
    const h = y2 - y1;
    
    // 绘制半透明填充
    ctx.fillStyle = 'rgba(102, 126, 234, 0.3)';
    ctx.fillRect(x1, y1, w, h);
    
    // 绘制边框
    ctx.strokeStyle = '#667eea';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(x1, y1, w, h);
    ctx.setLineDash([]);
}