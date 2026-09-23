/**
 * Reusable publish modal for semi-automatic video publishing.
 */
(function () {
    const MODAL_ID = 'publishModalOverlay';

    function ensureModal() {
        if (document.getElementById(MODAL_ID)) return;
        const html = `
        <div id="${MODAL_ID}" class="app-modal-overlay" hidden>
          <div class="app-modal" role="dialog" aria-modal="true" aria-labelledby="publishModalHeading">
            <h3 id="publishModalHeading">📤 发布短视频</h3>
            <input type="hidden" id="publishModalVideoPath" />
            <input type="hidden" id="publishModalCoverPath" />
            <div id="publishModalCoverPreview" class="app-modal-cover" hidden>
              <label class="app-modal-label">封面预览</label>
              <img id="publishModalCoverImg" alt="封面" />
            </div>
            <label class="app-modal-label" for="publishModalTitle">标题（视频号短标题，最多16字，无标点）</label>
            <input id="publishModalTitle" class="form-control" maxlength="16" />
            <label class="app-modal-label" for="publishModalDescription">描述</label>
            <textarea id="publishModalDescription" class="form-control" rows="3"></textarea>
            <label class="app-modal-label" for="publishModalTags">标签（逗号分隔）</label>
            <input id="publishModalTags" class="form-control" />
            <label class="app-modal-label" for="publishModalFirstComment">首评（可选，15~50字）</label>
            <textarea id="publishModalFirstComment" class="form-control" rows="2" maxlength="50" placeholder="问句优先，引导评论"></textarea>
            <label class="app-modal-label">发布账号（可多选，将逐一提交）</label>
            <div id="publishModalAccounts" class="app-modal-account-list"></div>
            <div id="publishModalAccountActions" class="app-modal-account-actions" hidden>
              <button type="button" id="publishModalSelectAll" class="btn btn-sm btn-secondary">全选</button>
              <button type="button" id="publishModalClearAll" class="btn btn-sm btn-secondary">清空</button>
            </div>
            <label class="app-modal-check">
              <input type="checkbox" id="publishModalScheduleEnabled" />
              定时发布
            </label>
            <div id="publishModalScheduleWrap" hidden>
              <label class="app-modal-label" for="publishModalScheduleAt">发布时间</label>
              <input type="datetime-local" id="publishModalScheduleAt" class="form-control" />
              <p class="app-modal-hint">到达设定时间后由发布 worker 自动上传</p>
            </div>
            <div id="publishModalError" class="app-modal-error" hidden></div>
            <div class="app-modal-actions">
              <button type="button" id="publishModalCancel" class="btn btn-secondary">取消</button>
              <button type="button" id="publishModalConfirm" class="btn btn-primary">确认发布</button>
            </div>
          </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        document.getElementById('publishModalCancel').onclick = closePublishModal;
        document.getElementById('publishModalConfirm').onclick = submitPublishModal;
        document.getElementById(MODAL_ID).onclick = function (e) {
            if (e.target.id === MODAL_ID) closePublishModal();
        };
        document.getElementById('publishModalScheduleEnabled').onchange = function () {
            const wrap = document.getElementById('publishModalScheduleWrap');
            wrap.hidden = !this.checked;
            if (this.checked) {
                setDefaultScheduleTime();
            }
        };
        document.getElementById('publishModalSelectAll').onclick = function () {
            document.querySelectorAll('.publish-modal-account').forEach((el) => {
                el.checked = true;
            });
        };
        document.getElementById('publishModalClearAll').onclick = function () {
            document.querySelectorAll('.publish-modal-account').forEach((el) => {
                el.checked = false;
            });
        };
    }

    function escapeHtml(text) {
        return String(text || '').replace(/[&<>"']/g, (ch) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        })[ch]);
    }

    function setAccountListMessage(message) {
        const container = document.getElementById('publishModalAccounts');
        const actions = document.getElementById('publishModalAccountActions');
        container.innerHTML = `<p class="app-modal-hint">${escapeHtml(message)}</p>`;
        if (actions) actions.hidden = true;
    }

    function getSelectedAccountIds() {
        return [...document.querySelectorAll('.publish-modal-account:checked')]
            .map((el) => el.value)
            .filter(Boolean);
    }

    function setDefaultScheduleTime() {
        const input = document.getElementById('publishModalScheduleAt');
        if (!input || input.value) return;
        const d = typeof beijingNowPlusMinutes === 'function'
            ? beijingNowPlusMinutes(60)
            : new Date(Date.now() + 60 * 60 * 1000);
        input.value = typeof toBeijingDatetimeLocalValue === 'function'
            ? toBeijingDatetimeLocalValue(d)
            : toDatetimeLocalValue(d);
    }

    function toDatetimeLocalValue(date) {
        const pad = (n) => String(n).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    function parseTagsField(tags) {
        if (Array.isArray(tags)) {
            return tags.map((t) => String(t).trim()).filter(Boolean);
        }
        const raw = String(tags || '').trim();
        if (!raw) return [];
        if (raw.includes('#')) {
            return raw.split(/[#\s,，]+/).map((t) => t.trim()).filter(Boolean);
        }
        return raw.split(/[,，]/).map((t) => t.trim()).filter(Boolean);
    }

    function normalizeMediaPath(path) {
        const p = String(path || '').trim();
        if (!p) return '';
        return p.startsWith('/') ? p.slice(1) : p;
    }

    function mediaDisplayUrl(path) {
        const p = String(path || '').trim();
        if (!p) return '';
        return p.startsWith('/') ? p : `/${p}`;
    }

    async function loadAccounts() {
        const container = document.getElementById('publishModalAccounts');
        const actions = document.getElementById('publishModalAccountActions');
        container.innerHTML = '<p class="app-modal-hint">加载中…</p>';
        if (actions) actions.hidden = true;
        const resp = await fetch('/api/publishing/accounts');
        const data = await resp.json();
        const all = data.accounts || [];
        const accounts = all.filter((a) => a.status === 'active' && a.can_publish);
        if (!accounts.length) {
            const activeOnly = all.filter((a) => a.status === 'active' && !a.can_publish);
            if (activeOnly.length) {
                const names = activeOnly
                    .map((a) => a.platform_display_name || a.platform)
                    .join('、');
                setAccountListMessage(`以下账号仅支持登录，暂不可发布：${names}`);
                return;
            }
            const inactive = all.filter((a) => a.status !== 'active');
            if (inactive.length) {
                setAccountListMessage('有账号但会话已过期，请到发布中心重新登录');
                return;
            }
            setAccountListMessage('请先在发布中心添加可发布平台账号');
            return;
        }
        container.innerHTML = accounts.map((a) => {
            const label = a.platform_display_name || a.platform;
            const nickname = a.nickname || label;
            const display = `${nickname} (${label})`;
            return `<label class="app-modal-account-row">
                <input type="checkbox" class="publish-modal-account" value="${escapeHtml(a.id)}"
                    data-label="${escapeHtml(display)}" data-platform="${escapeHtml(a.platform || '')}" checked />
                <span>${escapeHtml(display)}</span>
            </label>`;
        }).join('');
        if (actions) actions.hidden = accounts.length <= 1;
    }

    function formatTagsForDescription(draft) {
        const d = draft || {};
        if (typeof d.tags === 'string' && d.tags.trim()) {
            return d.tags.trim();
        }
        const tags = parseTagsField((d.praise_tags && d.praise_tags.length ? d.praise_tags : d.tags) || []);
        return tags.map((t) => (t.startsWith('#') ? t : `#${t}`)).join(' ');
    }

    function sanitizeShortTitle(text) {
        const kept = String(text || '').split('').map((ch) => {
            if ('.．。'.includes(ch)) return '点';
            if ('-－—–'.includes(ch)) return '';
            return (ch === ' ' || /[\p{L}\p{N}]/u.test(ch)) ? ch : '';
        }).join('');
        return kept.replace(/\s+/g, ' ').trim().slice(0, 16);
    }

    function wechatTitleFromDraft(draft) {
        const d = draft || {};
        return sanitizeShortTitle(d.short_title || d.main_line1 || '');
    }

    function buildDraftFields(draft) {
        const d = draft || {};
        const title = wechatTitleFromDraft(d);
        const descParts = [
            d.main_line2,
            d.sub_title,
            d.sub_title2,
            d.summary,
        ].map((s) => String(s || '').trim()).filter(Boolean);
        const tagsLine = formatTagsForDescription(d);
        if (tagsLine) descParts.push(tagsLine);
        const description = descParts.join('\n');
        const tags = parseTagsField(
            (d.praise_tags && d.praise_tags.length ? d.praise_tags : d.tags) || []
        );
        return { title, description, tags };
    }

    window.openPublishModal = async function ({ videoPath, coverPath, draft, sourceType, sourceId }) {
        ensureModal();
        const fields = buildDraftFields(draft);
        window.lastPublishDraft = {
            source_type: sourceType || 'index',
            source_id: sourceId || null,
            ...(draft || {}),
        };
        document.getElementById('publishModalVideoPath').value = normalizeMediaPath(videoPath);
        const coverNormalized = normalizeMediaPath(coverPath);
        document.getElementById('publishModalCoverPath').value = coverNormalized;
        const coverPreview = document.getElementById('publishModalCoverPreview');
        const coverImg = document.getElementById('publishModalCoverImg');
        if (coverNormalized) {
            coverImg.src = mediaDisplayUrl(coverNormalized);
            coverPreview.hidden = false;
        } else {
            coverImg.removeAttribute('src');
            coverPreview.hidden = true;
        }
        document.getElementById('publishModalTitle').value = fields.title;
        document.getElementById('publishModalDescription').value = fields.description;
        document.getElementById('publishModalTags').value = fields.tags.join(', ');
        document.getElementById('publishModalFirstComment').value = String((draft && draft.first_comment) || '').trim();
        document.getElementById('publishModalError').hidden = true;
        document.getElementById('publishModalScheduleEnabled').checked = false;
        document.getElementById('publishModalScheduleWrap').hidden = true;
        document.getElementById('publishModalScheduleAt').value = '';
        await loadAccounts();
        const overlay = document.getElementById(MODAL_ID);
        overlay.hidden = false;
        overlay.classList.add('is-open');
    };

    window.closePublishModal = function () {
        const overlay = document.getElementById(MODAL_ID);
        if (!overlay) return;
        overlay.classList.remove('is-open');
        overlay.hidden = true;
    };

    async function submitPublishModal() {
        const errEl = document.getElementById('publishModalError');
        const confirmBtn = document.getElementById('publishModalConfirm');
        errEl.hidden = true;
        const accountIds = getSelectedAccountIds();
        const videoPath = document.getElementById('publishModalVideoPath').value;
        const coverPath = document.getElementById('publishModalCoverPath').value;
        const title = sanitizeShortTitle(document.getElementById('publishModalTitle').value);
        const description = document.getElementById('publishModalDescription').value.trim();
        const tags = document.getElementById('publishModalTags').value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
        const firstComment = document.getElementById('publishModalFirstComment').value.trim();
        const scheduleEnabled = document.getElementById('publishModalScheduleEnabled').checked;
        const scheduleAtRaw = document.getElementById('publishModalScheduleAt').value;
        if (!accountIds.length) {
            errEl.textContent = '请至少选择一个发布账号';
            errEl.hidden = false;
            return;
        }
        if (!videoPath || !title) {
            errEl.textContent = '视频路径或标题不能为空';
            errEl.hidden = false;
            return;
        }
        let scheduledAt = null;
        if (scheduleEnabled) {
            if (!scheduleAtRaw) {
                errEl.textContent = '请选择定时发布时间';
                errEl.hidden = false;
                return;
            }
            const when = typeof parseBeijingDatetimeLocal === 'function'
                ? parseBeijingDatetimeLocal(scheduleAtRaw)
                : new Date(scheduleAtRaw);
            if (Number.isNaN(when.getTime()) || when.getTime() <= Date.now()) {
                errEl.textContent = '定时发布时间必须晚于当前时间';
                errEl.hidden = false;
                return;
            }
            scheduledAt = when.toISOString();
        }
        const draft = window.lastPublishDraft || {};
        const basePayload = {
            video_path: videoPath,
            title,
            description,
            main_line2: String(draft.main_line2 || '').trim() || null,
            sub_title: String(draft.sub_title || '').trim() || null,
            sub_title2: String(draft.sub_title2 || '').trim() || null,
            summary: String(draft.summary || '').trim() || null,
            tags,
            source_type: (window.lastPublishDraft && window.lastPublishDraft.source_type) || 'index',
            source_id: window.lastPublishDraft && window.lastPublishDraft.source_id,
        };
        if (scheduledAt) {
            basePayload.scheduled_at = scheduledAt;
        }
        if (firstComment) {
            basePayload.first_comment_text = firstComment;
        }

        const originalLabel = confirmBtn.textContent;
        confirmBtn.disabled = true;
        const failures = [];
        const accountLabels = Object.fromEntries(
            [...document.querySelectorAll('.publish-modal-account')].map((el) => [
                el.value,
                el.dataset.label || el.value,
            ])
        );
        const accountPlatforms = Object.fromEntries(
            [...document.querySelectorAll('.publish-modal-account')].map((el) => [
                el.value,
                el.dataset.platform || '',
            ])
        );
        try {
            for (let index = 0; index < accountIds.length; index += 1) {
                const accountId = accountIds[index];
                confirmBtn.textContent = `提交中 ${index + 1}/${accountIds.length}…`;
                const platform = accountPlatforms[accountId] || '';
                const payload = { ...basePayload, account_id: accountId };
                if (platform && platform !== 'wechat_channels') {
                    const longTitle = String(draft.main_line1 || title).trim();
                    if (longTitle) payload.title = longTitle.slice(0, 30);
                }
                if (coverPath && accountPlatforms[accountId] !== 'douyin') {
                    payload.cover_path = coverPath;
                }
                if (draft.playbook_attribution && draft.playbook_version_id && draft.copy_draft_id) {
                    payload.playbook_attribution = draft.playbook_attribution;
                    payload.playbook_version_id = draft.playbook_version_id;
                    payload.copy_draft_id = draft.copy_draft_id;
                }
                const resp = await fetch('/api/publishing/jobs', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await resp.json();
                if (!resp.ok) {
                    const msg = typeof data.detail === 'string'
                        ? data.detail
                        : (data.detail && data.detail.message) || '发布失败';
                    failures.push({
                        label: accountLabels[accountId] || accountId,
                        message: msg,
                    });
                }
            }
        } finally {
            confirmBtn.disabled = false;
            confirmBtn.textContent = originalLabel;
        }

        if (failures.length === accountIds.length) {
            const detail = failures.map((item) => `${item.label}: ${item.message}`).join('；');
            errEl.textContent = `全部提交失败：${detail}`;
            errEl.hidden = false;
            return;
        }

        closePublishModal();
        const successCount = accountIds.length - failures.length;
        let successMsg = scheduledAt
            ? `已为 ${successCount} 个账号提交定时发布任务（${formatBeijingDateTime(scheduledAt)}）`
            : `已为 ${successCount} 个账号提交发布任务，将逐一自动上传并发布`;
        if (failures.length) {
            const detail = failures.map((item) => `${item.label}: ${item.message}`).join('；');
            successMsg += `。失败 ${failures.length} 个：${detail}`;
        }
        if (typeof window.showToast === 'function') {
            window.showToast(successMsg, failures.length ? 'warning' : 'success', 4000);
        } else if (typeof window.setStatus === 'function') {
            window.setStatus(successMsg, failures.length ? 'error' : 'ok');
        } else {
            alert(successMsg);
        }
    }
})();
