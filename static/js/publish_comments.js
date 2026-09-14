/** 评论管理：观众评论扫描、回复与收件箱 */
(function () {
    function esc(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/"/g, '&quot;');
    }

    async function loadCommentReplySettings() {
        const resp = await fetch('/api/publishing/comment-reply/settings');
        const data = await resp.json();
        const checkbox = document.getElementById('commentReplyEnabled');
        if (checkbox) checkbox.checked = !!data.enabled;
        const modeSelect = document.getElementById('commentReplyMode');
        if (modeSelect && data.mode) {
            modeSelect.value = data.mode;
            modeSelect.dataset.lastValue = data.mode;
        }
        const lookbackInput = document.getElementById('commentReplyLookbackHours');
        if (lookbackInput && data.lookback_hours != null) {
            lookbackInput.value = String(data.lookback_hours);
            lookbackInput.dataset.lastValue = String(data.lookback_hours);
        }
    }

    async function loadCommentReplyRuns() {
        const meta = document.getElementById('commentReplyRunMeta');
        if (!meta) return;
        try {
            const resp = await fetch('/api/publishing/comment-reply/runs?limit=1');
            const data = await resp.json();
            const run = (data.items || [])[0];
            if (!run) {
                meta.textContent = '上次运行：暂无记录';
                return;
            }
            const when = run.finished_at || run.started_at || '';
            const whenText = (typeof formatBeijingDateTime === 'function' && when)
                ? formatBeijingDateTime(when)
                : when;
            meta.textContent = [
                `上次运行：${whenText}`,
                `模式 ${run.mode}`,
                `待审 ${run.new_pending}`,
                `自动发 ${run.auto_sent}`,
                `重试 ${run.retried}`,
                `失败 ${run.failed}`,
            ].join(' · ');
        } catch (err) {
            meta.textContent = '上次运行：加载失败';
        }
    }

    async function saveCommentReplySettings(payload) {
        const resp = await fetch('/api/publishing/comment-reply/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.message || '保存失败');
        return data;
    }

    function commentInboxStatusLabel(status) {
        const map = {
            pending_approval: '待审核',
            replied: '已回复',
            skipped: '已跳过',
            failed: '失败',
        };
        return map[status] || status;
    }

    async function loadCommentInbox() {
        const tbody = document.getElementById('commentInboxTable');
        if (!tbody) return;
        const status = document.getElementById('commentInboxStatus')?.value || 'replied';
        const query = status ? `?status=${encodeURIComponent(status)}&limit=50` : '?limit=50';
        try {
            const resp = await fetch(`/api/publishing/comment-inbox${query}`);
            const raw = await resp.text();
            let data;
            try {
                data = raw ? JSON.parse(raw) : {};
            } catch {
                throw new Error(raw.slice(0, 200) || resp.statusText || '加载失败');
            }
            if (!resp.ok) throw new Error(data.detail || data.message || '加载失败');
            const items = data.items || [];
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">暂无评论</td></tr>';
                return;
            }
            tbody.innerHTML = items.map((item) => {
                const title = esc((item.post_title || '').slice(0, 24));
                const author = esc(item.author_name || '观众');
                const content = esc((item.content || '').slice(0, 60));
                const reply = esc(item.reply_text || '');
                const actions = item.status === 'pending_approval'
                    ? `<button class="btn btn-sm" data-comment-action="approve" data-id="${esc(item.id)}">确认发送</button>
                       <button class="btn-secondary btn btn-sm" data-comment-action="reject" data-id="${esc(item.id)}">跳过</button>`
                    : (item.status === 'failed'
                        ? `<button class="btn btn-sm" data-comment-action="approve" data-id="${esc(item.id)}">重试发送</button>`
                        : '');
                return `<tr>
                    <td>${title}</td>
                    <td>${author}</td>
                    <td>${content}</td>
                    <td><textarea class="form-control" rows="2" id="reply-${esc(item.id)}">${reply}</textarea></td>
                    <td>${commentInboxStatusLabel(item.status)}</td>
                    <td>${actions}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="6" class="empty-cell">加载失败: ${esc(err.message)}</td></tr>`;
        }
    }

    async function approveCommentReply(inboxId) {
        const textarea = document.getElementById(`reply-${inboxId}`);
        const replyText = textarea ? textarea.value.trim() : '';
        const resp = await fetch(`/api/publishing/comment-inbox/${inboxId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reply_text: replyText || null }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            alert('发送失败: ' + (data.detail || data.error || resp.statusText));
            return;
        }
        alert('回复已发送');
        loadCommentInbox();
    }

    async function rejectCommentReply(inboxId) {
        const resp = await fetch(`/api/publishing/comment-inbox/${inboxId}/reject`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) {
            alert('操作失败: ' + (data.detail || resp.statusText));
            return;
        }
        loadCommentInbox();
    }

    async function triggerCommentReplyScan() {
        const btn = document.getElementById('commentReplyScanBtn');
        if (btn) btn.disabled = true;
        try {
            const resp = await fetch('/api/publishing/comment-reply/scan', { method: 'POST' });
            const raw = await resp.text();
            let data;
            try {
                data = raw ? JSON.parse(raw) : {};
            } catch {
                throw new Error(raw.slice(0, 200) || resp.statusText || '扫描失败');
            }
            if (!resp.ok) throw new Error(data.detail || data.message || '扫描失败');
            const platformLines = (data.summaries || []).map((item) => {
                const label = item.platform === 'wechat_channels' ? '视频号' : item.platform === 'kuaishou' ? '快手' : item.platform;
                const err = item.errors ? `，异常 ${item.errors}` : '';
                return `${label}：作品 ${item.posts_scanned ?? 0}，评论 ${item.comments_seen ?? 0}，发送 ${item.auto_sent ?? 0}${err}`;
            });
            const parts = [
                data.message,
                `账号 ${data.accounts ?? 0} 个`,
                `扫描作品 ${data.posts_scanned ?? 0} 个`,
                `看到评论 ${data.comments_seen ?? 0} 条`,
                `新增待审 ${data.new_pending ?? 0} 条`,
                `自动发 ${data.auto_sent ?? 0} 条`,
                `跳过 ${data.skipped ?? 0} 条`,
                ...platformLines,
            ].filter(Boolean);
            alert(parts.join('\n'));
            loadCommentInbox();
            loadCommentReplyRuns();
        } catch (err) {
            alert('扫描失败: ' + err.message);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async function retryFailedCommentReplies() {
        const btn = document.getElementById('commentReplyRetryBtn');
        if (btn) btn.disabled = true;
        try {
            const resp = await fetch('/api/publishing/comment-reply/retry-failed', { method: 'POST' });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || '重试失败');
            alert(`重试完成：成功 ${data.retried ?? 0} 条，仍失败 ${data.failed ?? 0} 条`);
            loadCommentInbox();
            loadCommentReplyRuns();
        } catch (err) {
            alert('重试失败: ' + err.message);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async function regenerateCommentReplies() {
        if (!confirm('将重新生成所有待审核回复文案，是否继续？')) return;
        const btn = document.getElementById('commentReplyRegenerateBtn');
        if (btn) btn.disabled = true;
        try {
            const resp = await fetch('/api/publishing/comment-reply/regenerate', { method: 'POST' });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || '重生成失败');
            alert(`重生成完成：成功 ${data.regenerated ?? 0} 条，失败 ${data.errors ?? 0} 条`);
            loadCommentInbox();
        } catch (err) {
            alert('重生成失败: ' + err.message);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    function initCommentInboxPage() {
        if (!document.getElementById('commentInboxTable')) return;

        document.getElementById('commentReplyEnabled')?.addEventListener('change', async (event) => {
            const enabled = event.target.checked;
            try {
                await saveCommentReplySettings({ enabled });
            } catch (err) {
                event.target.checked = !enabled;
                alert('保存评论回复开关失败: ' + err.message);
            }
        });
        document.getElementById('commentReplyMode')?.addEventListener('change', async (event) => {
            const mode = event.target.value;
            const previous = event.target.dataset.lastValue || 'approve';
            try {
                await saveCommentReplySettings({ mode });
                event.target.dataset.lastValue = mode;
            } catch (err) {
                event.target.value = previous;
                alert('保存评论回复模式失败: ' + err.message);
            }
        });
        document.getElementById('commentReplyLookbackHours')?.addEventListener('change', async (event) => {
            const raw = Number(event.target.value);
            const previous = event.target.dataset.lastValue || '48';
            if (!Number.isFinite(raw) || raw < 1 || raw > 168) {
                alert('评论时效须在 1～168 小时之间');
                event.target.value = previous;
                return;
            }
            const hours = Math.round(raw);
            try {
                await saveCommentReplySettings({ lookback_hours: hours });
                event.target.dataset.lastValue = String(hours);
                event.target.value = String(hours);
            } catch (err) {
                event.target.value = previous;
                alert('保存评论时效失败: ' + err.message);
            }
        });
        document.getElementById('commentInboxStatus')?.addEventListener('change', loadCommentInbox);
        document.getElementById('commentReplyScanBtn')?.addEventListener('click', triggerCommentReplyScan);
        document.getElementById('commentInboxRefreshBtn')?.addEventListener('click', loadCommentInbox);
        document.getElementById('commentReplyRetryBtn')?.addEventListener('click', retryFailedCommentReplies);
        document.getElementById('commentReplyRegenerateBtn')?.addEventListener('click', regenerateCommentReplies);
        document.getElementById('commentInboxTable')?.addEventListener('click', (event) => {
            const btn = event.target.closest('[data-comment-action]');
            if (!btn) return;
            const inboxId = btn.dataset.id;
            if (btn.dataset.commentAction === 'approve') approveCommentReply(inboxId);
            if (btn.dataset.commentAction === 'reject') rejectCommentReply(inboxId);
        });

        loadCommentReplySettings();
        loadCommentReplyRuns();
        loadCommentInbox();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCommentInboxPage);
    } else {
        initCommentInboxPage();
    }
})();
