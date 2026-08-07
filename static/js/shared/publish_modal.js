/**
 * Reusable publish modal for semi-automatic video publishing.
 */
(function () {
    const MODAL_ID = 'publishModalOverlay';

    function ensureModal() {
        if (document.getElementById(MODAL_ID)) return;
        const html = `
        <div id="${MODAL_ID}" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:2000;align-items:center;justify-content:center;">
          <div style="background:#fff;border-radius:12px;max-width:520px;width:92%;padding:24px;box-shadow:0 8px 32px rgba(0,0,0,.15);max-height:90vh;overflow:auto;">
            <h3 style="margin:0 0 16px;">📤 发布短视频</h3>
            <input type="hidden" id="publishModalVideoPath" />
            <input type="hidden" id="publishModalCoverPath" />
            <div id="publishModalCoverPreview" style="display:none;margin-bottom:12px;">
              <label style="display:block;font-size:13px;color:#475569;">封面预览</label>
              <img id="publishModalCoverImg" alt="封面" style="max-width:100%;max-height:160px;border-radius:8px;border:1px solid #e2e8f0;margin-top:6px;" />
            </div>
            <label style="display:block;font-size:13px;color:#475569;">标题</label>
            <input id="publishModalTitle" style="width:100%;margin:6px 0 12px;padding:8px;border:1px solid #cbd5e1;border-radius:6px;box-sizing:border-box;" />
            <label style="display:block;font-size:13px;color:#475569;">描述</label>
            <textarea id="publishModalDescription" rows="3" style="width:100%;margin:6px 0 12px;padding:8px;border:1px solid #cbd5e1;border-radius:6px;box-sizing:border-box;"></textarea>
            <label style="display:block;font-size:13px;color:#475569;">标签（逗号分隔）</label>
            <input id="publishModalTags" style="width:100%;margin:6px 0 12px;padding:8px;border:1px solid #cbd5e1;border-radius:6px;box-sizing:border-box;" />
            <label style="display:block;font-size:13px;color:#475569;">发布账号</label>
            <select id="publishModalAccount" style="width:100%;margin:6px 0 12px;padding:8px;border:1px solid #cbd5e1;border-radius:6px;box-sizing:border-box;"></select>
            <label style="display:flex;align-items:center;gap:8px;font-size:13px;color:#475569;margin:4px 0 8px;cursor:pointer;">
              <input type="checkbox" id="publishModalScheduleEnabled" />
              定时发布
            </label>
            <div id="publishModalScheduleWrap" style="display:none;margin-bottom:12px;">
              <label style="display:block;font-size:13px;color:#475569;">发布时间</label>
              <input type="datetime-local" id="publishModalScheduleAt" style="width:100%;margin:6px 0 0;padding:8px;border:1px solid #cbd5e1;border-radius:6px;box-sizing:border-box;" />
              <p style="font-size:12px;color:#64748b;margin:6px 0 0;">到达设定时间后由发布 worker 自动上传</p>
            </div>
            <div id="publishModalError" style="color:#dc2626;font-size:13px;margin-bottom:8px;display:none;"></div>
            <div style="display:flex;gap:8px;justify-content:flex-end;">
              <button type="button" id="publishModalCancel" style="padding:8px 16px;border:1px solid #cbd5e1;background:#fff;border-radius:6px;cursor:pointer;">取消</button>
              <button type="button" id="publishModalConfirm" style="padding:8px 16px;background:#667eea;color:#fff;border:none;border-radius:6px;cursor:pointer;">确认发布</button>
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
            wrap.style.display = this.checked ? 'block' : 'none';
            if (this.checked) {
                setDefaultScheduleTime();
            }
        };
    }

    function setDefaultScheduleTime() {
        const input = document.getElementById('publishModalScheduleAt');
        if (!input || input.value) return;
        const d = new Date(Date.now() + 60 * 60 * 1000);
        d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0);
        input.value = toDatetimeLocalValue(d);
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
        const select = document.getElementById('publishModalAccount');
        select.innerHTML = '<option value="">加载中…</option>';
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
                select.innerHTML = `<option value="">以下账号仅支持登录，暂不可发布：${names}</option>`;
                return;
            }
            const inactive = all.filter((a) => a.status !== 'active');
            if (inactive.length) {
                select.innerHTML = '<option value="">有账号但会话已过期，请到发布中心重新登录</option>';
                return;
            }
            select.innerHTML = '<option value="">请先在发布中心添加可发布平台账号</option>';
            return;
        }
        select.innerHTML = accounts.map((a) => {
            const label = a.platform_display_name || a.platform;
            return `<option value="${a.id}">${a.nickname || label} (${label})</option>`;
        }).join('');
    }

    function formatTagsForDescription(draft) {
        const d = draft || {};
        if (typeof d.tags === 'string' && d.tags.trim()) {
            return d.tags.trim();
        }
        const tags = parseTagsField((d.praise_tags && d.praise_tags.length ? d.praise_tags : d.tags) || []);
        return tags.map((t) => (t.startsWith('#') ? t : `#${t}`)).join(' ');
    }

    function buildDraftFields(draft) {
        const d = draft || {};
        const title = String(d.main_line1 || '').trim().replace(/！/g, '？').slice(0, 30);
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
            coverPreview.style.display = 'block';
        } else {
            coverImg.removeAttribute('src');
            coverPreview.style.display = 'none';
        }
        document.getElementById('publishModalTitle').value = fields.title;
        document.getElementById('publishModalDescription').value = fields.description;
        document.getElementById('publishModalTags').value = fields.tags.join(', ');
        document.getElementById('publishModalError').style.display = 'none';
        document.getElementById('publishModalScheduleEnabled').checked = false;
        document.getElementById('publishModalScheduleWrap').style.display = 'none';
        document.getElementById('publishModalScheduleAt').value = '';
        await loadAccounts();
        const overlay = document.getElementById(MODAL_ID);
        overlay.style.display = 'flex';
    };

    window.closePublishModal = function () {
        const overlay = document.getElementById(MODAL_ID);
        if (overlay) overlay.style.display = 'none';
    };

    async function submitPublishModal() {
        const errEl = document.getElementById('publishModalError');
        errEl.style.display = 'none';
        const accountId = document.getElementById('publishModalAccount').value;
        const videoPath = document.getElementById('publishModalVideoPath').value;
        const coverPath = document.getElementById('publishModalCoverPath').value;
        const title = document.getElementById('publishModalTitle').value.trim();
        const description = document.getElementById('publishModalDescription').value.trim();
        const tags = document.getElementById('publishModalTags').value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
        const scheduleEnabled = document.getElementById('publishModalScheduleEnabled').checked;
        const scheduleAtRaw = document.getElementById('publishModalScheduleAt').value;
        if (!accountId) {
            errEl.textContent = '请选择发布账号';
            errEl.style.display = 'block';
            return;
        }
        if (!videoPath || !title) {
            errEl.textContent = '视频路径或标题不能为空';
            errEl.style.display = 'block';
            return;
        }
        let scheduledAt = null;
        if (scheduleEnabled) {
            if (!scheduleAtRaw) {
                errEl.textContent = '请选择定时发布时间';
                errEl.style.display = 'block';
                return;
            }
            const when = new Date(scheduleAtRaw);
            if (Number.isNaN(when.getTime()) || when.getTime() <= Date.now()) {
                errEl.textContent = '定时发布时间必须晚于当前时间';
                errEl.style.display = 'block';
                return;
            }
            scheduledAt = when.toISOString();
        }
        const draft = window.lastPublishDraft || {};
        const payload = {
            account_id: accountId,
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
        if (coverPath) {
            payload.cover_path = coverPath;
        }
        if (scheduledAt) {
            payload.scheduled_at = scheduledAt;
        }
        const resp = await fetch('/api/publishing/jobs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok) {
            const msg = typeof data.detail === 'string' ? data.detail : (data.detail && data.detail.message) || '发布失败';
            errEl.textContent = msg;
            errEl.style.display = 'block';
            return;
        }
        closePublishModal();
        const successMsg = scheduledAt
            ? `已提交定时发布任务（${new Date(scheduledAt).toLocaleString()}），到达时间后将自动上传并发布`
            : '已提交发布任务：将自动上传、填写文案并点击发布';
        if (typeof window.showToast === 'function') {
            window.showToast(successMsg, 'success', 4000);
        } else if (typeof window.setStatus === 'function') {
            window.setStatus(successMsg, 'ok');
        } else {
            alert(successMsg);
        }
    }
})();
