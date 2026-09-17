(function () {
    const API_BASE = '/api/publishing';

    let currentPage = 1;
    let currentTotal = 0;

    function esc(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatDate(value) {
        if (!value) return '—';
        const parsed = parseServerDateTime(value);
        return parsed ? formatBeijingDateTime(parsed) : '—';
    }

    function platformName(platform) {
        const map = {
            douyin: '抖音',
            kuaishou: '快手',
            wechat_channels: '视频号',
        };
        return map[platform] || platform;
    }

    function actionClass(action) {
        if (action === 'publish') return 'status-pending';
        if (action === 'defer') return 'status-uploading';
        return 'status-scheduled';
    }

    function statusClass(status) {
        if (status === 'pending') return 'status-pending';
        if (status === 'deferred') return 'status-uploading';
        if (status === 'skipped') return 'status-error';
        if (status === 'dispatched') return 'status-published';
        return '';
    }

    function showToast(message, isError) {
        const toast = document.getElementById('candidateToast');
        toast.textContent = message;
        toast.classList.toggle('error', isError);
        toast.hidden = false;
        setTimeout(() => {
            toast.hidden = true;
        }, 3000);
    }

    async function doAction(candidateId, action) {
        const url = `${API_BASE}/candidates/${candidateId}/${action}`;
        const res = await fetch(url, { method: 'POST' });
        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.detail || `${action} failed`);
        }
        return data;
    }

    const REASON_LABELS = {
        'recommend.publish.wechat_dual_grade': '视频号行业与传播评分均达标，建议发布',
        'recommend.defer.wechat_grade_threshold': '视频号评分未达阈值，建议暂缓',
        'recommend.publish.douyin_grade_threshold': '抖音评分达标，建议发布',
        'recommend.defer.douyin_low_viral': '抖音传播潜力不足，建议暂缓',
        'recommend.defer.douyin_industry_threshold': '抖音行业质量未达标，建议暂缓',
        'recommend.publish.kuaishou_industry_motive': '快手行业与动机信号达标，建议发布',
        'recommend.defer.kuaishou_continue': '快手继续观察，建议暂缓',
        'priority.platform_fit': '内容与平台调性匹配（优先级加分）',
        'policy.disabled.global': '发布策略总开关未启用',
        'policy.disabled.platform': '该平台在策略中未启用',
        'policy.shadow_mode': '影子模式：仅评估，不自动派发',
    };

    function formatReasonLabel(reason) {
        const code = String(reason ?? '').trim();
        if (!code) return '—';
        if (REASON_LABELS[code]) return REASON_LABELS[code];
        if (code.startsWith('priority.recent_story_penalty:')) {
            const count = code.split(':')[1] || '0';
            return `同题近期已有 ${count} 篇（优先级降权）`;
        }
        if (code.startsWith('platform.unknown:')) {
            return `未知平台：${code.split(':').slice(1).join(':')}`;
        }
        if (code.startsWith('dispatch.failed:')) {
            const detail = code.slice('dispatch.failed:'.length);
            const detailMap = {
                article_missing: '文章数据缺失',
                account_unavailable: '无可用发布账号',
                no_slot: '今日发布额度已满',
            };
            return `入队失败：${detailMap[detail] || detail}`;
        }
        if (code.startsWith('reconcile.')) {
            const state = code.slice('reconcile.'.length);
            const stateMap = {
                published: '关联任务已发布',
                pending: '关联任务排队中',
                uploading: '关联任务上传中',
                failed: '关联任务失败',
                cancelled: '关联任务已取消',
            };
            return `状态同步：${stateMap[state] || state}`;
        }
        return code;
    }

    function renderReasons(reasons) {
        if (!reasons || !reasons.length) return '—';
        return reasons.map((r) => formatReasonLabel(r)).join(' · ');
    }

    function canOperate(row) {
        return row.status === 'pending' || row.status === 'deferred';
    }

    function renderRow(row) {
        const tr = document.createElement('tr');
        const actions = canOperate(row)
            ? `<button type="button" class="btn btn-small action-enqueue" data-action="enqueue" data-id="${esc(row.id)}">立即入队</button>
                <button type="button" class="btn btn-small action-skip" data-action="skip" data-id="${esc(row.id)}">跳过</button>`
            : '<span class="text-muted">—</span>';
        tr.innerHTML = `
            <td title="${esc(row.title)}">${esc(row.title)}</td>
            <td><span class="platform-chip">${esc(platformName(row.platform))}</span></td>
            <td><span class="${actionClass(row.recommended_action)}">${esc(row.recommended_action)}</span></td>
            <td><span class="${statusClass(row.status)}">${esc(row.status)}</span></td>
            <td>${Number(row.priority || 0).toFixed(2)}</td>
            <td class="reasons" title="${esc(renderReasons(row.reasons))}">${esc(renderReasons(row.reasons))}</td>
            <td>${formatDate(row.evaluated_at)}</td>
            <td class="actions">${actions}</td>
        `;
        return tr;
    }

    async function loadCandidates() {
        const tbody = document.getElementById('candidateTableBody');
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">加载中…</td></tr>';

        const platform = document.getElementById('filterPlatform').value;
        const status = document.getElementById('filterStatus').value;
        const recommended = document.getElementById('filterRecommended').value;
        const sortBy = document.getElementById('filterSort').value;

        const params = new URLSearchParams();
        params.set('page', currentPage);
        params.set('per_page', 20);
        if (platform) params.set('platform', platform);
        if (status) params.set('status', status);
        if (recommended) params.set('recommended_action', recommended);
        if (sortBy) params.set('sort_by', sortBy);

        try {
            const res = await fetch(`${API_BASE}/candidates?${params.toString()}`);
            const data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.detail || '加载失败');
            }
            currentTotal = data.total;
            document.getElementById('candidateCount').textContent = `共 ${data.total} 条`;

            if (!data.items || data.items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">暂无候选</td></tr>';
            } else {
                tbody.innerHTML = '';
                data.items.forEach((row) => {
                    const tr = renderRow(row);
                    tbody.appendChild(tr);
                });
            }
            renderPager(data.page, data.per_page, data.total);
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">加载失败：${esc(err.message)}</td></tr>`;
        }
    }

    function renderPager(page, perPage, total) {
        const totalPages = Math.max(1, Math.ceil(total / perPage));
        const pager = document.getElementById('candidatePager');
        pager.innerHTML = '';

        const prev = document.createElement('button');
        prev.textContent = '上一页';
        prev.disabled = page <= 1;
        prev.addEventListener('click', () => {
            if (currentPage > 1) {
                currentPage -= 1;
                loadCandidates();
            }
        });

        const next = document.createElement('button');
        next.textContent = '下一页';
        next.disabled = page >= totalPages;
        next.addEventListener('click', () => {
            if (currentPage < totalPages) {
                currentPage += 1;
                loadCandidates();
            }
        });

        const info = document.createElement('span');
        info.className = 'page-info';
        info.textContent = `第 ${page} / ${totalPages} 页`;

        pager.appendChild(prev);
        pager.appendChild(info);
        pager.appendChild(next);
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('refreshCandidatesBtn').addEventListener('click', () => {
            currentPage = 1;
            loadCandidates();
        });

        ['filterPlatform', 'filterStatus', 'filterRecommended', 'filterSort'].forEach((id) => {
            document.getElementById(id).addEventListener('change', () => {
                currentPage = 1;
                loadCandidates();
            });
        });

        document.getElementById('candidateTableBody').addEventListener('click', async (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;
            const id = btn.dataset.id;
            const action = btn.dataset.action;
            if (!id || !action) return;
            try {
                await doAction(id, action);
                showToast(action === 'skip' ? '已跳过' : '已入队');
                loadCandidates();
            } catch (err) {
                showToast(err.message, true);
            }
        });

        loadCandidates();
    });
})();
