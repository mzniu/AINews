(function () {
    let selectedArticleId = null;
    let selectedPrepare = null;
    let sourcesCache = [];
    let sourceNameMap = {};

    const $ = (id) => document.getElementById(id);

    async function api(path, options = {}) {
        const resp = await fetch(path, {
            headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
            ...options,
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.detail || data.message || `HTTP ${resp.status}`);
        }
        return data;
    }

    function setStatus(text, type = 'muted') {
        const bar = $('statusBar');
        if (!bar) return;
        bar.className = `small mt-2 text-${type === 'error' ? 'danger' : type === 'ok' ? 'success' : 'muted'}`;
        bar.textContent = text;
    }
    window.setStatus = setStatus;

    async function loadSources() {
        sourcesCache = await api('/api/ingestion/sources');
        sourceNameMap = Object.fromEntries(
            sourcesCache.map((s) => [s.id, s.display_name || s.id])
        );
        const sel = $('sourceSelect');
        const prev = sel.value;
        sel.innerHTML = '<option value="">所有数据源</option>' + sourcesCache.map((s) =>
            `<option value="${s.id}">${s.display_name} (${s.enabled ? '启用' : '停用'})</option>`
        ).join('');
        if (prev && [...sel.options].some((o) => o.value === prev)) {
            sel.value = prev;
        }
        updateSourceToolbar();
    }

    function updateSourceToolbar() {
        const sourceId = $('sourceSelect').value;
        const runBtn = $('runSourceBtn');
        if (runBtn) runBtn.disabled = false;
        if (!sourceId) {
            setStatus(`显示全部 ${sourcesCache.length} 个数据源的文章 · 可一键抓取全部已启用源`);
            return;
        }
        const s = sourcesCache.find((x) => x.id === sourceId);
        if (s) {
            setStatus(`调度: ${s.schedule_cron} | 上次运行: ${s.last_run_at || '—'}`);
        }
    }

    function formatViewCount(count) {
        if (count == null || count === '') return '';
        const n = Number(count);
        if (!Number.isFinite(n)) return '';
        if (n >= 10000) return `${(n / 10000).toFixed(1).replace(/\.0$/, '')}万浏览`;
        return `${n.toLocaleString()} 浏览`;
    }

    function formatImageGradeBadge(grade, score) {
        if (!grade) return '';
        const cls = `grade-${String(grade).toLowerCase()}`;
        const label = score != null ? `${grade} ${Math.round(score)}` : grade;
        return `<span class="badge grade-badge ${cls} img-grade-badge" title="配图相关度">${label}</span>`;
    }

    function renderImageGrid(images, { title, emptyText }) {
        if (!images || !images.length) {
            return `<div class="mb-2"><strong>${title}</strong><br><span class="text-muted">${emptyText}</span></div>`;
        }
        const sorted = [...images].sort((a, b) => {
            const ra = a.relevance_rank ?? 9999;
            const rb = b.relevance_rank ?? 9999;
            if (ra !== rb) return ra - rb;
            return (a.sort_order || 0) - (b.sort_order || 0);
        });
        const cards = sorted.map((img) => {
        const badge = formatImageGradeBadge(img.relevance_grade, img.relevance_score);
        const cover = img.cover_fit_score != null ? `<span class="badge badge-light ml-1" title="封面适配">封面 ${Math.round(img.cover_fit_score)}</span>` : '';
        const flash = img.flash_fit_score != null ? `<span class="badge badge-primary ml-1" title="主画面适配">主画面 ${Math.round(img.flash_fit_score)}</span>` : '';
        const figure = img.figure_prominence_score != null ? `<span class="badge badge-light ml-1" title="人物突出">人物 ${Math.round(img.figure_prominence_score)}</span>` : '';
        const animated = img.is_animated ? '<span class="badge badge-warning ml-1" title="动图优先">动图</span>' : '';
        const orient = img.orientation === 'landscape' ? '<span class="badge badge-info ml-1">横图</span>' : (img.orientation === 'portrait' ? '<span class="badge badge-secondary ml-1">竖图</span>' : '');
        const tip = img.verdict || img.caption || '';
        return `<div class="img-score-card mr-2 mb-2" title="${escapeHtml(tip)}">
                <img src="${img.local_path}" class="thumb" alt="">
                <div class="img-score-badges">${badge}${flash}${cover}${figure}${animated}${orient}</div>
            </div>`;
        }).join('');
        return `<div class="mb-2"><strong>${title}</strong><div class="d-flex flex-wrap">${cards}</div></div>`;
    }

    async function runScoreImages(id) {
        setStatus('正在评估配图相关度（视觉模型）…', 'muted');
        try {
            const res = await api(`/api/ingestion/articles/${id}/score-images`, {
                method: 'POST',
                body: JSON.stringify({ force: false, include_story_images: true }),
            });
            const autoN = (res.summary && res.summary.auto_selected_ids) ? res.summary.auto_selected_ids.length : 0;
            setStatus(
                `配图评估完成：${res.scored_count} 张` +
                    (res.from_cache ? '（缓存）' : ` · VL ${res.vl_calls} 次`) +
                    (autoN ? ` · 建议自动勾选 ${autoN} 张` : ''),
                'ok'
            );
            selectArticle(id);
        } catch (e) {
            const msg = e.message || '';
            if (msg.includes('视觉模型')) {
                setStatus(msg + ' — 请先在「模型设置」配置视觉模型', 'error');
            } else {
                setStatus(msg, 'error');
            }
        }
    }

    function formatScoreBadge(grade, total) {
        if (!grade) return '<span class="badge badge-light">未评分</span>';
        const cls = `grade-${String(grade).toLowerCase()}`;
        const scoreNum = total != null && Number.isFinite(Number(total)) ? Math.round(Number(total)) : null;
        const label = scoreNum != null ? `${grade} ${scoreNum}分` : grade;
        return `<span class="badge grade-badge ${cls}" title="规则评分">${label}</span>`;
    }

    function renderScorePanel(article) {
        const breakdown = article.score_breakdown;
        if (!breakdown) {
            return '<p class="text-muted small">暂无评分，可点击下方按钮生成。</p>';
        }
        const dims = (breakdown.dimensions || [])
            .map((d) => `<li class="small">${escapeHtml(d.label)} ${d.score}/10 · ${escapeHtml((d.signals || []).join('、'))}</li>`)
            .join('');
        const llm = breakdown.llm || {};
        const rule = breakdown.rule || {};
        const final = breakdown.final || {};
        const ruleNote =
            rule.grade && final.grade && rule.grade !== final.grade
                ? `<p class="small text-muted">规则初评 ${rule.grade}（${rule.total}）→ LLM 修正为 ${final.grade}（${final.total}）</p>`
                : '';
        const adjustReason = llm.grade_adjust_reason
            ? `<p class="small text-muted">修正说明：${escapeHtml(llm.grade_adjust_reason)}</p>`
            : '';
        const llmBlock = llm.comment ? `
            <div class="score-llm mt-2">
                <strong>AI 评语</strong>
                <p class="small mb-1">${escapeHtml(llm.comment)}</p>
                ${llm.flash_verdict ? `<p class="small text-muted">判断：${escapeHtml(llm.flash_verdict)}</p>` : ''}
                ${llm.headline_angle ? `<p class="small text-muted">角度：${escapeHtml(llm.headline_angle)}</p>` : ''}
                ${llm.why_now ? `<p class="small text-muted">时机：${escapeHtml(llm.why_now)}</p>` : ''}
                ${llm.risks ? `<p class="small text-muted">风险：${escapeHtml(llm.risks)}</p>` : ''}
                ${adjustReason}
            </div>` : (article.score_comment ? `<p class="small">${escapeHtml(article.score_comment)}</p>` : '');
        return `
            <div class="score-panel mb-3">
                <div class="d-flex align-items-center gap-2 mb-2">
                    ${formatScoreBadge(article.score_grade, article.score_total)}
                    <span class="small text-muted">${breakdown.recommendation || ''} · ${article.score_total != null ? Math.round(article.score_total) : '—'} 分</span>
                </div>
                ${ruleNote}
                <ul class="mb-1 pl-3">${dims}</ul>
                ${llmBlock}
            </div>`;
    }

    async function loadArticles() {
        const sourceId = $('sourceSelect').value;
        const q = $('searchInput').value.trim();
        const sort = $('sortSelect')?.value || 'published_desc';
        const params = new URLSearchParams({ limit: '50' });
        if (sourceId) params.set('source_id', sourceId);
        if (q) params.set('q', q);
        if (sort === 'score_desc') params.set('sort', 'score_desc');
        const data = await api(`/api/ingestion/articles?${params}`);
        $('articleCount').textContent = data.total;
        const list = $('articleList');
        const showSource = !sourceId;
        if (!data.articles.length) {
            list.innerHTML = '<p class="text-muted">暂无文章。请点击「立即抓取」并确保 ingestion worker 正在运行。</p>';
            return;
        }
        list.innerHTML = data.articles.map((a) => {
            const thumbSrc = a.cover_local_path || null;
            const thumb = thumbSrc
                ? `<img class="thumb" src="${thumbSrc}" alt="">`
                : '<div class="thumb thumb-placeholder"></div>';
            const pub = a.published_at ? new Date(a.published_at).toLocaleString() : '—';
            const views = formatViewCount(a.view_count);
            const storyBadge = a.story_id
                ? `<span class="badge badge-info ml-1" title="同题 story">story</span>`
                : '';
            const gradeBadge = formatScoreBadge(a.score_grade, a.score_total);
            const sourceBadge = showSource
                ? `<span class="badge badge-secondary mr-1">${escapeHtml(sourceNameMap[a.source_id] || a.source_id)}</span>`
                : '';
            const prepBadge = a.video_prep_ready
                ? '<span class="badge badge-success ml-1" title="主页素材已就绪">主页就绪</span>'
                : '';
            const videoBadge = a.has_generated_video
                ? '<span class="badge badge-primary ml-1" title="已自动生成视频">已出片</span>'
                : (a.media_pipeline_status === 'running' || a.media_pipeline_status === 'pending'
                    ? '<span class="badge badge-warning ml-1">出片中</span>' : '');
            return `
            <div class="article-item ${selectedArticleId === a.id ? 'selected' : ''}"
                 data-id="${a.id}">
                ${thumb}
                <div class="flex-grow-1">
                    <div class="font-weight-bold">${escapeHtml(a.title)}</div>
                    <div class="small text-muted">${pub}${views ? ` · ${views}` : ''} · ${escapeHtml(a.theme || '')} · 图 ${a.image_count}${a.story_id ? ' · 同题' : ''}</div>
                    ${sourceBadge}${gradeBadge}${prepBadge}${videoBadge}<span class="badge badge-${a.status === 'selected' ? 'success' : 'light'}">${a.status}</span>${storyBadge}
                </div>
            </div>`;
        }).join('');
        list.querySelectorAll('.article-item').forEach((el) => {
            el.addEventListener('click', () => selectArticle(el.dataset.id));
        });
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[c]);
    }

    function mediaUrl(path) {
        const p = String(path || '').trim();
        if (!p) return '';
        return p.startsWith('/') ? p : `/${p}`;
    }

    function joinDraftLines(...parts) {
        return parts.map((p) => String(p || '').trim()).filter(Boolean).join('\n');
    }

    function draftFieldText(draft, field) {
        if (!draft) return '';
        switch (field) {
            case 'title':
                return joinDraftLines(draft.main_line1, draft.main_line2);
            case 'subtitle':
                return joinDraftLines(draft.sub_title, draft.sub_title2);
            case 'summary':
                return String(draft.summary || '').trim();
            case 'tags':
                return String(draft.tags || '').trim();
            case 'all':
                return [
                    joinDraftLines(draft.main_line1, draft.main_line2),
                    joinDraftLines(draft.sub_title, draft.sub_title2),
                    String(draft.summary || '').trim(),
                    String(draft.tags || '').trim(),
                ].filter(Boolean).join('\n\n');
            default:
                return '';
        }
    }

    function copyTextToClipboard(text, label) {
        if (!text) {
            setStatus(`${label}为空，无法复制`, 'error');
            return;
        }
        const onOk = () => setStatus(`已复制${label}`, 'ok');
        const onFail = () => {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            try {
                document.execCommand('copy');
                onOk();
            } catch (e) {
                setStatus(`复制失败: ${e.message}`, 'error');
            }
            document.body.removeChild(ta);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(onOk).catch(onFail);
        } else {
            onFail();
        }
    }

    function renderDraftCopyButtons(article) {
        if (!article.generated_video_path || !article.video_draft) return '';
        return `<div class="draft-copy-actions mt-2 d-flex flex-wrap gap-2">
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="title">复制标题</button>
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="subtitle">复制副标题</button>
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="summary">复制摘要</button>
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="tags">复制标签</button>
            <button type="button" class="btn btn-sm btn-outline-primary copy-draft-btn" data-copy-field="all">一键复制全部</button>
        </div>`;
    }

    function wireDraftCopyButtons(draft) {
        const labels = {
            title: '标题',
            subtitle: '副标题',
            summary: '摘要',
            tags: '标签',
            all: '标题、副标题、摘要、标签',
        };
        document.querySelectorAll('.copy-draft-btn').forEach((btn) => {
            btn.onclick = () => {
                const field = btn.dataset.copyField;
                copyTextToClipboard(draftFieldText(draft, field), labels[field] || '内容');
            };
        });
    }

    function renderVideoDraftPanel(article) {
        const draft = article.video_draft;
        if (!draft && !article.generated_video_path) return '';
        const lines = [];
        if (draft) {
            if (draft.main_line1) lines.push(`<div><strong>主标题</strong>：${escapeHtml(draft.main_line1)}${draft.main_line2 ? ' / ' + escapeHtml(draft.main_line2) : ''}</div>`);
            if (draft.sub_title) lines.push(`<div><strong>副标题</strong>：${escapeHtml(draft.sub_title)}${draft.sub_title2 ? ' / ' + escapeHtml(draft.sub_title2) : ''}</div>`);
            if (draft.summary) lines.push(`<div><strong>摘要</strong>：${escapeHtml(draft.summary)}</div>`);
            if (draft.tags) lines.push(`<div><strong>标签</strong>：${escapeHtml(draft.tags)}</div>`);
        }
        const status = article.media_pipeline_status || '';
        const statusBadge = status === 'succeeded' ? '<span class="badge badge-success">已出片</span>'
            : status === 'running' ? '<span class="badge badge-warning">出片中</span>'
            : status === 'pending' ? '<span class="badge badge-info">排队中</span>'
            : status === 'failed' ? '<span class="badge badge-danger">出片失败</span>' : '';
        const videoBlock = article.generated_video_path
            ? `<div class="mt-2"><video src="${mediaUrl(article.generated_video_path)}" controls style="max-width:100%;max-height:320px;border-radius:8px;"></video>
               <div class="mt-1"><a class="btn btn-sm btn-outline-primary" href="${mediaUrl(article.generated_video_path)}" download>下载视频</a></div></div>`
            : '';
        const coverBlock = article.generated_cover_path
            ? `<div class="mt-2">
                <div class="small text-muted mb-1">3:4 发布封面</div>
                <img src="${mediaUrl(article.generated_cover_path)}" alt="发布封面"
                     style="max-width:100%;max-height:240px;border-radius:8px;border:1px solid #e2e8f0;" />
                <div class="mt-1">
                    <a class="btn btn-sm btn-outline-secondary" href="${mediaUrl(article.generated_cover_path)}" download>下载封面</a>
                </div>
               </div>`
            : '';
        const bgm = article.selected_bgm_path ? `<div class="small text-muted">BGM: ${escapeHtml(article.selected_bgm_path)}</div>` : '';
        return `<div class="video-draft-panel mb-3 p-2 border rounded">
            <div class="d-flex align-items-center gap-2 mb-2"><strong>AI 成片素材</strong>${statusBadge}</div>
            ${lines.join('')}
            ${renderDraftCopyButtons(article)}
            ${bgm}
            ${coverBlock}
            ${videoBlock}
            <div class="mt-2">
                <button class="btn btn-sm btn-outline-secondary" id="retryMediaBtn">重新出片</button>
                ${article.generated_video_path ? '<button class="btn btn-sm btn-success ml-1" id="publishVideoBtn" type="button">一键发布</button>' : ''}
                <a class="btn btn-sm btn-primary ml-1" href="/?from=ingestion&article_id=${encodeURIComponent(article.id)}">打开主页编辑</a>
            </div>
        </div>`;
    }

    async function selectArticle(id) {
        selectedArticleId = id;
        selectedPrepare = null;
        $('useOnHomeBtn').disabled = false;
        await loadArticles();
        const [article, related] = await Promise.all([
            api(`/api/ingestion/articles/${id}`),
            api(`/api/ingestion/articles/${id}/related`).catch(() => ({ articles: [], assets: [] })),
        ]);
        const articleImgs = (article.images || []).filter((img) => img.local_path && img.download_status === 'ok');
        const relatedImgs = (related.assets || [])
            .filter((asset) => asset.source_article_id !== id && asset.local_path)
            .map((asset) => ({
                local_path: asset.local_path,
                relevance_grade: asset.relevance_grade,
                relevance_score: asset.relevance_score,
                relevance_rank: asset.relevance_rank,
                sort_order: asset.sort_order || 0,
                verdict: asset.verdict,
                caption: asset.caption,
            }));
        const failedCount = (article.images || []).filter((img) => img.download_status !== 'ok').length;
        const relatedArticles = (related.articles || [])
            .map((a) => `<li class="small">${escapeHtml(a.title)} <span class="text-muted">(${a.role})</span></li>`)
            .join('');
        const views = formatViewCount(article.view_count);
        const prepNote = article.generated_video_path
            ? `<p class="small text-success mb-2">✓ 已自动生成视频 · ${article.generated_video_at ? new Date(article.generated_video_at).toLocaleString() : ''}</p>`
            : article.video_prep_at
            ? `<p class="small text-success mb-2">✓ 主页素材已就绪 · ${new Date(article.video_prep_at).toLocaleString()}</p>`
            : (article.media_pipeline_status === 'pending' || article.media_pipeline_status === 'running'
                ? '<p class="small text-warning mb-2">媒体流水线处理中（配图/文案/出片）…</p>'
                : (article.score_grade === 'S' || (article.score_total != null && article.score_total >= 80)
                    ? '<p class="small text-muted mb-2">高分文章将自动排队出片（需 worker 运行 + API Key）</p>'
                    : ''));
        $('articleDetail').innerHTML = `
            <h5>${escapeHtml(article.title)}</h5>
            <p class="small text-muted">${views || '浏览量未知'} · ${article.published_at ? new Date(article.published_at).toLocaleString() : '—'}</p>
            ${prepNote}
            ${renderVideoDraftPanel(article)}
            <p class="small"><a href="${article.canonical_url}" target="_blank">${article.canonical_url}</a></p>
            <p>${escapeHtml(article.summary || '')}</p>
            ${renderScorePanel(article)}
            ${renderImageGrid(articleImgs, { title: '本文图片', emptyText: '无本地图片' })}
            ${failedCount ? `<div class="small text-muted mb-2">另有 ${failedCount} 张图片未下载到本地（常见原因：微信 CDN 防盗链占位图、链接过期）。微信图片会自动尝试 mp.weixin.qq.com Referer；仍失败可运行 <code>python scripts/retry_failed_ingestion_images.py ${escapeHtml(article.source_id)}</code> 重试</div>` : ''}
            ${related.articles && related.articles.length ? `
            <div class="mb-2"><strong>同题相关 (${related.story_id || ''})</strong>
                <ul class="mb-1 pl-3">${relatedArticles}</ul>
            </div>` : ''}
            ${relatedImgs.length ? renderImageGrid(relatedImgs, { title: '同题可合并图片', emptyText: '' }) : ''}
            <div style="white-space:pre-wrap;font-size:14px;max-height:240px;overflow:auto;border:1px solid #eee;padding:10px;border-radius:8px;">${escapeHtml((article.content_text || '').slice(0, 3000))}</div>
            <div class="mt-3">
                <button class="btn btn-sm btn-outline-secondary" id="scoreRuleBtn">规则评分</button>
                <button class="btn btn-sm btn-outline-primary" id="scoreLlmBtn">规则+AI评语</button>
                <button class="btn btn-sm btn-outline-info" id="scoreImagesBtn">评估配图</button>
                <button class="btn btn-sm btn-outline-primary" id="markSelectBtn">标记已选</button>
                <button class="btn btn-sm btn-primary" id="prepareBtn">准备主页数据（含同题图）</button>
            </div>
            <pre class="meta mt-2" id="prepareMeta" style="display:none"></pre>
        `;
        $('markSelectBtn').onclick = async () => {
            await api(`/api/ingestion/articles/${id}/select`, { method: 'POST' });
            setStatus('已标记为 selected', 'ok');
            loadArticles();
        };
        $('scoreRuleBtn').onclick = () => runScore(id, false);
        $('scoreLlmBtn').onclick = () => runScore(id, true);
        $('scoreImagesBtn').onclick = () => runScoreImages(id);
        $('prepareBtn').onclick = () => prepareForHome(id);
        const retryBtn = document.getElementById('retryMediaBtn');
        if (retryBtn) {
            retryBtn.onclick = async () => {
                setStatus('正在重新排队出片…', 'muted');
                try {
                    await api(`/api/ingestion/articles/${id}/media-pipeline/retry`, { method: 'POST' });
                    setStatus('已提交出片任务', 'ok');
                    selectArticle(id);
                } catch (e) {
                    setStatus(e.message, 'error');
                }
            };
        }
        if (article.generated_video_path && article.video_draft) {
            wireDraftCopyButtons(article.video_draft);
        }
        const publishBtn = document.getElementById('publishVideoBtn');
        if (publishBtn && article.generated_video_path) {
            publishBtn.onclick = () => {
                if (typeof window.openPublishModal !== 'function') {
                    setStatus('发布模块未加载，请刷新页面', 'error');
                    return;
                }
                window.openPublishModal({
                    videoPath: article.generated_video_path,
                    coverPath: article.generated_cover_path || null,
                    draft: article.video_draft || {},
                    sourceType: 'ingestion',
                    sourceId: article.id,
                });
            };
        }
    }

    async function runScore(id, useLlm) {
        setStatus(useLlm ? '正在生成规则分与 AI 评语…' : '正在生成规则评分…', 'muted');
        try {
            const res = await api(`/api/ingestion/articles/${id}/score`, {
                method: 'POST',
                body: JSON.stringify({ use_llm: useLlm }),
            });
            setStatus(
                `评分完成：${res.score_grade} 级 ${Math.round(res.score_total)} 分` +
                    (res.rule_grade && res.rule_grade !== res.score_grade
                        ? `（规则 ${res.rule_grade}→LLM 修正）`
                        : '') +
                    (res.llm_used ? '（含 AI 评语）' : ''),
                'ok'
            );
            selectArticle(id);
            loadArticles();
        } catch (e) {
            setStatus(e.message, 'error');
        }
    }

    async function scoreBatch() {
        const sourceId = $('sourceSelect').value;
        setStatus('批量规则评分中…', 'muted');
        try {
            const res = await api('/api/ingestion/articles/score-batch', {
                method: 'POST',
                body: JSON.stringify({ source_id: sourceId || null, use_llm: false, limit: 100 }),
            });
            setStatus(`已评分 ${res.count} 篇`, 'ok');
            loadArticles();
        } catch (e) {
            setStatus(e.message, 'error');
        }
    }

    async function prepareForHome(id) {
        const data = await api(`/api/ingestion/articles/${id}/prepare-video?auto_select=true&sort_by_relevance=true`, { method: 'POST' });
        selectedPrepare = data;
        $('useOnHomeBtn').disabled = false;
        const meta = $('prepareMeta');
        if (meta) {
            meta.style.display = 'block';
            meta.textContent = JSON.stringify(data.metadata, null, 2);
        }
        const autoN = (data.auto_selected_images || []).length;
        setStatus(
            autoN
                ? `已生成桥接 metadata，已自动勾选 ${autoN} 张 A/B 级配图`
                : '已生成桥接 metadata，可点击「用于主页生成」',
            'ok'
        );
    }

    async function runSource() {
        const sourceId = $('sourceSelect').value;
        if (!sourceId) {
            setStatus('正在为全部已启用数据源提交抓取任务…', 'muted');
            try {
                const res = await api('/api/ingestion/sources/run-all', { method: 'POST' });
                const jobIds = (res.jobs || []).map((j) => j.job_id).filter(Boolean);
                setStatus(res.message || `已提交 ${jobIds.length} 个任务`, 'ok');
                if (jobIds.length) pollJobs(jobIds);
            } catch (e) {
                setStatus(e.message, 'error');
            }
            return;
        }
        const res = await api(`/api/ingestion/sources/${sourceId}/run`, { method: 'POST' });
        const hint = res.message || '已提交';
        setStatus(`${hint} (job_id=${res.job_id}, status=${res.status || 'unknown'})`);
        pollJobs([res.job_id]);
    }

    async function pollJobs(jobIds) {
        const pending = new Set(jobIds.filter(Boolean));
        if (!pending.size) return;

        const maxRounds = Math.max(60, pending.size * 30);
        for (let i = 0; i < maxRounds; i++) {
            await new Promise((r) => setTimeout(r, 2000));
            const results = await Promise.all(
                [...pending].map((id) => api(`/api/ingestion/jobs/${id}`).catch(() => ({ id, status: 'unknown' })))
            );
            let running = 0;
            let failed = 0;
            results.forEach((job) => {
                if (job.status === 'succeeded' || job.status === 'failed') {
                    pending.delete(job.id);
                    if (job.status === 'failed') failed += 1;
                } else if (job.status === 'running') {
                    running += 1;
                }
            });
            const done = jobIds.length - pending.size;
            if (pending.size === 0) {
                if (failed) {
                    setStatus(`抓取结束：${done - failed}/${jobIds.length} 成功，${failed} 个失败`, 'error');
                } else {
                    setStatus(jobIds.length > 1 ? `全部 ${jobIds.length} 个数据源抓取完成` : '抓取完成', 'ok');
                }
                loadArticles();
                loadSources();
                return;
            }
            const suffix = jobIds.length > 1 ? ` · 进行中 ${running} · 待完成 ${pending.size}` : '';
            setStatus(`抓取进度 ${done}/${jobIds.length}${suffix} (${i + 1}/${maxRounds})`, 'muted');
        }
        setStatus('部分任务仍在执行，请稍后刷新列表', 'muted');
    }

    function useOnHome() {
        const articleId = selectedArticleId;
        if (!articleId) {
            setStatus('请先选择一篇文章', 'error');
            return;
        }
        // 主页通过 article_id 调 API 拉取正文与图片，避免 sessionStorage 缓存/容量问题
        window.location.href = `/?from=ingestion&article_id=${encodeURIComponent(articleId)}`;
    }

    $('refreshBtn').addEventListener('click', loadArticles);
    $('runSourceBtn').addEventListener('click', runSource);
    $('scoreBatchBtn').addEventListener('click', scoreBatch);
    $('useOnHomeBtn').addEventListener('click', useOnHome);
    if ($('sourceSelect')) {
        $('sourceSelect').addEventListener('change', () => {
            updateSourceToolbar();
            loadArticles().catch((e) => setStatus(e.message, 'error'));
        });
    }
    if ($('sortSelect')) $('sortSelect').addEventListener('change', loadArticles);
    $('searchInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') loadArticles();
    });

    loadSources().then(() => Promise.all([loadArticles(), loadIngestionWorkerHealth()])).catch((e) => setStatus(e.message, 'error'));

    async function loadIngestionWorkerHealth() {
        try {
            const data = await api('/api/ingestion/health');
            const banner = $('ingestionWorkerBanner');
            if (!banner) return;
            banner.style.display = data.worker_reachable ? 'none' : 'block';
            if (!data.worker_reachable && data.worker_mode === 'embedded') {
                banner.textContent = '⚠️ 内嵌爬取 Worker 未就绪，请重启 web_server 或查看日志。';
            }
        } catch (_) {
            /* ignore */
        }
    }
})();
