(function () {
    const ACTIVE_STATUSES = new Set(['pending', 'uploading']);
    const STATUS_LABEL = {
        pending: '等待中',
        uploading: '上传中',
    };

    let scheduleJobId = null;
    let scheduleIsArticleGroup = false;
    let refreshTimer = null;

    function esc(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/"/g, '&quot;');
    }

    function parseJobTime(value) {
        if (!value) return null;
        const parsed = parseServerDateTime(value);
        return parsed ? parsed.getTime() : null;
    }

    function statusLabel(status) {
        return STATUS_LABEL[status] || status;
    }

    function statusClass(status) {
        return status === 'uploading' ? 'status-uploading' : 'status-pending';
    }

    function formatSchedule(job) {
        if (job.status !== 'pending') return '—';
        return job.scheduled_at ? formatBeijingDateTime(job.scheduled_at) : '尽快';
    }

    function groupQueueJobs(jobs) {
        const active = jobs.filter((job) => ACTIVE_STATUSES.has(job.status));
        const singles = [];
        const articleGroups = new Map();

        active.forEach((job) => {
            if (job.source_type === 'ingestion' && job.source_id) {
                const key = job.source_id;
                if (!articleGroups.has(key)) {
                    articleGroups.set(key, {
                        type: 'article',
                        sourceId: key,
                        title: job.title,
                        scheduledAt: job.scheduled_at,
                        createdAt: job.created_at,
                        representativeJobId: job.id,
                        jobs: [],
                    });
                }
                const group = articleGroups.get(key);
                group.jobs.push(job);
                if (parseJobTime(job.scheduled_at) !== null) {
                    const current = parseJobTime(group.scheduledAt);
                    const next = parseJobTime(job.scheduled_at);
                    if (current === null || next < current) {
                        group.scheduledAt = job.scheduled_at;
                    }
                }
                if (parseJobTime(job.created_at) !== null) {
                    const current = parseJobTime(group.createdAt);
                    const next = parseJobTime(job.created_at);
                    if (current === null || next < current) {
                        group.createdAt = job.created_at;
                    }
                }
                if (job.status === 'pending') {
                    group.representativeJobId = job.id;
                }
            } else {
                singles.push({ type: 'single', job });
            }
        });

        const rows = [...singles, ...articleGroups.values()];
        rows.sort((a, b) => {
            const slotA = a.type === 'single' ? a.job.scheduled_at : a.scheduledAt;
            const slotB = b.type === 'single' ? b.job.scheduled_at : b.scheduledAt;
            const timeA = parseJobTime(slotA);
            const timeB = parseJobTime(slotB);
            if (timeA !== null && timeB !== null && timeA !== timeB) return timeA - timeB;
            if (timeA !== null && timeB === null) return -1;
            if (timeA === null && timeB !== null) return 1;
            const createdA = parseJobTime(a.type === 'single' ? a.job.created_at : a.createdAt) || 0;
            const createdB = parseJobTime(b.type === 'single' ? b.job.created_at : b.createdAt) || 0;
            return createdA - createdB;
        });
        return rows;
    }

    function renderPlatformChips(jobs) {
        return jobs.map((job) => {
            const platform = esc(job.platform_display_name || job.platform || '—');
            const account = job.account_nickname ? ` · ${esc(job.account_nickname)}` : '';
            return `<span class="platform-chip">${platform}${account}<span class="chip-status">${esc(statusLabel(job.status))}</span></span>`;
        }).join('');
    }

    function renderRowActions(jobId, canReschedule, canCancel, options = {}) {
        const { scheduledAt = '', title = '', isArticleGroup = false } = options;
        const parts = [];
        if (canReschedule) {
            parts.push(
                `<button type="button" class="btn btn-soft btn-sm" data-action="reschedule"`
                + ` data-job-id="${esc(jobId)}" data-title="${esc(title)}"`
                + ` data-scheduled-at="${esc(scheduledAt || '')}"`
                + ` data-article-group="${isArticleGroup ? '1' : '0'}">改期</button>`
            );
        }
        if (canCancel) {
            parts.push(`<button type="button" class="btn btn-soft btn-sm" data-action="cancel" data-job-id="${esc(jobId)}">取消</button>`);
        }
        return parts.length ? `<div class="queue-actions">${parts.join('')}</div>` : '—';
    }

    function renderQueueRows(rows) {
        if (!rows.length) {
            return '<tr><td colspan="6" class="empty-cell">当前没有待发布任务</td></tr>';
        }

        return rows.map((row) => {
            if (row.type === 'single') {
                const job = row.job;
                const platform = esc(job.platform_display_name || job.platform || '—');
                const account = job.account_nickname
                    ? `<div class="small text-muted">${esc(job.account_nickname)}</div>`
                    : '';
                return `
                <tr>
                    <td>${esc(job.title)}</td>
                    <td>${platform}${account}</td>
                    <td><span class="${statusClass(job.status)}">${esc(statusLabel(job.status))}</span></td>
                    <td>${esc(formatSchedule(job))}</td>
                    <td>${job.created_at ? esc(formatBeijingDateTime(job.created_at)) : '—'}</td>
                    <td>${renderRowActions(
                        job.id,
                        job.status === 'pending',
                        ACTIVE_STATUSES.has(job.status),
                        { scheduledAt: job.scheduled_at || '', title: job.title || '', isArticleGroup: false },
                    )}</td>
                </tr>`;
            }

            const hasPending = row.jobs.some((job) => job.status === 'pending');
            const groupStatus = row.jobs.some((job) => job.status === 'uploading') ? 'uploading' : 'pending';
            const scheduleText = hasPending
                ? (row.scheduledAt ? formatBeijingDateTime(row.scheduledAt) : '尽快')
                : '—';
            return `
            <tr data-article-group="${esc(row.sourceId)}" data-job-ids="${esc(row.jobs.map((job) => job.id).join(','))}">
                <td>
                    ${esc(row.title)}
                    <div class="article-tag">自动发布 · 本篇 ${row.jobs.length} 个平台</div>
                </td>
                <td><div class="platform-chips">${renderPlatformChips(row.jobs)}</div></td>
                <td><span class="${statusClass(groupStatus)}">${esc(statusLabel(groupStatus))}</span></td>
                <td>${esc(scheduleText)}</td>
                <td>${row.createdAt ? esc(formatBeijingDateTime(row.createdAt)) : '—'}</td>
                <td>${renderRowActions(
                    row.representativeJobId,
                    hasPending,
                    row.jobs.some((job) => ACTIVE_STATUSES.has(job.status)),
                    { scheduledAt: row.scheduledAt || '', title: row.title || '', isArticleGroup: true },
                )}</td>
            </tr>`;
        }).join('');
    }

    function updateSummary(jobs) {
        const pending = jobs.filter((job) => job.status === 'pending').length;
        const uploading = jobs.filter((job) => job.status === 'uploading').length;
        document.getElementById('pendingCount').textContent = String(pending);
        document.getElementById('uploadingCount').textContent = String(uploading);

        const nextJob = jobs
            .filter((job) => job.status === 'pending' && job.scheduled_at)
            .slice()
            .sort((a, b) => (parseJobTime(a.scheduled_at) || 0) - (parseJobTime(b.scheduled_at) || 0))[0];

        document.getElementById('nextPublishText').textContent = nextJob
            ? `${formatBeijingDateTime(nextJob.scheduled_at)}（${nextJob.title}）`
            : (pending ? '有任务等待发布，但未设置定时' : '—');

        document.getElementById('queueHint').textContent = jobs.length
            ? `共 ${jobs.length} 条活跃任务`
            : '';
    }

    async function checkHealth() {
        const banner = document.getElementById('workerBanner');
        if (!banner) return;
        try {
            const resp = await fetch('/api/publishing/health');
            const data = await resp.json();
            banner.hidden = !!data.worker_reachable;
        } catch (_err) {
            banner.hidden = false;
        }
    }

    function commentStatusLabel(status) {
        const map = {
            failed: '失败',
            pending: '待发',
            posted: '已发',
            skipped: '已跳过',
            unsupported: '不支持',
            none: '—',
        };
        return map[status] || status || '—';
    }

    async function retryComment(jobId) {
        const resp = await fetch(`/api/publishing/jobs/${jobId}/retry-comment`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) {
            throw new Error(data.detail || data.error || '重试失败');
        }
        if (!data.success) {
            throw new Error(data.error || '首评仍未成功');
        }
    }

    async function loadCommentRetries() {
        const tbody = document.getElementById('commentRetryTableBody');
        if (!tbody) return;
        try {
            const resp = await fetch('/api/publishing/jobs?status=published&comment_status=failed&limit=50');
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || '加载失败');
            const jobs = data.jobs || [];
            if (!jobs.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">暂无待重试首评</td></tr>';
                return;
            }
            tbody.innerHTML = jobs.map((job) => `
                <tr>
                    <td>${esc(job.title)}</td>
                    <td>${esc(job.platform_display_name || job.platform || '—')}</td>
                    <td>${esc(commentStatusLabel(job.comment_status))}</td>
                    <td>${esc(String(job.comment_retry_count || 0))}</td>
                    <td><button type="button" class="btn btn-soft btn-sm" data-action="retry-comment" data-job-id="${esc(job.id)}">重试首评</button></td>
                </tr>
            `).join('');
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">加载失败：${esc(err.message)}</td></tr>`;
        }
    }

    async function loadQueue() {
        const tbody = document.getElementById('queueTableBody');
        try {
            const resp = await fetch('/api/publishing/jobs?limit=200');
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || '加载失败');

            const activeJobs = (data.jobs || []).filter((job) => ACTIVE_STATUSES.has(job.status));
            const rows = groupQueueJobs(data.jobs || []);
            updateSummary(activeJobs);
            tbody.innerHTML = renderQueueRows(rows);
            loadCommentRetries();
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="6" class="empty-cell">加载失败：${esc(err.message)}</td></tr>`;
        }
    }

    function openReschedule(jobId, title, scheduledAt, isArticleGroup) {
        scheduleJobId = jobId;
        scheduleIsArticleGroup = isArticleGroup;
        document.getElementById('scheduleModalTitle').textContent = title || '未命名';
        document.getElementById('scheduleModalNote').textContent = isArticleGroup
            ? '本篇各平台将共用同一发布时间；若勾选顺延，后续自动发布任务会依次后移。'
            : '仅修改本条任务的发布时间。';
        document.getElementById('scheduleDatetime').value = scheduledAt
            ? toBeijingDatetimeLocalValue(scheduledAt)
            : toBeijingDatetimeLocalValue(beijingNowPlusMinutes(60));
        document.getElementById('scheduleCascade').checked = isArticleGroup;
        document.getElementById('scheduleModal').hidden = false;
    }

    function closeRescheduleModal() {
        document.getElementById('scheduleModal').hidden = true;
        scheduleJobId = null;
        scheduleIsArticleGroup = false;
    }

    async function saveReschedule() {
        if (!scheduleJobId) return;
        const parsed = parseBeijingDatetimeLocal(document.getElementById('scheduleDatetime').value);
        if (!parsed) {
            alert('请选择有效的发布时间');
            return;
        }
        const body = {
            scheduled_at: parsed.toISOString().replace('.000Z', 'Z'),
            cascade: document.getElementById('scheduleCascade').checked,
        };
        const resp = await fetch(`/api/publishing/jobs/${scheduleJobId}/schedule`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok) {
            alert('改期失败: ' + (data.detail || data.message || resp.statusText));
            return;
        }
        closeRescheduleModal();
        await loadQueue();
    }

    async function cancelJobs(jobIds) {
        const ids = (jobIds || []).filter(Boolean);
        if (!ids.length) return;
        const message = ids.length > 1
            ? `确定取消本篇 ${ids.length} 个平台的发布任务？`
            : '确定取消该任务？';
        if (!confirm(message)) return;
        for (const jobId of ids) {
            const resp = await fetch(`/api/publishing/jobs/${jobId}/cancel`, { method: 'POST' });
            const data = await resp.json();
            if (!resp.ok) {
                alert('取消失败: ' + (data.detail || data.message || resp.statusText));
                return;
            }
        }
        await loadQueue();
    }

    function handleTableClick(event) {
        const button = event.target.closest('button[data-action]');
        if (!button) return;

        const jobId = button.dataset.jobId;
        const action = button.dataset.action;
        const row = button.closest('tr');

        if (action === 'reschedule') {
            openReschedule(
                jobId,
                button.dataset.title || '',
                button.dataset.scheduledAt || '',
                button.dataset.articleGroup === '1',
            );
            return;
        }

        if (action === 'cancel') {
            const groupIds = row?.dataset?.jobIds;
            cancelJobs(groupIds ? groupIds.split(',') : [jobId]);
            return;
        }

        if (action === 'retry-comment' && jobId) {
            retryComment(jobId)
                .then(() => {
                    loadQueue();
                })
                .catch((err) => alert('首评重试失败: ' + err.message));
        }
    }

    function bindEvents() {
        document.getElementById('refreshQueueBtn')?.addEventListener('click', () => {
            loadQueue();
            checkHealth();
        });
        document.getElementById('queueTableBody')?.addEventListener('click', handleTableClick);
        document.getElementById('commentRetryTableBody')?.addEventListener('click', handleTableClick);
        document.getElementById('scheduleCancelBtn')?.addEventListener('click', closeRescheduleModal);
        document.getElementById('scheduleSaveBtn')?.addEventListener('click', () => {
            saveReschedule().catch((err) => alert('改期失败: ' + err.message));
        });
        document.getElementById('scheduleModal')?.addEventListener('click', (event) => {
            if (event.target.id === 'scheduleModal') closeRescheduleModal();
        });
    }

    function init() {
        bindEvents();
        checkHealth();
        loadQueue();
        refreshTimer = window.setInterval(() => {
            loadQueue();
            checkHealth();
        }, 5000);
        window.addEventListener('beforeunload', () => {
            if (refreshTimer) window.clearInterval(refreshTimer);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
