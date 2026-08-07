        // ===== 图片查看器 & 去水印功能 =====
        let modalState = {
            currentPath: '',       // 当前图片路径
            cleanedPath: '',       // 去水印后路径
            zoom: 1,
            drawMode: false,
            drawing: false,
            isFullscreen: true,    // 全屏状态
            regions: [],           // 框选的水印区域 [{x, y, width, height}]
            startX: 0,
            startY: 0,
            imgNaturalW: 0,
            imgNaturalH: 0,
            imgDisplayW: 0,
            imgDisplayH: 0,
            imgOffsetX: 0,
            imgOffsetY: 0,
            sourceElement: null,   // 点击来源的img元素
            skipAutoDetect: false, // 去水印后跳过自动检测
            // ---- 边框绘制 ----
            borderMode: false,
            borderDrawing: false,
            borders: [],           // [{x, y, width, height, color, lineWidth}]（图片原始坐标）
            borderColor: '#ff0000',
            borderLineWidth: 3,
            // ---- 裁剪 ----
            cropMode: false,
            cropDrawing: false,
            cropRegion: null,      // {x, y, width, height} 图片原始坐标
            // ---- 文字标注 ----
            textMode: false,
            textOverlays: [],      // [{text, x, y, color, font_key, font_size}]
            textFontsLoaded: false,
        };

        const IMAGE_TEXT_FONT_FAMILY = {
            msyhbd: '"Microsoft YaHei", "PingFang SC", sans-serif',
            msyh: '"Microsoft YaHei", "PingFang SC", sans-serif',
            simhei: 'SimHei, "Microsoft YaHei", sans-serif',
            simsun: 'SimSun, serif',
            kaiti: 'KaiTi, "STKaiti", serif',
        };

        function _setCanvasPointerEvents() {
            const canvas = document.getElementById('modalCanvas');
            if (!canvas) return;
            const active = modalState.drawMode || modalState.borderMode || modalState.cropMode || modalState.textMode;
            canvas.style.pointerEvents = active ? 'auto' : 'none';
            canvas.style.cursor = modalState.textMode ? 'text' : (active ? 'crosshair' : 'default');
        }

        function openImageModal(imgSrc, sourceEl) {
            modalState.currentPath = imgSrc;
            modalState.cleanedPath = '';
            modalState.zoom = 1;
            modalState.drawMode = false;
            modalState.regions = [];
            modalState.sourceElement = sourceEl || null;
            modalState.skipAutoDetect = false;
            // 边框状态重置
            modalState.borderMode = false;
            modalState.borderDrawing = false;
            modalState.borders = [];
            modalState.cropMode = false;
            modalState.cropDrawing = false;
            modalState.cropRegion = null;
            modalState.textMode = false;
            modalState.textOverlays = [];
            if (typeof _exitTextMode === 'function') {
                _exitTextMode(false);
            }
            if (typeof _updateTextUI === 'function') {
                _updateTextUI();
            }

            const overlay = document.getElementById('imageModalOverlay');
            const img = document.getElementById('modalImage');
            
            img.src = imgSrc;
            img.style.transform = 'scale(1)';
            
            overlay.classList.add('active');
            
            // 安全地设置按钮状态（检查元素是否存在）
            const drawModeBtn = document.getElementById('drawModeBtn');
            if (drawModeBtn) {
                drawModeBtn.classList.remove('active');
                drawModeBtn.textContent = '✏️ 框选水印';
            }
            
            const removeWatermarkBtn = document.getElementById('removeWatermarkBtn');
            if (removeWatermarkBtn) {
                removeWatermarkBtn.disabled = true;
            }
            
            const useCleanedBtn = document.getElementById('useCleanedBtn');
            if (useCleanedBtn) {
                useCleanedBtn.style.display = 'none';
            }
            
            const undoRegionBtn = document.getElementById('undoRegionBtn');
            if (undoRegionBtn) {
                undoRegionBtn.style.display = 'none';
            }
            
            const clearRegionsBtn = document.getElementById('clearRegionsBtn');
            if (clearRegionsBtn) {
                clearRegionsBtn.style.display = 'none';
            }
            
            const regionsCount = document.getElementById('regionsCount');
            if (regionsCount) {
                regionsCount.innerHTML = '';
            }
            
            const zoomLevel = document.getElementById('zoomLevel');
            if (zoomLevel) {
                zoomLevel.textContent = '100%';
            }
            
            const modalTitle = document.getElementById('modalTitle');
            if (modalTitle) {
                modalTitle.textContent = '🔍 图片查看器';
            }

            img.onload = function() {
                modalState.imgNaturalW = img.naturalWidth;
                modalState.imgNaturalH = img.naturalHeight;
                document.getElementById('modalImageInfo').textContent = 
                    `${img.naturalWidth} × ${img.naturalHeight} px`;
                updateCanvasSize();
                
                // 检查是否为外部 URL 图片
                const isExternalUrl = imgSrc.startsWith('http');
                const usageTip = isExternalUrl 
                    ? '💡 提示：外部图片可能因跨域限制无法处理，建议下载后本地上传'
                    : '💡 操作说明：用鼠标框选水印区域，然后点击“去除水印”按钮';
                
                document.getElementById('modalTitle').innerHTML = `
                    🔍 图片查看器 
                    <span style="font-size: 12px; color: #888; margin-left: 10px; font-weight: normal;">
                        ${usageTip}
                    </span>
                `;
                
                // 默认进入框选模式
                if (!modalState.drawMode) {
                    toggleDrawMode();
                }
                // 不再自动检测水印，用户可手动点击"自动检测"按钮
                // if (!modalState.skipAutoDetect) {
                //     autoDetectWatermark();
                // }
            };
        }

        function closeImageModal() {
            document.getElementById('imageModalOverlay').classList.remove('active');
            clearCanvas();
            toggleRegionPanel(false);
            modalState.isFullscreen = true;
            updateFullscreenButton();
            // 退出边框模式
            if (modalState.borderMode) _exitBorderMode();
            // 退出裁剪模式
            if (modalState.cropMode) _exitCropMode();
            if (modalState.textMode) _exitTextMode(false);
            // 退出编辑模式
            exitEditMode();
        }
        
        /**
         * 切换编辑模式
         */
        function toggleEditMode() {
            const editTools = document.getElementById('editTools');
            const editModeBtn = document.getElementById('editModeBtn');
            if (!editTools || !editModeBtn) return;
            const isEditing = editTools.style.display === 'flex';
            
            if (!isEditing) {
                // 进入编辑模式
                editTools.style.display = 'flex';
                editModeBtn.textContent = '✅ 编辑中';
                editModeBtn.classList.add('active');
                showToast('💡 提示：可用「剪裁」裁剪、「添加文字」标注，或用「框选水印」去水印', 'info', 5000);
            } else {
                // 退出编辑模式
                editTools.style.display = 'none';
                editModeBtn.textContent = '✏️ 编辑图片';
                editModeBtn.classList.remove('active');
            }
        }
        
        /**
         * 退出编辑模式
         */
        function exitEditMode() {
            const editTools = document.getElementById('editTools');
            const editModeBtn = document.getElementById('editModeBtn');
            const modalTitle = document.getElementById('modalTitle');
            
            if (editTools) {
                editTools.style.display = 'none';
            }
            if (editModeBtn) {
                editModeBtn.textContent = '✏️ 编辑图片';
                editModeBtn.classList.remove('active');
            }
            if (modalTitle) {
                modalTitle.textContent = '🔍 图片查看器';
            }
            
            // 清除编辑状态
            window.currentEditingImagePath = null;
            window.editModified = false;
        }

        function toggleFullscreen() {
            modalState.isFullscreen = !modalState.isFullscreen;
            const modal = document.querySelector('.image-modal');
            const btn = document.getElementById('fullscreenBtn');
            
            if (modalState.isFullscreen) {
                // 切换到全屏
                modal.style.width = '100vw';
                modal.style.height = '100vh';
                modal.style.maxWidth = 'none';
                modal.style.maxHeight = 'none';
                modal.style.borderRadius = '0';
                btn.innerHTML = '🔲 全屏';
                btn.title = '退出全屏';
            } else {
                // 切换到窗口模式
                modal.style.width = '95vw';
                modal.style.height = '90vh';
                modal.style.maxWidth = '1200px';
                modal.style.maxHeight = '800px';
                modal.style.borderRadius = '12px';
                btn.innerHTML = '🔳 窗口';
                btn.title = '全屏显示';
            }
            
            // 重新计算图片显示尺寸
            setTimeout(updateCanvasSize, 100);
        }

        function updateFullscreenButton() {
            const btn = document.getElementById('fullscreenBtn');
            if (btn) {
                if (modalState.isFullscreen) {
                    btn.innerHTML = '🔲 全屏';
                    btn.title = '退出全屏';
                } else {
                    btn.innerHTML = '🔳 窗口';
                    btn.title = '全屏显示';
                }
            }
        }

        function zoomImage(delta) {
            modalState.zoom = Math.max(0.2, Math.min(5, modalState.zoom + delta));
            document.getElementById('modalImage').style.transform = `scale(${modalState.zoom})`;
            document.getElementById('zoomLevel').textContent = `${Math.round(modalState.zoom * 100)}%`;
            updateCanvasSize();
        }

        function resetZoom() {
            modalState.zoom = 1;
            document.getElementById('modalImage').style.transform = 'scale(1)';
            document.getElementById('zoomLevel').textContent = '100%';
            updateCanvasSize();
        }

        function toggleDrawMode() {
            // 互斥：关闭边框模式、裁剪模式、文字模式
            if (modalState.borderMode) toggleBorderMode();
            if (modalState.cropMode) toggleCropMode();
            if (modalState.textMode) toggleTextMode();

            modalState.drawMode = !modalState.drawMode;
            const btn = document.getElementById('drawModeBtn');
            const canvas = document.getElementById('modalCanvas');
            
            if (modalState.drawMode) {
                btn.classList.add('active');
                btn.textContent = '✏️ 框选中...';
                _setCanvasPointerEvents();
                // 重置缩放到100%方便框选
                resetZoom();
            } else {
                btn.classList.remove('active');
                btn.textContent = '✏️ 框选水印';
                _setCanvasPointerEvents();
            }
        }

        function updateCanvasSize() {
            const body = document.getElementById('modalBody');
            const img = document.getElementById('modalImage');
            const canvas = document.getElementById('modalCanvas');
            
            // 获取图片在容器中的实际渲染尺寸和位置
            const bodyRect = body.getBoundingClientRect();
            canvas.width = bodyRect.width;
            canvas.height = bodyRect.height;
            
            // 计算图片在容器中的实际显示尺寸（考虑object-fit: contain）
            const imgRect = img.getBoundingClientRect();
            const bodyR = body.getBoundingClientRect();
            
            modalState.imgDisplayW = imgRect.width;
            modalState.imgDisplayH = imgRect.height;
            modalState.imgOffsetX = imgRect.left - bodyR.left;
            modalState.imgOffsetY = imgRect.top - bodyR.top;
            
            // 重绘已有的框选区域
            redrawRegions();
        }

        function getCanvasCoords(e) {
            const canvas = document.getElementById('modalCanvas');
            const rect = canvas.getBoundingClientRect();
            return {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };
        }

        // 将canvas坐标转换为图片原始像素坐标
        function canvasToImageCoords(cx, cy) {
            const scaleX = modalState.imgNaturalW / modalState.imgDisplayW;
            const scaleY = modalState.imgNaturalH / modalState.imgDisplayH;
            
            const imgX = (cx - modalState.imgOffsetX) * scaleX;
            const imgY = (cy - modalState.imgOffsetY) * scaleY;
            
            return {
                x: Math.max(0, Math.min(modalState.imgNaturalW, imgX)),
                y: Math.max(0, Math.min(modalState.imgNaturalH, imgY))
            };
        }

        function _canvasRectToImageRegion(cx, cy, cw, ch) {
            const topLeft = canvasToImageCoords(cx, cy);
            const bottomRight = canvasToImageCoords(cx + cw, cy + ch);
            return {
                x: Math.round(topLeft.x),
                y: Math.round(topLeft.y),
                width: Math.max(1, Math.round(bottomRight.x - topLeft.x)),
                height: Math.max(1, Math.round(bottomRight.y - topLeft.y)),
            };
        }

        // 将图片原始像素坐标转换为canvas坐标
        function imageToCanvasCoords(ix, iy) {
            const scaleX = modalState.imgDisplayW / modalState.imgNaturalW;
            const scaleY = modalState.imgDisplayH / modalState.imgNaturalH;
            
            return {
                x: ix * scaleX + modalState.imgOffsetX,
                y: iy * scaleY + modalState.imgOffsetY
            };
        }

        function redrawRegions() {
            const canvas = document.getElementById('modalCanvas');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            modalState.regions.forEach((region, idx) => {
                const topLeft = imageToCanvasCoords(region.x, region.y);
                const bottomRight = imageToCanvasCoords(region.x + region.width, region.y + region.height);
                const w = bottomRight.x - topLeft.x;
                const h = bottomRight.y - topLeft.y;
                
                // 半透明红色填充
                ctx.fillStyle = 'rgba(233, 69, 96, 0.25)';
                ctx.fillRect(topLeft.x, topLeft.y, w, h);
                
                // 红色虚线边框
                ctx.strokeStyle = '#e94560';
                ctx.lineWidth = 2;
                ctx.setLineDash([6, 3]);
                ctx.strokeRect(topLeft.x, topLeft.y, w, h);
                ctx.setLineDash([]);
                
                // 区域编号
                ctx.fillStyle = '#e94560';
                ctx.font = 'bold 14px sans-serif';
                ctx.fillText(`${idx + 1}`, topLeft.x + 4, topLeft.y + 16);
            });

            // 同时绘制已保存的边框与裁剪框
            _drawBordersOnCanvas(ctx);
            _drawCropRegionOnCanvas(ctx);
            _drawTextOverlaysOnCanvas(ctx);
        }

        function _canvasFontSize(fontSize) {
            const scale = modalState.imgDisplayW / Math.max(1, modalState.imgNaturalW);
            return Math.max(10, fontSize * scale);
        }

        function _drawTextOverlaysOnCanvas(ctx) {
            modalState.textOverlays.forEach((item) => {
                const pos = imageToCanvasCoords(item.x, item.y);
                const family = IMAGE_TEXT_FONT_FAMILY[item.font_key] || IMAGE_TEXT_FONT_FAMILY.msyhbd;
                const weight = item.font_key === 'msyhbd' ? 'bold ' : '';
                ctx.font = `${weight}${_canvasFontSize(item.font_size)}px ${family}`;
                ctx.fillStyle = item.color || '#ffffff';
                ctx.strokeStyle = 'rgba(0,0,0,0.55)';
                ctx.lineWidth = 2;
                ctx.textBaseline = 'top';
                ctx.strokeText(item.text, pos.x, pos.y);
                ctx.fillText(item.text, pos.x, pos.y);
            });
        }

        function _drawCropRegionOnCanvas(ctx, previewRect) {
            const region = previewRect || modalState.cropRegion;
            if (!region) return;

            const topLeft = imageToCanvasCoords(region.x, region.y);
            const bottomRight = imageToCanvasCoords(region.x + region.width, region.y + region.height);
            const w = bottomRight.x - topLeft.x;
            const h = bottomRight.y - topLeft.y;

            ctx.fillStyle = 'rgba(46, 204, 113, 0.22)';
            ctx.fillRect(topLeft.x, topLeft.y, w, h);
            ctx.strokeStyle = '#2ecc71';
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 3]);
            ctx.strokeRect(topLeft.x, topLeft.y, w, h);
            ctx.setLineDash([]);

            ctx.fillStyle = '#2ecc71';
            ctx.font = 'bold 12px sans-serif';
            ctx.fillText(`${region.width} × ${region.height}`, topLeft.x + 4, topLeft.y + 14);
        }

        /**
         * 将 modalState.borders 绘制到 canvas（复用坐标转换）
         */
        function _drawBordersOnCanvas(ctx, extraBorder) {
            const allBorders = extraBorder
                ? [...modalState.borders, extraBorder]
                : modalState.borders;

            allBorders.forEach((b) => {
                const tl = imageToCanvasCoords(b.x, b.y);
                const br = imageToCanvasCoords(b.x + b.width, b.y + b.height);
                ctx.strokeStyle = b.color || '#ff0000';
                ctx.lineWidth = b.lineWidth || 3;
                ctx.setLineDash([]);
                ctx.strokeRect(tl.x, tl.y, br.x - tl.x, br.y - tl.y);
            });
        }

        function clearCanvas() {
            const canvas = document.getElementById('modalCanvas');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }

        function updateRegionUI() {
            const count = modalState.regions.length;
                    
            // 安全地更新 UI 元素（检查元素是否存在）
            const regionsCount = document.getElementById('regionsCount');
            if (regionsCount) {
                regionsCount.innerHTML = count > 0 
                    ? `<span class="region-badge" style="cursor:pointer;" onclick="toggleRegionPanel()" title="查看区域列表">${count} 个区域 ▸</span>` : '';
            }
                    
            const removeWatermarkBtn = document.getElementById('removeWatermarkBtn');
            if (removeWatermarkBtn) {
                removeWatermarkBtn.disabled = count === 0;
            }
                    
            const undoRegionBtn = document.getElementById('undoRegionBtn');
            if (undoRegionBtn) {
                undoRegionBtn.style.display = count > 0 ? 'inline-block' : 'none';
            }
                    
            const clearRegionsBtn = document.getElementById('clearRegionsBtn');
            if (clearRegionsBtn) {
                clearRegionsBtn.style.display = count > 0 ? 'inline-block' : 'none';
            }
                    
            // 更新区域列表面板内容
            const listBody = document.getElementById('regionListBody');
            const listFooter = document.getElementById('regionListFooter');
            const panel = document.getElementById('regionListPanel');
                    
            if (!listBody || !listFooter || !panel) return;
                    
            if (count === 0) {
                listBody.innerHTML = '<div class="region-list-empty">暂无检测区域<br><small style="color:#555;">使用“自动检测”或“框选水印”添加</small></div>';
                listFooter.style.display = 'none';
                panel.classList.remove('active');
            } else {
                let html = '';
                modalState.regions.forEach((r, idx) => {
                    html += `<div class="region-list-item" data-region-idx="${idx}" 
                                  onmouseenter="highlightRegion(${idx}, true)" 
                                  onmouseleave="highlightRegion(${idx}, false)"
                                  onclick="focusRegion(${idx})">
                        <span class="region-item-num">${idx + 1}</span>
                        <div class="region-item-info">
                            <div class="region-item-size">${r.width} × ${r.height} px</div>
                            <div class="region-item-pos">位置：(${r.x}, ${r.y})</div>
                        </div>
                        <button class="region-item-del" onclick="event.stopPropagation(); removeRegion(${idx})" title="删除此区域">✕</button>
                    </div>`;
                });
                listBody.innerHTML = html;
                listFooter.style.display = 'block';
                // 自动显示面板
                panel.classList.add('active');
            }
        }

        function toggleRegionPanel(forceState) {
            const panel = document.getElementById('regionListPanel');
            if (typeof forceState === 'boolean') {
                panel.classList.toggle('active', forceState);
            } else {
                panel.classList.toggle('active');
            }
        }

        function removeRegion(index) {
            if (index >= 0 && index < modalState.regions.length) {
                modalState.regions.splice(index, 1);
                redrawRegions();
                updateRegionUI();
                showToast(`已删除区域 ${index + 1}`, 'info', 2000);
            }
        }

        function highlightRegion(index, isHighlight) {
            // 高亮列表项
            const items = document.querySelectorAll('.region-list-item');
            items.forEach((item, i) => {
                item.classList.toggle('highlighted', i === index && isHighlight);
            });
            
            // 在canvas上高亮显示对应区域
            redrawRegions();
            if (isHighlight && index >= 0 && index < modalState.regions.length) {
                const region = modalState.regions[index];
                const canvas = document.getElementById('modalCanvas');
                const ctx = canvas.getContext('2d');
                
                const topLeft = imageToCanvasCoords(region.x, region.y);
                const bottomRight = imageToCanvasCoords(region.x + region.width, region.y + region.height);
                const w = bottomRight.x - topLeft.x;
                const h = bottomRight.y - topLeft.y;
                
                // 加粗高亮边框
                ctx.strokeStyle = '#ffcc00';
                ctx.lineWidth = 3;
                ctx.setLineDash([]);
                ctx.strokeRect(topLeft.x - 1, topLeft.y - 1, w + 2, h + 2);
                
                // 黄色半透明覆盖
                ctx.fillStyle = 'rgba(255, 204, 0, 0.15)';
                ctx.fillRect(topLeft.x, topLeft.y, w, h);
            }
        }

        function focusRegion(index) {
            // 点击列表项时闪烁对应区域
            highlightRegion(index, true);
            setTimeout(() => {
                highlightRegion(index, false);
                setTimeout(() => highlightRegion(index, true), 150);
                setTimeout(() => highlightRegion(index, false), 600);
            }, 300);
        }

        function undoLastRegion() {
            modalState.regions.pop();
            redrawRegions();
            updateRegionUI();
        }

        function clearRegions() {
            modalState.regions = [];
            clearCanvas();
            updateRegionUI();
            toggleRegionPanel(false);
        }

        // Canvas事件：画框（水印框选 & 边框绘制 双模式）
        const modalCanvas = document.getElementById('modalCanvas');
        if (modalCanvas) {
        modalCanvas.style.pointerEvents = 'none';

        modalCanvas.addEventListener('mousedown', function(e) {
            const coords = getCanvasCoords(e);
            if (modalState.drawMode) {
                modalState.drawing = true;
                modalState.startX = coords.x;
                modalState.startY = coords.y;
            } else if (modalState.borderMode) {
                modalState.borderDrawing = true;
                modalState.startX = coords.x;
                modalState.startY = coords.y;
            } else if (modalState.cropMode) {
                modalState.cropDrawing = true;
                modalState.startX = coords.x;
                modalState.startY = coords.y;
            } else if (modalState.textMode) {
                _placeTextAtCanvas(coords);
            }
        });

        modalCanvas.addEventListener('mousemove', function(e) {
            const coords = getCanvasCoords(e);

            if (modalState.drawing && modalState.drawMode) {
                // ---- 水印框选预览 ----
                redrawRegions();
                const ctx = modalCanvas.getContext('2d');
                const x = Math.min(modalState.startX, coords.x);
                const y = Math.min(modalState.startY, coords.y);
                const w = Math.abs(coords.x - modalState.startX);
                const h = Math.abs(coords.y - modalState.startY);
                ctx.fillStyle = 'rgba(102, 126, 234, 0.3)';
                ctx.fillRect(x, y, w, h);
                ctx.strokeStyle = '#667eea';
                ctx.lineWidth = 2;
                ctx.setLineDash([4, 4]);
                ctx.strokeRect(x, y, w, h);
                ctx.setLineDash([]);

            } else if (modalState.borderDrawing && modalState.borderMode) {
                // ---- 边框绘制预览 ----
                redrawRegions();
                const ctx = modalCanvas.getContext('2d');
                const x = Math.min(modalState.startX, coords.x);
                const y = Math.min(modalState.startY, coords.y);
                const w = Math.abs(coords.x - modalState.startX);
                const h = Math.abs(coords.y - modalState.startY);
                // 预览实线边框
                ctx.strokeStyle = modalState.borderColor;
                ctx.lineWidth = modalState.borderLineWidth;
                ctx.setLineDash([5, 3]);
                ctx.strokeRect(x, y, w, h);
                ctx.setLineDash([]);

            } else if (modalState.cropDrawing && modalState.cropMode) {
                redrawRegions();
                const ctx = modalCanvas.getContext('2d');
                const x = Math.min(modalState.startX, coords.x);
                const y = Math.min(modalState.startY, coords.y);
                const w = Math.abs(coords.x - modalState.startX);
                const h = Math.abs(coords.y - modalState.startY);
                _drawCropRegionOnCanvas(ctx, _canvasRectToImageRegion(x, y, w, h));
            }
        });

        modalCanvas.addEventListener('mouseup', function(e) {
            const coords = getCanvasCoords(e);

            if (modalState.drawing && modalState.drawMode) {
                // ---- 水印框选确认 ----
                modalState.drawing = false;
                const cx = Math.min(modalState.startX, coords.x);
                const cy = Math.min(modalState.startY, coords.y);
                const cw = Math.abs(coords.x - modalState.startX);
                const ch = Math.abs(coords.y - modalState.startY);
                if (cw < 5 || ch < 5) { redrawRegions(); return; }
                const topLeft = canvasToImageCoords(cx, cy);
                const bottomRight = canvasToImageCoords(cx + cw, cy + ch);
                const region = {
                    x: Math.round(topLeft.x),
                    y: Math.round(topLeft.y),
                    width: Math.round(bottomRight.x - topLeft.x),
                    height: Math.round(bottomRight.y - topLeft.y)
                };
                if (region.width > 0 && region.height > 0) {
                    modalState.regions.push(region);
                }
                redrawRegions();
                updateRegionUI();

            } else if (modalState.borderDrawing && modalState.borderMode) {
                // ---- 边框绘制确认 ----
                modalState.borderDrawing = false;
                const cx = Math.min(modalState.startX, coords.x);
                const cy = Math.min(modalState.startY, coords.y);
                const cw = Math.abs(coords.x - modalState.startX);
                const ch = Math.abs(coords.y - modalState.startY);
                if (cw < 5 || ch < 5) { redrawRegions(); return; }
                const topLeft = canvasToImageCoords(cx, cy);
                const bottomRight = canvasToImageCoords(cx + cw, cy + ch);
                const border = {
                    x: Math.round(topLeft.x),
                    y: Math.round(topLeft.y),
                    width: Math.round(bottomRight.x - topLeft.x),
                    height: Math.round(bottomRight.y - topLeft.y),
                    color: modalState.borderColor,
                    lineWidth: modalState.borderLineWidth,
                };
                if (border.width > 0 && border.height > 0) {
                    modalState.borders.push(border);
                }
                redrawRegions();
                _updateBorderUI();

            } else if (modalState.cropDrawing && modalState.cropMode) {
                modalState.cropDrawing = false;
                const cx = Math.min(modalState.startX, coords.x);
                const cy = Math.min(modalState.startY, coords.y);
                const cw = Math.abs(coords.x - modalState.startX);
                const ch = Math.abs(coords.y - modalState.startY);
                if (cw < 5 || ch < 5) { redrawRegions(); return; }
                modalState.cropRegion = _canvasRectToImageRegion(cx, cy, cw, ch);
                redrawRegions();
                _updateCropUI();
            }
        });
        }

        // 窗口大小变化时重新计算
        window.addEventListener('resize', function() {
            if (document.getElementById('imageModalOverlay').classList.contains('active')) {
                setTimeout(updateCanvasSize, 100);
            }
        });

        async function autoDetectWatermark() {
            const btn = document.getElementById('autoDetectBtn');
            btn.disabled = true;
            btn.textContent = '🔍 检测中...';
            
            try {
                const response = await fetch('/api/detect-watermark', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_path: modalState.currentPath })
                });
                const data = await response.json();
                
                if (data.success && data.regions && data.regions.length > 0) {
                    // 将检测到的区域添加到框选列表
                    data.regions.forEach(r => modalState.regions.push(r));
                    redrawRegions();
                    updateRegionUI();
                    showToast(`检测到 ${data.regions.length} 个可疑水印区域`, 'success');
                } else {
                    showToast('未检测到明显水印，请手动框选', 'info');
                }
            } catch (error) {
                showToast('自动检测失败: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '🔍 自动检测';
            }
        }

        async function autoDetectAndRemove() {
            const btn = document.getElementById('autoRemoveBtn');
            btn.disabled = true;
            btn.textContent = '🚀 检测中...';
            
            try {
                // 第1步：自动检测
                const detectResp = await fetch('/api/detect-watermark', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_path: modalState.currentPath })
                });
                const detectData = await detectResp.json();
                
                if (!detectData.success || !detectData.regions || detectData.regions.length === 0) {
                    showToast('未检测到水印区域，请手动框选后去除', 'info');
                    return;
                }
                
                // 将检测区域显示出来
                modalState.regions = detectData.regions;
                redrawRegions();
                updateRegionUI();
                showToast(`检测到 ${detectData.regions.length} 个水印区域，正在去除...`, 'info');
                
                // 第2步：自动去除
                btn.textContent = '🚀 去除中...';
                
                const removeResp = await fetch('/api/remove-watermark', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        image_path: modalState.currentPath,
                        regions: modalState.regions
                    })
                });
                const removeData = await removeResp.json();
                
                if (removeData.success) {
                    modalState.cleanedPath = removeData.cleaned_path;
                    modalState.skipAutoDetect = true;
                    document.getElementById('modalImage').src = removeData.cleaned_path + '?t=' + Date.now();
                    document.getElementById('modalTitle').textContent = '✅ 去水印完成 - 点击"使用此图"替换原图';
                    document.getElementById('useCleanedBtn').style.display = 'inline-block';
                    
                    modalState.regions = [];
                    clearCanvas();
                    updateRegionUI();
                    
                    showToast(`已自动检测并去除 ${detectData.regions.length} 个水印区域`, 'success');
                } else {
                    showToast('去水印失败: ' + removeData.message, 'error');
                }
            } catch (error) {
                showToast('一键去水印失败: ' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '🚀 一键去水印';
            }
        }

        async function removeWatermark() {
            console.log('\n=== 开始去水印 ===');
            console.log('当前编辑路径:', window.currentEditingImagePath);
            console.log('当前 editModified:', window.editModified);
            
            if (modalState.regions.length === 0) {
                showToast('请先框选水印区域', 'info');
                return;
            }
            
            const btn = document.getElementById('removeWatermarkBtn');
            if (!btn) {
                showToast('去除水印按钮不存在', 'error');
                return;
            }
            
            btn.disabled = true;
            btn.textContent = '🧹 处理中...';
            
            try {
                const response = await fetch('/api/remove-watermark', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        image_path: modalState.currentPath,
                        regions: modalState.regions
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // 显示去水印后的图片
                    modalState.cleanedPath = data.cleaned_path;
                    modalState.skipAutoDetect = true;  // 去水印后的图不再自动检测
                    document.getElementById('modalImage').src = data.cleaned_path + '?t=' + Date.now();
                    
                    // 安全地更新 UI（检查元素是否存在）
                    const modalTitle = document.getElementById('modalTitle');
                    if (modalTitle) {
                        // 如果在编辑模式下，保持编辑器标题
                        if (window.currentEditingImagePath) {
                            modalTitle.textContent = '🛠️ 图片编辑器 - 去水印完成';
                        } else {
                            modalTitle.textContent = '✅ 去水印完成 - 点击"使用此图"替换原图';
                        }
                    }
                    
                    const useCleanedBtn = document.getElementById('useCleanedBtn');
                    if (useCleanedBtn) {
                        // 在编辑模式下不显示"使用此图"按钮，因为有"保存修改"按钮
                        if (!window.currentEditingImagePath) {
                            useCleanedBtn.style.display = 'inline-block';
                        }
                    }
                    
                    // 清除框选
                    modalState.regions = [];
                    clearCanvas();
                    updateRegionUI();
                                        
                    showToast('水印去除成功！', 'success');
                                        
                    console.log('检查编辑模式：', {
                        currentEditingImagePath: window.currentEditingImagePath,
                        hasSaveBtn: !!document.getElementById('saveEditBtn'),
                        editModified: window.editModified
                    });
                                        
                    // 如果是在编辑模式下，标记为已修改并启用保存按钮
                    if (window.currentEditingImagePath) {
                        window.editModified = true;
                        const saveEditBtn = document.getElementById('saveEditBtn');
                        if (saveEditBtn) {
                            saveEditBtn.disabled = false;
                            console.log('✅ 保存修改按钮已启用');
                            showToast('💡 点击“保存修改”应用更改', 'info', 3000);
                        } else {
                            console.warn('⚠️ 保存修改按钮不存在');
                        }
                    } else {
                        console.log('ℹ️ 非编辑模式，显示使用此图按钮');
                        showToast('可点击「使用此图」替换', 'info', 3000);
                    }
                } else {
                    showToast('去水印失败: ' + data.message, 'error');
                }
            } catch (error) {
                showToast('去水印失败：' + error.message, 'error');
            } finally {
                // 安全地恢复按钮状态
                if (btn) {
                    btn.disabled = modalState.regions.length === 0;
                    btn.textContent = '🧹 去除水印';
                }
            }
        }

        function useCleanedImage() {
            if (!modalState.cleanedPath || !modalState.sourceElement) return;
            
            const newPath = modalState.cleanedPath;
            const oldPath = modalState.currentPath;
            
            // 更新原图预览为去水印后的图片
            modalState.sourceElement.src = newPath;
            
            // 如果在编辑模式下，询问是否替换
            if (window.currentEditingImagePath) {
                const confirmReplace = confirm('是否保存编辑后的图片并替换原图？\n\n点击“确定”替换原图，点击“取消”保留两个版本。');
                if (confirmReplace) {
                    replaceEditedImage(oldPath, newPath);
                }
            }
            
            closeImageModal();
            showToast('✅ 已使用去水印后的图片', 'success');
        }
        
        /**
         * 替换编辑后的图片
         */
        async function replaceEditedImage(originalPath, newPath) {
            try {
                console.log('\n=== 替换图片 ===');
                console.log('原路径:', originalPath);
                console.log('新路径:', newPath);
                
                // 去除路径前的 '/' 和时间戳参数
                const cleanOriginal = originalPath.replace(/^\//, '').split('?')[0];
                const cleanNew = newPath.replace(/^\//, '').split('?')[0];
                
                console.log('清理后的原路径:', cleanOriginal);
                console.log('清理后的新路径:', cleanNew);
                
                const response = await fetch('/api/replace-edited-image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        original_path: cleanOriginal,
                        new_path: cleanNew
                    })
                });
                
                const result = await response.json();
                console.log('API 响应:', result);
                
                if (result.success) {
                    const imgDiv = Array.from(document.querySelectorAll('.selectable-image')).find(
                        (el) => el.dataset.path === originalPath
                    );
                    if (imgDiv) {
                        const thumb = imgDiv.querySelector('img');
                        if (thumb) thumb.src = result.final_path + '?t=' + Date.now();
                        imgDiv.dataset.path = result.final_path;
                    }
                    
                    // 如果在 selectedImages 数组中，也更新
                    const idx = selectedImages.findIndex(img => img.path === originalPath);
                    if (idx !== -1) {
                        selectedImages[idx].path = result.final_path;
                    }
                    
                    console.log('✅ 图片已替换:', result.final_path);
                    showToast('✅ 编辑已保存，图片已替换', 'success');
                } else {
                    showToast('❌ 替换图片失败：' + result.message, 'error');
                }
            } catch (error) {
                console.error('替换图片异常:', error);
                showToast('❌ 替换图片失败：' + error.message, 'error');
            }
        }

        // ===== 边框绘制功能 =====

        function toggleBorderMode() {
            // 互斥：关闭水印框选模式、裁剪模式
            if (modalState.drawMode) toggleDrawMode();
            if (modalState.cropMode) toggleCropMode();
            if (modalState.textMode) toggleTextMode();

            modalState.borderMode = !modalState.borderMode;
            const btn = document.getElementById('borderModeBtn');
            const canvas = document.getElementById('modalCanvas');
            const opts = document.getElementById('borderToolOptions');

            if (modalState.borderMode) {
                btn.classList.add('active');
                btn.textContent = '🔲 绘制中...';
                _setCanvasPointerEvents();
                if (opts) opts.style.display = 'flex';
                // 同步 UI 输入框到当前状态
                const cp = document.getElementById('borderColorPicker');
                if (cp) { cp.value = modalState.borderColor; }
                const wi = document.getElementById('borderWidthInput');
                if (wi) { wi.value = modalState.borderLineWidth; }
            } else {
                _exitBorderMode();
            }
        }

        function _exitBorderMode() {
            modalState.borderMode = false;
            modalState.borderDrawing = false;
            const btn = document.getElementById('borderModeBtn');
            const canvas = document.getElementById('modalCanvas');
            const opts = document.getElementById('borderToolOptions');
            if (btn) {
                btn.classList.remove('active');
                btn.textContent = '🔲 绘制边框';
            }
            if (canvas) _setCanvasPointerEvents();
            if (opts) opts.style.display = 'none';
        }

        function _updateBorderUI() {
            const count = modalState.borders.length;
            const undoBtn = document.getElementById('undoBorderBtn');
            const clearBtn = document.getElementById('clearBordersBtn');
            const applyBtn = document.getElementById('applyBordersBtn');
            if (undoBtn) undoBtn.style.display = count > 0 ? 'inline-block' : 'none';
            if (clearBtn) clearBtn.style.display = count > 0 ? 'inline-block' : 'none';
            if (applyBtn) applyBtn.style.display = count > 0 ? 'inline-block' : 'none';
        }

        function undoLastBorder() {
            if (modalState.borders.length === 0) return;
            modalState.borders.pop();
            redrawRegions();
            _updateBorderUI();
            showToast('已撤销上一条边框', 'info', 1500);
        }

        function clearAllBorders() {
            modalState.borders = [];
            redrawRegions();
            _updateBorderUI();
            showToast('已清除全部边框', 'info', 1500);
        }

        // ===== 图片裁剪功能 =====

        function toggleCropMode() {
            if (modalState.currentPath.startsWith('http')) {
                showToast('外部图片无法裁剪，请先下载或本地上传', 'error');
                return;
            }

            if (modalState.drawMode) toggleDrawMode();
            if (modalState.borderMode) toggleBorderMode();
            if (modalState.textMode) toggleTextMode();

            modalState.cropMode = !modalState.cropMode;
            const btn = document.getElementById('cropModeBtn');

            if (modalState.cropMode) {
                if (btn) {
                    btn.classList.add('active');
                    btn.textContent = '✂️ 框选中...';
                }
                _setCanvasPointerEvents();
                resetZoom();
                showToast('拖拽框选要保留的区域，然后点击「应用剪裁」', 'info', 4000);
            } else {
                _exitCropMode();
            }
        }

        function _exitCropMode() {
            modalState.cropMode = false;
            modalState.cropDrawing = false;
            const btn = document.getElementById('cropModeBtn');
            if (btn) {
                btn.classList.remove('active');
                btn.textContent = '✂️ 剪裁';
            }
            _setCanvasPointerEvents();
        }

        // ===== 图片文字标注 =====

        async function loadImageTextFonts() {
            if (modalState.textFontsLoaded) return;
            try {
                const resp = await fetch('/api/list-title-fonts');
                const data = await resp.json();
                const sel = document.getElementById('imageTextFontSelect');
                if (data.success && sel && Array.isArray(data.fonts) && data.fonts.length) {
                    sel.innerHTML = data.fonts.map((f) =>
                        `<option value="${f.key}">${f.label}</option>`
                    ).join('');
                }
                modalState.textFontsLoaded = true;
            } catch (e) {
                console.warn('加载字体列表失败', e);
            }
        }

        function _getTextToolValues() {
            const text = (document.getElementById('imageTextInput')?.value || '').trim();
            const font_key = document.getElementById('imageTextFontSelect')?.value || 'msyhbd';
            const color = document.getElementById('imageTextColorPicker')?.value || '#ffffff';
            const font_size = parseInt(document.getElementById('imageTextSizeInput')?.value, 10) || 48;
            return {
                text,
                font_key,
                color,
                font_size: Math.min(200, Math.max(12, font_size)),
            };
        }

        function toggleTextMode() {
            if (modalState.currentPath.startsWith('http')) {
                showToast('外部图片无法添加文字，请先下载或本地上传', 'error');
                return;
            }

            if (modalState.drawMode) toggleDrawMode();
            if (modalState.borderMode) toggleBorderMode();
            if (modalState.cropMode) toggleCropMode();

            modalState.textMode = !modalState.textMode;
            if (modalState.textMode) {
                loadImageTextFonts();
                const btn = document.getElementById('textModeBtn');
                if (btn) {
                    btn.classList.add('active');
                    btn.textContent = '🅰️ 点击放置';
                }
                const opts = document.getElementById('textToolOptions');
                if (opts) opts.style.display = 'flex';
                _setCanvasPointerEvents();
                resetZoom();
                showToast('输入文字后，在图片上点击要放置的位置', 'info', 4000);
            } else {
                _exitTextMode(true);
            }
        }

        function _exitTextMode(keepOverlays) {
            modalState.textMode = false;
            const btn = document.getElementById('textModeBtn');
            const opts = document.getElementById('textToolOptions');
            if (btn) {
                btn.classList.remove('active');
                btn.textContent = '🅰️ 添加文字';
            }
            if (opts) opts.style.display = 'none';
            if (!keepOverlays) {
                modalState.textOverlays = [];
            }
            _setCanvasPointerEvents();
            _updateTextUI();
            redrawRegions();
        }

        function _placeTextAtCanvas(coords) {
            const values = _getTextToolValues();
            if (!values.text) {
                showToast('请先在输入框中填写文字', 'info');
                return;
            }
            const imgPos = canvasToImageCoords(coords.x, coords.y);
            if (imgPos.x < 0 || imgPos.y < 0 ||
                imgPos.x > modalState.imgNaturalW || imgPos.y > modalState.imgNaturalH) {
                return;
            }
            modalState.textOverlays.push({
                text: values.text,
                x: Math.round(imgPos.x),
                y: Math.round(imgPos.y),
                color: values.color,
                font_key: values.font_key,
                font_size: values.font_size,
            });
            redrawRegions();
            _updateTextUI();
        }

        function _updateTextUI() {
            const count = modalState.textOverlays.length;
            const applyBtn = document.getElementById('applyTextBtn');
            const undoBtn = document.getElementById('undoTextBtn');
            if (applyBtn) applyBtn.style.display = count > 0 ? 'inline-block' : 'none';
            if (undoBtn) undoBtn.style.display = count > 0 ? 'inline-block' : 'none';
        }

        function undoLastImageText() {
            if (!modalState.textOverlays.length) return;
            modalState.textOverlays.pop();
            redrawRegions();
            _updateTextUI();
            showToast('已撤销上一条文字', 'info', 1500);
        }

        async function applyImageTexts() {
            if (!modalState.textOverlays.length) {
                showToast('请先点击图片放置文字', 'info');
                return;
            }
            if (modalState.currentPath.startsWith('http')) {
                showToast('外部图片无法添加文字，请先下载或本地上传', 'error');
                return;
            }

            const btn = document.getElementById('applyTextBtn');
            if (btn) {
                btn.disabled = true;
                btn.textContent = '⏳ 应用中...';
            }

            try {
                const resp = await fetch('/api/draw-image-text', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        image_path: modalState.currentPath,
                        texts: modalState.textOverlays.map((t) => ({
                            text: t.text,
                            x: t.x,
                            y: t.y,
                            color: t.color,
                            font_key: t.font_key,
                            font_size: t.font_size,
                        })),
                    }),
                });
                const data = await resp.json();

                if (data.success) {
                    modalState.currentPath = data.result_path;
                    modalState.cleanedPath = data.result_path;
                    modalState.textOverlays = [];
                    _exitTextMode(true);
                    _updateTextUI();

                    const img = document.getElementById('modalImage');
                    img.onload = function() {
                        modalState.imgNaturalW = img.naturalWidth;
                        modalState.imgNaturalH = img.naturalHeight;
                        document.getElementById('modalImageInfo').textContent =
                            `${img.naturalWidth} × ${img.naturalHeight} px`;
                        updateCanvasSize();
                    };
                    img.src = data.result_path + '?t=' + Date.now();
                    redrawRegions();

                    window.editModified = true;
                    const saveBtn = document.getElementById('saveEditBtn');
                    if (saveBtn) saveBtn.disabled = false;

                    showToast('✅ 文字已添加到图片', 'success');
                } else {
                    showToast('添加文字失败: ' + (data.message || '未知错误'), 'error');
                }
            } catch (err) {
                showToast('添加文字异常: ' + err.message, 'error');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '✅ 应用文字';
                }
            }
        }

        function _updateCropUI() {
            const hasCrop = !!modalState.cropRegion;
            const applyBtn = document.getElementById('applyCropBtn');
            if (applyBtn) applyBtn.style.display = hasCrop ? 'inline-block' : 'none';
        }

        async function applyCrop() {
            if (!modalState.cropRegion) {
                showToast('请先框选裁剪区域', 'info');
                return;
            }
            if (modalState.currentPath.startsWith('http')) {
                showToast('外部图片无法裁剪，请先下载或本地上传', 'error');
                return;
            }

            const btn = document.getElementById('applyCropBtn');
            if (btn) {
                btn.disabled = true;
                btn.textContent = '⏳ 剪裁中...';
            }

            try {
                const region = modalState.cropRegion;
                const resp = await fetch('/api/crop-image', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        image_path: modalState.currentPath,
                        x: region.x,
                        y: region.y,
                        width: region.width,
                        height: region.height,
                    }),
                });
                const data = await resp.json();

                if (data.success) {
                    modalState.currentPath = data.result_path;
                    modalState.cleanedPath = data.result_path;
                    modalState.cropRegion = null;
                    _exitCropMode();
                    _updateCropUI();

                    const img = document.getElementById('modalImage');
                    img.onload = function() {
                        modalState.imgNaturalW = img.naturalWidth;
                        modalState.imgNaturalH = img.naturalHeight;
                        document.getElementById('modalImageInfo').textContent =
                            `${img.naturalWidth} × ${img.naturalHeight} px`;
                        updateCanvasSize();
                    };
                    img.src = data.result_path + '?t=' + Date.now();
                    redrawRegions();

                    window.editModified = true;
                    const saveBtn = document.getElementById('saveEditBtn');
                    if (saveBtn) saveBtn.disabled = false;

                    showToast(`✅ 剪裁完成：${data.width} × ${data.height} px`, 'success');
                } else {
                    showToast('剪裁失败: ' + (data.message || '未知错误'), 'error');
                }
            } catch (err) {
                showToast('剪裁异常: ' + err.message, 'error');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '✅ 应用剪裁';
                }
            }
        }

        async function applyBorders() {
            if (modalState.borders.length === 0) {
                showToast('请先在图片上拖拽绘制边框', 'info');
                return;
            }
            const btn = document.getElementById('applyBordersBtn');
            if (btn) { btn.disabled = true; btn.textContent = '⏳ 应用中...'; }

            try {
                const payload = {
                    image_path: modalState.currentPath,
                    borders: modalState.borders.map(b => ({
                        x: b.x, y: b.y,
                        width: b.width, height: b.height,
                        color: b.color,
                        line_width: b.lineWidth,
                    }))
                };
                const resp = await fetch('/api/draw-borders', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await resp.json();

                if (data.success) {
                    // 更新当前展示图片
                    modalState.currentPath = data.result_path;
                    modalState.cleanedPath = data.result_path;
                    document.getElementById('modalImage').src = data.result_path + '?t=' + Date.now();
                    // 清除 canvas 上的边框预览（已烧录到图片）
                    modalState.borders = [];
                    redrawRegions();
                    _updateBorderUI();
                    // 标记编辑状态，启用保存按鈕
                    window.editModified = true;
                    const saveBtn = document.getElementById('saveEditBtn');
                    if (saveBtn) saveBtn.disabled = false;
                    showToast(`✅ 边框已烧录！${data.message}`, 'success');
                } else {
                    showToast('应用边框失败: ' + data.message, 'error');
                }
            } catch (err) {
                showToast('应用边框异常: ' + err.message, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = '✅ 应用边框'; }
            }
        }
        
        /**
         * 保存图片编辑
         */
        async function saveImageEdit() {
            if (!window.editModified) {
                closeImageModal();
                return;
            }
            
            const btn = document.getElementById('saveEditBtn');
            btn.disabled = true;
            btn.textContent = '⏳ 保存中...';
            
            try {
                console.log('\n=== 保存编辑 ===');
                console.log('编辑路径:', window.currentEditingImagePath);
                console.log('当前显示路径:', modalState.currentPath);
                console.log('去水印后路径:', modalState.cleanedPath);
                
                // 获取当前显示的图像路径（从 img 元素的 src）
                const modalImage = document.getElementById('modalImage');
                let currentImagePath = modalImage.src;
                
                console.log('modalImage.src:', currentImagePath);
                
                // 去除域名部分（如果是完整 URL）
                if (currentImagePath.startsWith('http')) {
                    try {
                        const url = new URL(currentImagePath);
                        currentImagePath = url.pathname;  // 只保留路径部分
                    } catch (e) {
                        console.warn('URL 解析失败，使用原路径');
                    }
                }
                
                // 去除时间戳参数和前导 '/'
                currentImagePath = currentImagePath.split('?')[0].replace(/^\//, '');
                
                console.log('清理后的当前路径:', currentImagePath);
                
                // 如果是去水印后的图片，需要替换原图
                if (currentImagePath !== window.currentEditingImagePath.replace(/^\//, '') && modalState.cleanedPath) {
                    console.log('检测到图片已修改，准备替换...');
                    const confirmReplace = confirm('是否保存编辑后的图片并替换原图？\n\n点击“确定”替换原图，点击“取消”保留两个版本。');
                    
                    if (confirmReplace) {
                        await replaceEditedImage(window.currentEditingImagePath, currentImagePath);
                    }
                }
                
                // 关闭编辑器
                closeImageModal();
                
                showToast('✅ 编辑已保存', 'success');
                
            } catch (error) {
                console.error('保存编辑异常:', error);
                showToast('❌ 保存失败：' + error.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = '💾 保存修改';
            }
        }

        function _handleImageModalClick(event) {
            const overlay = document.getElementById('imageModalOverlay');
            if (!overlay) return;

            if (event.target === overlay) {
                closeImageModal();
                return;
            }

            const btn = event.target.closest('button');
            if (!btn || !overlay.contains(btn)) return;

            switch (btn.id) {
                case 'zoomOutBtn':
                    zoomImage(-0.2);
                    break;
                case 'zoomInBtn':
                    zoomImage(0.2);
                    break;
                case 'resetZoomBtn':
                    resetZoom();
                    break;
                case 'fullscreenBtn':
                    toggleFullscreen();
                    break;
                case 'editModeBtn':
                    toggleEditMode();
                    break;
                case 'drawModeBtn':
                    toggleDrawMode();
                    break;
                case 'cropModeBtn':
                    toggleCropMode();
                    break;
                case 'applyCropBtn':
                    applyCrop();
                    break;
                case 'removeWatermarkBtn':
                    if (!btn.disabled) removeWatermark();
                    break;
                case 'textModeBtn':
                    toggleTextMode();
                    break;
                case 'applyTextBtn':
                    applyImageTexts();
                    break;
                case 'undoTextBtn':
                    undoLastImageText();
                    break;
                case 'rotateImageBtn':
                    rotateImage(90);
                    break;
                case 'flipImageBtn':
                    flipImage('horizontal');
                    break;
                case 'saveEditBtn':
                    if (!btn.disabled) saveImageEdit();
                    break;
                case 'closeImageModalBtn':
                    closeImageModal();
                    break;
                case 'closeRegionPanelBtn':
                    toggleRegionPanel(false);
                    break;
                case 'clearRegionsBtn':
                    clearRegions();
                    break;
                default:
                    break;
            }
        }

        function _initImageModalInteractions() {
            const overlay = document.getElementById('imageModalOverlay');
            if (!overlay || overlay.dataset.modalBound === '1') return;
            overlay.dataset.modalBound = '1';
            overlay.addEventListener('click', _handleImageModalClick);
            _exportImageModalApi();
        }

        function rotateImage(degrees) {
            showToast(`旋转 ${degrees}° 功能即将上线`, 'info');
        }

        function flipImage(direction) {
            showToast(`翻转（${direction}）功能即将上线`, 'info');
        }

        function _exportImageModalApi() {
            const api = {
                openImageModal,
                closeImageModal,
                zoomImage,
                resetZoom,
                toggleFullscreen,
                toggleEditMode,
                exitEditMode,
                toggleDrawMode,
                toggleCropMode,
                applyCrop,
                removeWatermark,
                toggleTextMode,
                applyImageTexts,
                undoLastImageText,
                saveImageEdit,
                toggleRegionPanel,
                clearRegions,
                removeRegion,
                rotateImage,
                flipImage,
            };
            Object.assign(window, api);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', _initImageModalInteractions);
        } else {
            _initImageModalInteractions();
        }
                
