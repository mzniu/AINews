(function () {
    let selectedArticleId = null;
    let selectedPrepare = null;
    let sourcesCache = [];
    let sourceNameMap = {};
    let viewMode = 'list';
    const expandedStories = new Set();
    const storyCache = {};
    let storiesData = [];
    let storyTotal = 0;
    let storyOffset = 0;
    const STORY_PAGE = 50;
    let articlesData = [];
    let articleTotal = 0;
    let articleOffset = 0;
    const ARTICLE_PAGE = 50;
    let detailImageCache = [];

    const IMAGE_DIMENSION_LABELS = {
        topic_relevance: '主题相关度',
        info_value: '信息价值',
        visual_quality: '画质可用性',
        flash_fit: '短视频主画面',
        cover_fit: '封面适配度',
        figure_prominence: '人物突出度',
        compliance: '合规安全',
    };
    const IMAGE_REASON_LABELS = {
        watermark: '水印/二维码',
        logo_only: '纯 logo',
        ad_banner: '广告横幅',
        off_topic: '与主题无关',
        duplicate: '近重复图',
        extreme_aspect: '极端比例',
        portrait: '竖图',
        chapter_title: '章节标题图',
        transition_decor: '过渡装饰图',
        landscape: '横图',
        animated: '动图',
    };

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

    let renderTemplateCache = null;
    async function fillRetryTemplateSelect() {
        const select = document.getElementById('retryTemplateSelect');
        if (!select) return;
        try {
            if (!renderTemplateCache) {
                renderTemplateCache = await api('/api/ingestion/render-templates');
            }
            const data = renderTemplateCache;
            const current = select.value;
            select.innerHTML = '<option value="">成片模板（系统默认）</option>';
            (data.templates || []).forEach((item) => {
                const opt = document.createElement('option');
                opt.value = item.id;
                const mark = item.id === data.default_template_id ? '（默认）' : '';
                opt.textContent = `${item.label || item.id}${mark}`;
                select.appendChild(opt);
            });
            if (current) select.value = current;
            else if (data.default_template_id) select.value = data.default_template_id;
        } catch (err) {
            console.warn('加载成片模板失败', err);
        }
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
            setStatus(`调度: ${s.schedule_cron} | 上次运行: ${s.last_run_at ? formatBeijingDateTime(s.last_run_at) : '—'}`);
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
        const start = detailImageCache.length;
        detailImageCache.push(...sorted);
        const cards = sorted.map((img, offset) => {
        const index = start + offset;
        const badge = formatImageGradeBadge(img.relevance_grade, img.relevance_score);
        const cover = img.cover_fit_score != null ? `<span class="badge badge-light ml-1" title="封面适配">封面 ${Math.round(img.cover_fit_score)}</span>` : '';
        const flash = img.flash_fit_score != null ? `<span class="badge badge-primary ml-1" title="主画面适配">主画面 ${Math.round(img.flash_fit_score)}</span>` : '';
        const figure = img.figure_prominence_score != null ? `<span class="badge badge-light ml-1" title="人物突出">人物 ${Math.round(img.figure_prominence_score)}</span>` : '';
        const animated = img.is_animated ? '<span class="badge badge-warning ml-1" title="动图优先">动图</span>' : '';
        const orient = img.orientation === 'landscape' ? '<span class="badge badge-info ml-1">横图</span>' : (img.orientation === 'portrait' ? '<span class="badge badge-secondary ml-1">竖图</span>' : '');
        const tip = img.content_description || img.verdict || img.caption || '点击查看大图';
        const desc = img.content_description || img.caption || '';
        return `<div class="img-score-card img-score-card-clickable mr-2 mb-2" role="button" tabindex="0"
                    data-image-index="${index}" title="${escapeHtml(tip)}">
                <img src="${img.local_path}" class="thumb" alt="">
                <div class="img-score-badges">${badge}${flash}${cover}${figure}${animated}${orient}</div>
                ${desc ? `<div class="img-score-desc">${escapeHtml(desc)}</div>` : ''}
            </div>`;
        }).join('');
        return `<div class="mb-2"><strong>${title}</strong><div class="d-flex flex-wrap">${cards}</div></div>`;
    }

    function formatDimScore(value) {
        if (value == null || value === '') return '—';
        const n = Number(value);
        return Number.isFinite(n) ? (Number.isInteger(n) ? String(n) : n.toFixed(1)) : String(value);
    }

    function renderImageEvalBody(img) {
        if (!img) return '<p class="text-muted">暂无图片</p>';
        const breakdown = img.score_breakdown || {};
        const dims = breakdown.dimensions || {};
        const dimRows = Object.keys(IMAGE_DIMENSION_LABELS).map((key) => {
            const dim = dims[key] || {};
            const score = dim.score != null ? dim.score : img[`${key}_score`];
            const signals = Array.isArray(dim.signals) ? dim.signals.filter(Boolean).join('、') : '';
            return `<li><span>${escapeHtml(IMAGE_DIMENSION_LABELS[key])}</span><strong>${formatDimScore(score)}</strong>${signals ? `<p>${escapeHtml(signals)}</p>` : ''}</li>`;
        }).join('');
        const adjustments = []
            .concat(breakdown.bonuses || [])
            .concat(breakdown.penalties || []);
        const adjRows = adjustments.map((item) => {
            const pts = Number(item.points || 0);
            const sign = pts >= 0 ? '+' : '';
            const label = IMAGE_REASON_LABELS[item.reason] || item.reason || '调整';
            return `<li class="${pts >= 0 ? 'bonus' : 'penalty'}"><span>${escapeHtml(label)}</span><strong>${sign}${formatDimScore(pts)}</strong></li>`;
        }).join('');
        const size = (img.width && img.height)
            ? `${img.width} × ${img.height}`
            : (breakdown.width && breakdown.height ? `${breakdown.width} × ${breakdown.height}` : '');
        const flags = [
            img.is_animated || breakdown.is_animated ? '动图' : '',
            img.orientation === 'landscape' ? '横图' : (img.orientation === 'portrait' ? '竖图' : ''),
            size,
        ].filter(Boolean).join(' · ');
        const hasScore = img.relevance_grade || img.relevance_score != null;
        return `
            <div class="image-preview-score-head">
                ${hasScore ? formatImageGradeBadge(img.relevance_grade, img.relevance_score) : '<span class="badge badge-light">未评估</span>'}
                ${img.relevance_rank ? `<span class="small text-muted">相关度排名 ${img.relevance_rank}</span>` : ''}
            </div>
            ${flags ? `<p class="image-preview-flags">${escapeHtml(flags)}</p>` : ''}
            ${img.verdict ? `<p class="image-preview-verdict">${escapeHtml(img.verdict)}</p>` : ''}
            ${img.content_description || img.caption ? `<p class="image-preview-desc">${escapeHtml(img.content_description || img.caption)}</p>` : ''}
            ${hasScore ? `<h4>维度得分</h4><ul class="image-preview-dims">${dimRows}</ul>` : '<p class="text-muted">尚未评估配图，可在详情页点击「评估配图」。</p>'}
            ${adjRows ? `<h4>加减分</h4><ul class="image-preview-dims">${adjRows}</ul>` : ''}
        `;
    }

    function closeImagePreview() {
        const modal = $('imagePreviewModal');
        if (!modal) return;
        modal.hidden = true;
        const photo = $('imagePreviewPhoto');
        if (photo) photo.removeAttribute('src');
    }

    function openImagePreview(index) {
        const img = detailImageCache[Number(index)];
        const modal = $('imagePreviewModal');
        if (!img || !modal) return;
        const photo = $('imagePreviewPhoto');
        if (photo) {
            photo.src = img.local_path;
            photo.alt = img.content_description || img.caption || '配图大图';
        }
        const body = $('imagePreviewBody');
        if (body) body.innerHTML = renderImageEvalBody(img);
        modal.hidden = false;
    }

    function bindImagePreviewEvents() {
        const detail = $('articleDetail');
        if (detail && !detail.dataset.imagePreviewBound) {
            detail.dataset.imagePreviewBound = '1';
            detail.addEventListener('click', (event) => {
                const card = event.target.closest('.img-score-card-clickable');
                if (!card || !detail.contains(card)) return;
                openImagePreview(card.dataset.imageIndex);
            });
            detail.addEventListener('keydown', (event) => {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                const card = event.target.closest('.img-score-card-clickable');
                if (!card) return;
                event.preventDefault();
                openImagePreview(card.dataset.imageIndex);
            });
        }
        const modal = $('imagePreviewModal');
        if (modal && !modal.dataset.bound) {
            modal.dataset.bound = '1';
            modal.addEventListener('click', (event) => {
                if (event.target.closest('[data-close-image-preview]')) closeImagePreview();
            });
        }
        if (!window.__imagePreviewEscBound) {
            window.__imagePreviewEscBound = true;
            document.addEventListener('keydown', (event) => {
                if (event.key === 'Escape') closeImagePreview();
            });
        }
    }

    async function runScoreImages(id) {
        setStatus('正在评估配图相关度（视觉模型）…', 'muted');
        try {
            const res = await api(`/api/ingestion/articles/${id}/score-images`, {
                method: 'POST',
                body: JSON.stringify({ force: true, include_story_images: true }),
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

    const PUBLISH_TIER_LABELS = {
        viral_priority: '传播优先',
        standard: '标准队列',
        skip: '建议跳过',
    };

    function getDualScoreInfo(article) {
        const breakdown = article?.score_breakdown || {};
        const final = breakdown.final || {};
        const industry = breakdown.industry || {};
        const viral = breakdown.viral || {};
        const industryGrade = final.industry_grade || breakdown.grade || article?.score_grade;
        const industryTotal = final.industry_total ?? breakdown.total ?? article?.score_total;
        const viralGrade = final.viral_grade || viral.grade || article?.viral_score_grade;
        const viralTotal = final.viral_total ?? viral.total ?? article?.viral_score_total;
        const publishTier = final.publish_tier || article?.publish_tier;
        const hasViral = Boolean(viralGrade || viral.total != null || article?.viral_score_grade);
        return {
            industryGrade,
            industryTotal,
            viralGrade,
            viralTotal,
            publishTier,
            hasViral,
            industry,
            viral,
            final,
            breakdown,
        };
    }

    function formatGradeBadge(grade, total, options = {}) {
        const kind = options.kind || 'industry';
        if (!grade) return '<span class="badge badge-light">未评分</span>';
        const cls = `grade-${String(grade).toLowerCase()}`;
        const scoreNum = total != null && Number.isFinite(Number(total)) ? Math.round(Number(total)) : null;
        const label = scoreNum != null ? `${grade} ${scoreNum}` : grade;
        const kindCls = kind === 'viral' ? ' grade-badge-viral' : ' grade-badge-industry';
        const title = options.title || (kind === 'viral' ? '传播潜力' : '行业质量');
        return `<span class="badge grade-badge${kindCls} ${cls}" title="${escapeHtml(title)}">${escapeHtml(label)}</span>`;
    }

    function formatScoreBadge(grade, total) {
        return formatGradeBadge(grade, total, { kind: 'industry', title: '行业质量' });
    }

    function formatDualScoreBadges(article) {
        const info = getDualScoreInfo(article);
        const parts = [formatGradeBadge(info.industryGrade, info.industryTotal, { kind: 'industry' })];
        if (info.hasViral) {
            parts.push(formatGradeBadge(info.viralGrade, info.viralTotal, { kind: 'viral' }));
        }
        if (info.publishTier) {
            parts.push(formatPublishTierBadge(info.publishTier));
        }
        return parts.join('');
    }

    function formatPublishTierBadge(tier) {
        if (!tier) return '';
        const label = PUBLISH_TIER_LABELS[tier] || tier;
        const cls = `publish-tier-${String(tier).replace(/_/g, '-')}`;
        return `<span class="badge publish-tier-badge ${cls}" title="发布分层（影子模式）">${escapeHtml(label)}</span>`;
    }

    function renderBonusList(items, emptyText) {
        if (!items || !items.length) return `<p class="small text-muted mb-0">${escapeHtml(emptyText)}</p>`;
        return `<ul class="score-bonus-list mb-0 pl-3">${items.map((item) => {
            const pts = Number(item.points);
            const sign = pts > 0 ? '+' : '';
            return `<li class="small">${escapeHtml(item.reason || '')} ${sign}${pts}</li>`;
        }).join('')}</ul>`;
    }

    function renderMotiveList(motives) {
        if (!motives || !motives.length) return '<p class="small text-muted mb-0">暂无动机信号</p>';
        return `<ul class="score-motive-list mb-0 pl-3">${motives.map((motive) => `
            <li class="small">
                <strong>${escapeHtml(motive.label || motive.key || '')}</strong>
                ${motive.score}/10
                ${(motive.signals || []).length ? ` · ${escapeHtml(motive.signals.slice(0, 4).join('、'))}` : ''}
            </li>`).join('')}</ul>`;
    }

    function renderHookGate(hookGate) {
        if (!hookGate) return '';
        const dims = [
            hookGate.subject ? '主体' : null,
            hookGate.number ? '数字' : null,
            hookGate.conflict ? '冲突' : null,
        ].filter(Boolean);
        const status = hookGate.passed ? '已通过' : '未通过';
        return `<p class="small text-muted mb-2">标题钩子检测：${status}${dims.length ? `（${dims.join(' / ')}）` : ''}</p>`;
    }

    function renderScorePanel(article) {
        const breakdown = article.score_breakdown;
        if (!breakdown) {
            return '<p class="text-muted small">暂无评分，可点击下方按钮生成。</p>';
        }
        const info = getDualScoreInfo(article);
        const industry = info.industry;
        const viral = info.viral;
        const dims = (breakdown.dimensions || industry.dimensions || [])
            .map((d) => `<li class="small">${escapeHtml(d.label)} ${d.score}/10 · ${escapeHtml((d.signals || []).join('、'))}</li>`)
            .join('');
        const industryBonuses = industry.bonuses || breakdown.bonuses || [];
        const industryPenalties = industry.penalties || breakdown.penalties || [];
        const llm = breakdown.llm || {};
        const rule = breakdown.rule || {};
        const final = info.final || {};
        const ruleNote =
            rule.grade && final.grade && rule.grade !== final.grade
                ? `<p class="small text-muted">规则初评 ${rule.grade}（${rule.total}）→ LLM 修正为 ${final.grade}（${final.total}）</p>`
                : '';
        const adjustReason = llm.grade_adjust_reason
            ? `<p class="small text-muted">修正说明：${escapeHtml(llm.grade_adjust_reason)}</p>`
            : '';
        const hotRadar = breakdown.hot_radar;
        const hotRadarBlock = hotRadar ? `
            <div class="score-hot-radar mt-2 small">
                <strong>热榜雷达</strong>
                <p class="mb-1">#${hotRadar.rank} · 热度 ${escapeHtml(hotRadar.heat_label || '—')} · ${escapeHtml(hotRadar.match_method === 'url' ? 'URL' : '标题')}命中</p>
                <p class="text-muted mb-1">${escapeHtml(hotRadar.hot_title || '')}</p>
                <a href="/hot-radar?article_id=${encodeURIComponent(article.id || '')}">查看热榜详情</a>
            </div>` : '';
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
        const industryRecommendation = industry.recommendation || breakdown.recommendation || '';
        const viralRecommendation = viral.recommendation || '';
        const viralBlock = info.hasViral ? `
            <div class="score-dimension-block mt-3">
                <div class="score-dimension-head">
                    <strong>传播潜力</strong>
                    <span class="small text-muted">${escapeHtml(viralRecommendation)}</span>
                </div>
                ${renderMotiveList(viral.motives)}
                ${renderHookGate(viral.hook_gate)}
                ${(viral.platform_fit || []).length ? `<p class="small text-muted mb-2">平台适配：${escapeHtml(viral.platform_fit.join('、'))}</p>` : ''}
                <div class="small mt-2"><strong>传播加成</strong></div>
                ${renderBonusList(viral.bonuses, '无额外传播加成')}
            </div>` : '';
        const penaltyBlock = industryPenalties.length
            ? `<div class="small mt-2 text-warning"><strong>扣分</strong>${renderBonusList(industryPenalties, '')}</div>`
            : '';
        return `
            <div class="score-panel mb-3">
                <div class="score-dual-summary mb-3">
                    <div class="score-dual-badges">
                        ${formatDualScoreBadges(article)}
                    </div>
                    <p class="small text-muted mb-0 mt-2">
                        行业 ${info.industryTotal != null ? Math.round(info.industryTotal) : '—'} 分
                        ${info.hasViral ? ` · 传播 ${info.viralTotal != null ? Math.round(info.viralTotal) : '—'} 分` : ''}
                        ${info.publishTier ? ` · ${escapeHtml(PUBLISH_TIER_LABELS[info.publishTier] || info.publishTier)}` : ''}
                    </p>
                </div>
                <div class="score-dimension-block">
                    <div class="score-dimension-head">
                        <strong>行业质量</strong>
                        <span class="small text-muted">${escapeHtml(industryRecommendation)}</span>
                    </div>
                    ${ruleNote}
                    <ul class="mb-1 pl-3">${dims}</ul>
                    ${industryBonuses.length ? `<div class="small mt-2"><strong>行业加成</strong>${renderBonusList(industryBonuses, '')}</div>` : ''}
                    ${penaltyBlock}
                </div>
                ${viralBlock}
                ${hotRadarBlock}
                ${llmBlock}
            </div>`;
    }

    function setListPanelTitle(text, countLabel) {
        const titleEl = $('listPanelTitleText');
        const countEl = $('articleCount');
        if (titleEl) titleEl.textContent = text;
        if (countEl) countEl.textContent = countLabel;
    }

    function refreshMainList() {
        if (viewMode === 'tree') {
            return loadStories(false);
        }
        return loadArticles();
    }

    function setViewMode(mode) {
        viewMode = mode === 'tree' ? 'tree' : 'list';
        $('viewListBtn')?.classList.toggle('active', viewMode === 'list');
        $('viewTreeBtn')?.classList.toggle('active', viewMode === 'tree');
        const treeFilter = $('treeFilterWrap');
        if (treeFilter) treeFilter.style.display = viewMode === 'tree' ? '' : 'none';
        const aiBtn = $('aiReviewBtn');
        if (aiBtn) aiBtn.style.display = viewMode === 'tree' ? '' : 'none';
        const aiPanel = $('aiReviewPanel');
        if (aiPanel && viewMode !== 'tree') aiPanel.style.display = 'none';
        const sortSel = $('sortSelect');
        if (sortSel) sortSel.disabled = viewMode === 'tree';
        refreshMainList().catch((e) => setStatus(e.message, 'error'));
    }

    function getFilteredStories() {
        const q = ($('searchInput')?.value || '').trim().toLowerCase();
        const multiOnly = $('treeMultiOnly')?.checked !== false;
        return storiesData.filter((story) => {
            if (multiOnly && (story.article_count || 0) < 2) return false;
            if (q && !(story.canonical_title || '').toLowerCase().includes(q)) return false;
            return true;
        });
    }

    function sortStoryArticles(articles, primaryId) {
        return [...articles].sort((a, b) => {
            const aPrimary = a.id === primaryId || a.role === 'primary';
            const bPrimary = b.id === primaryId || b.role === 'primary';
            if (aPrimary !== bPrimary) return aPrimary ? -1 : 1;
            return (b.score_total || 0) - (a.score_total || 0);
        });
    }

    function renderPrimaryArticleButton(articleId, primaryId) {
        if (!primaryId || primaryId === articleId) return '';
        return `<button type="button" class="btn btn-sm btn-outline-primary open-primary-btn"
            data-primary-id="${escapeHtml(primaryId)}" title="打开同题代表篇（用于发布出片）">代表篇</button>`;
    }

    function renderRecrawlArticleButton(articleId) {
        return `<button type="button" class="btn btn-sm btn-outline-secondary recrawl-article-btn"
            data-article-id="${escapeHtml(articleId)}" title="重新抓取正文与配图">重新抓取</button>`;
    }

    function wireRecrawlArticleButtons(root) {
        const scope = root || document;
        scope.querySelectorAll('.recrawl-article-btn').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.stopPropagation();
                recrawlArticle(btn.dataset.articleId, btn);
            });
        });
    }

    async function recrawlArticle(id, button) {
        if (!id) return;
        if (button) button.disabled = true;
        try {
            const res = await api(`/api/ingestion/articles/${id}/recrawl`, { method: 'POST' });
            setStatus(res.message || '已提交重新抓取', 'ok');
            if (selectedArticleId === id) {
                await selectArticle(id);
            }
            await refreshMainList();
        } catch (err) {
            setStatus(err.message, 'error');
        } finally {
            if (button) button.disabled = false;
        }
    }

    function wirePrimaryArticleButtons(root) {
        const scope = root || document;
        scope.querySelectorAll('.open-primary-btn').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.stopPropagation();
                const primaryId = btn.dataset.primaryId;
                if (primaryId) selectArticle(primaryId);
            });
        });
    }

    function renderTreeArticleRow(article, story) {
        const isPrimary = article.id === story.primary_article_id || article.role === 'primary';
        const thumbSrc = mediaUrl(article.generated_cover_path || article.cover_local_path || '');
        const thumb = thumbSrc
            ? `<img class="thumb" src="${thumbSrc}" alt="">`
            : '<div class="thumb thumb-placeholder"></div>';
        const pub = article.published_at ? formatBeijingDateTime(article.published_at) : '—';
        const views = formatViewCount(article.view_count);
        const roleBadge = isPrimary
            ? '<span class="badge badge-success ml-1">代表篇</span>'
            : `<span class="badge badge-light ml-1">${escapeHtml(article.role || 'related')}</span>`;
        const sim = article.similarity_score != null
            ? `<span class="badge badge-secondary ml-1" title="聚类相似度">${Math.round(article.similarity_score * 100)}%</span>`
            : '';
        const videoBadge = article.has_generated_video
            ? '<span class="badge badge-primary ml-1">已出片</span>'
            : (article.media_pipeline_status === 'running' || article.media_pipeline_status === 'pending'
                ? '<span class="badge badge-warning ml-1">出片中</span>' : '');
        const publishedBadge = article.has_published
            ? '<span class="badge badge-published ml-1" title="已发布到平台">已发布</span>'
            : '';
        const primaryBtn = renderPrimaryArticleButton(article.id, story.primary_article_id);
        const recrawlBtn = renderRecrawlArticleButton(article.id);
        return `
            <div class="story-tree-article ${selectedArticleId === article.id ? 'selected' : ''} ${isPrimary ? 'is-primary' : ''}"
                 data-id="${article.id}">
                ${thumb}
                <div class="flex-grow-1">
                    <div class="font-weight-bold">${escapeHtml(article.title)}</div>
                    <div class="small text-muted">
                        ${escapeHtml(sourceNameMap[article.source_id] || article.source_id)}
                        · ${pub}${views ? ` · ${views}` : ''} · 图 ${article.image_count || 0}
                    </div>
                    <div class="article-item-actions mt-1">
                        ${formatDualScoreBadges(article)}${roleBadge}${sim}${videoBadge}${publishedBadge}${recrawlBtn}${primaryBtn}
                    </div>
                </div>
            </div>`;
    }

    function renderStoryChildren(story) {
        const articles = storyCache[story.id];
        if (!articles) {
            return '<div class="story-loading small text-muted">加载成员文章…</div>';
        }
        if (!articles.length) {
            return '<div class="story-loading small text-muted">暂无成员文章</div>';
        }
        return sortStoryArticles(articles, story.primary_article_id)
            .map((article) => renderTreeArticleRow(article, story))
            .join('');
    }

    function wireStoryTreeEvents() {
        const list = $('articleList');
        if (!list) return;
        list.querySelectorAll('.story-tree-header').forEach((el) => {
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleStory(el.dataset.storyId).catch((err) => setStatus(err.message, 'error'));
            });
        });
        list.querySelectorAll('.story-tree-article').forEach((el) => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('.open-primary-btn, .recrawl-article-btn')) return;
                e.stopPropagation();
                selectArticle(el.dataset.id);
            });
        });
        wirePrimaryArticleButtons(list);
        wireRecrawlArticleButtons(list);
    }

    async function toggleStory(storyId) {
        if (!storyId) return;
        if (expandedStories.has(storyId)) {
            expandedStories.delete(storyId);
        } else {
            expandedStories.add(storyId);
            if (!storyCache[storyId]) {
                const data = await api(`/api/ingestion/stories/${storyId}/articles`);
                storyCache[storyId] = data.articles || [];
            }
        }
        renderStoryTree();
    }

    function renderStoryTree() {
        const list = $('articleList');
        const loadMore = $('storyLoadMore');
        const filtered = getFilteredStories();
        setListPanelTitle('同题聚类', `${filtered.length}/${storyTotal}`);

        if (!filtered.length) {
            list.innerHTML = '<p class="text-muted">暂无符合条件的 Story 聚类。可取消「仅多篇同题」或调整搜索词。</p>';
            if (loadMore) loadMore.style.display = 'none';
            return;
        }

        list.innerHTML = filtered.map((story) => {
            const expanded = expandedStories.has(story.id);
            const chevron = expanded ? '▼' : '▶';
            const multiBadge = (story.article_count || 0) > 1
                ? `<span class="badge badge-info">${story.article_count} 篇</span>`
                : `<span class="badge badge-light">${story.article_count || 1} 篇</span>`;
            const method = story.cluster_method ? `<span class="badge badge-secondary ml-1">${escapeHtml(story.cluster_method)}</span>` : '';
            const updated = story.updated_at ? formatBeijingDateTime(story.updated_at) : '—';
            return `
                <div class="story-tree-node" data-story-id="${story.id}">
                    <div class="story-tree-header ${expanded ? 'expanded' : ''}" data-story-id="${story.id}">
                        <span class="story-chevron" aria-hidden="true">${chevron}</span>
                        <div class="flex-grow-1">
                            <div class="font-weight-bold">${escapeHtml(story.canonical_title)}</div>
                            <div class="small text-muted">更新 ${updated}${story.cluster_score != null ? ` · 相似度 ${Math.round(story.cluster_score * 100)}%` : ''}</div>
                            <div class="mt-1">${multiBadge}${method}</div>
                        </div>
                    </div>
                    ${expanded ? `<div class="story-tree-children">${renderStoryChildren(story)}</div>` : ''}
                </div>`;
        }).join('');

        wireStoryTreeEvents();
        if (loadMore) {
            loadMore.style.display = storyOffset < storyTotal ? 'block' : 'none';
        }
        const articleLoadMore = $('articleLoadMore');
        if (articleLoadMore) articleLoadMore.style.display = 'none';
    }

    async function loadStories(append = false) {
        if (!append) {
            storyOffset = 0;
            storiesData = [];
        }
        const data = await api(`/api/ingestion/stories?limit=${STORY_PAGE}&offset=${storyOffset}`);
        const batch = data.stories || [];
        storiesData = append ? storiesData.concat(batch) : batch;
        storyTotal = data.total || storiesData.length;
        storyOffset = storiesData.length;
        renderStoryTree();
    }

    function renderAiReviewPanel(data) {
        const panel = $('aiReviewPanel');
        const content = $('aiReviewContent');
        if (!panel || !content) return;
        panel.style.display = 'block';

        if (data.skipped) {
            content.innerHTML = `<p>巡检已跳过：${escapeHtml(data.reason || 'disabled')}</p>`;
            return;
        }

        const mergeItems = (data.merge_suggestions || []).map((item) => `
            <div class="ai-suggestion">
                <div><strong>建议合并 Story</strong> · 置信度 ${Math.round((item.confidence || 0) * 100)}%</div>
                <div class="mt-1">${escapeHtml(item.title_a || '')}</div>
                <div class="text-muted">↕</div>
                <div>${escapeHtml(item.title_b || '')}</div>
                <div class="small text-muted mt-1">${escapeHtml(item.reason || '')}</div>
                <div class="ai-suggestion-actions">
                    <button type="button" class="btn btn-sm btn-primary apply-merge-btn"
                        data-article-ids='${JSON.stringify(item.article_ids || [])}'>应用合并</button>
                </div>
            </div>
        `).join('');

        const splitItems = (data.split_suggestions || []).map((item) => `
            <div class="ai-suggestion">
                <div><strong>建议移出 Story</strong> · 文章 ${escapeHtml(item.article_id || '')}</div>
                <div class="small text-muted mt-1">${escapeHtml(item.reason || '')}</div>
            </div>
        `).join('');

        const incoherent = (data.story_reviews || []).filter((row) => row.review && row.review.coherent === false);
        const incoherentItems = incoherent.map((row) => `
            <div class="ai-suggestion">
                <div><strong>聚类可能不合理</strong> · Story ${escapeHtml(row.story_id || '')}</div>
                <div class="small text-muted mt-1">${escapeHtml((row.review && row.review.summary) || row.review?.reason || '')}</div>
            </div>
        `).join('');

        content.innerHTML = `
            <p class="mb-2">已巡检 ${data.reviewed_stories || 0} 个 Story，发现 ${data.incoherent_stories || 0} 个可能不合理聚类，${(data.merge_suggestions || []).length} 条合并建议。</p>
            ${mergeItems ? `<div class="ai-review-section"><h4>合并建议</h4>${mergeItems}</div>` : ''}
            ${splitItems ? `<div class="ai-review-section"><h4>拆分建议</h4>${splitItems}</div>` : ''}
            ${incoherentItems ? `<div class="ai-review-section"><h4>不一致 Story</h4>${incoherentItems}</div>` : ''}
            ${!mergeItems && !splitItems && !incoherentItems ? '<p class="text-success">未发现需要处理的聚类问题。</p>' : ''}
        `;

        content.querySelectorAll('.apply-merge-btn').forEach((btn) => {
            btn.addEventListener('click', async () => {
                let articleIds = [];
                try {
                    articleIds = JSON.parse(btn.dataset.articleIds || '[]');
                } catch (_) {
                    setStatus('合并数据无效', 'error');
                    return;
                }
                if (!Array.isArray(articleIds) || articleIds.length < 2) {
                    setStatus('合并至少需要 2 篇文章', 'error');
                    return;
                }
                setStatus('正在应用 AI 合并建议…', 'muted');
                try {
                    await api('/api/ingestion/stories/merge', {
                        method: 'POST',
                        body: JSON.stringify({ article_ids: articleIds }),
                    });
                    setStatus('已应用合并建议', 'ok');
                    Object.keys(storyCache).forEach((key) => delete storyCache[key]);
                    await refreshMainList();
                    await runAiReview();
                } catch (err) {
                    setStatus(err.message, 'error');
                }
            });
        });
    }

    async function runAiReview() {
        setStatus('AI 正在巡检近期 Story 聚类（可能需要数十秒）…', 'muted');
        try {
            const data = await api('/api/ingestion/stories/ai-review?limit=30', { method: 'POST' });
            renderAiReviewPanel(data);
            setStatus(
                `AI 巡检完成：${data.reviewed_stories || 0} 个 Story，${(data.merge_suggestions || []).length} 条合并建议`,
                'ok'
            );
        } catch (err) {
            setStatus(err.message, 'error');
        }
    }

    function buildArticleItemHtml(a, showSource) {
        const thumbSrc = mediaUrl(a.generated_cover_path || a.cover_local_path || '');
        const thumb = thumbSrc
            ? `<img class="thumb" src="${thumbSrc}" alt="">`
            : '<div class="thumb thumb-placeholder"></div>';
        const pub = a.published_at ? formatBeijingDateTime(a.published_at) : '—';
        const views = formatViewCount(a.view_count);
        const storyBadge = a.story_id
            ? (a.is_story_primary
                ? `<span class="badge badge-info ml-1" title="同题代表篇">代表篇</span>`
                : `<span class="badge badge-info ml-1" title="同题 story">同题</span>`)
            : '';
        const primaryBtn = renderPrimaryArticleButton(a.id, a.story_primary_article_id);
        const recrawlBtn = renderRecrawlArticleButton(a.id);
        const gradeBadge = formatDualScoreBadges(a);
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
        const publishedBadge = a.has_published
            ? '<span class="badge badge-published ml-1" title="已发布到平台">已发布</span>'
            : '';
        return `
            <div class="article-item ${selectedArticleId === a.id ? 'selected' : ''}"
                 data-id="${a.id}">
                ${thumb}
                <div class="flex-grow-1">
                    <div class="font-weight-bold">${escapeHtml(a.title)}</div>
                    <div class="small text-muted">${pub}${views ? ` · ${views}` : ''} · ${escapeHtml(a.theme || '')} · 图 ${a.image_count}${a.story_id ? ' · 同题' : ''}</div>
                    <div class="article-item-actions mt-1">
                        ${sourceBadge}${gradeBadge}${prepBadge}${videoBadge}${publishedBadge}
                        <span class="badge badge-${a.status === 'selected' ? 'success' : 'light'}">${a.status}</span>
                        ${storyBadge}${recrawlBtn}${primaryBtn}
                    </div>
                </div>
            </div>`;
    }

    function wireArticleListEvents(list) {
        list.querySelectorAll('.article-item').forEach((el) => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('.open-primary-btn, .recrawl-article-btn')) return;
                selectArticle(el.dataset.id);
            });
        });
        wirePrimaryArticleButtons(list);
        wireRecrawlArticleButtons(list);
    }

    function renderArticleList() {
        const sourceId = $('sourceSelect').value;
        const showSource = !sourceId;
        setListPanelTitle('文章列表', `${articlesData.length}/${articleTotal}`);
        const list = $('articleList');
        const storyLoadMore = $('storyLoadMore');
        const articleLoadMore = $('articleLoadMore');
        if (storyLoadMore) storyLoadMore.style.display = 'none';
        if (!articlesData.length) {
            list.innerHTML = '<p class="text-muted">暂无文章。请点击「立即抓取」并确保 ingestion worker 正在运行。</p>';
            if (articleLoadMore) articleLoadMore.style.display = 'none';
            return;
        }
        list.innerHTML = articlesData.map((a) => buildArticleItemHtml(a, showSource)).join('');
        wireArticleListEvents(list);
        if (articleLoadMore) {
            articleLoadMore.style.display = articleOffset < articleTotal ? 'block' : 'none';
        }
    }

    async function loadArticles(append = false) {
        if (!append) {
            articleOffset = 0;
            articlesData = [];
        }
        const sourceId = $('sourceSelect').value;
        const q = $('searchInput').value.trim();
        const sort = $('sortSelect')?.value || 'published_desc';
        const grade = $('gradeSelect')?.value || '';
        const params = new URLSearchParams({
            limit: String(ARTICLE_PAGE),
            offset: String(articleOffset),
        });
        if (sourceId) params.set('source_id', sourceId);
        if (q) params.set('q', q);
        if (sort === 'score_desc') params.set('sort', 'score_desc');
        if (grade) params.set('min_grade', grade);
        const data = await api(`/api/ingestion/articles?${params}`);
        const batch = data.articles || [];
        articlesData = append ? articlesData.concat(batch) : batch;
        articleTotal = data.total ?? articlesData.length;
        articleOffset = articlesData.length;
        renderArticleList();
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
            case 'short_title':
                return String(draft.short_title || draft.main_line1 || '').trim();
            case 'subtitle':
                return joinDraftLines(draft.sub_title, draft.sub_title2);
            case 'summary':
                return String(draft.summary || '').trim();
            case 'tags':
                return String(draft.tags || '').trim();
            case 'first_comment':
                return String(draft.first_comment || '').trim();
            case 'all':
                return [
                    joinDraftLines(draft.main_line1, draft.main_line2),
                    String(draft.short_title || '').trim(),
                    joinDraftLines(draft.sub_title, draft.sub_title2),
                    String(draft.summary || '').trim(),
                    String(draft.tags || '').trim(),
                    String(draft.first_comment || '').trim(),
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
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="short_title">复制短标题</button>
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="subtitle">复制副标题</button>
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="summary">复制摘要</button>
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="tags">复制标签</button>
            <button type="button" class="btn btn-sm btn-outline-secondary copy-draft-btn" data-copy-field="first_comment">复制首评</button>
            <button type="button" class="btn btn-sm btn-outline-primary copy-draft-btn" data-copy-field="all">一键复制全部</button>
        </div>`;
    }

    function wireDraftCopyButtons(draft) {
        const labels = {
            title: '标题',
            short_title: '视频号短标题',
            subtitle: '副标题',
            summary: '摘要',
            tags: '标签',
            first_comment: '首评',
            all: '标题、短标题、副标题、摘要、标签、首评',
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
        if (!draft && !article.generated_video_path && !article.generated_cover_path) return '';
        const lines = [];
        if (draft) {
            if (draft.main_line1) lines.push(`<div><strong>主标题</strong>：${escapeHtml(draft.main_line1)}${draft.main_line2 ? ' / ' + escapeHtml(draft.main_line2) : ''}</div>`);
            if (draft.short_title) lines.push(`<div><strong>视频号短标题</strong>：${escapeHtml(draft.short_title)}</div>`);
            if (draft.sub_title) lines.push(`<div><strong>副标题</strong>：${escapeHtml(draft.sub_title)}${draft.sub_title2 ? ' / ' + escapeHtml(draft.sub_title2) : ''}</div>`);
            if (draft.summary) lines.push(`<div><strong>摘要</strong>：${escapeHtml(draft.summary)}</div>`);
            if (draft.tags) lines.push(`<div><strong>标签</strong>：${escapeHtml(draft.tags)}</div>`);
            lines.push(`<div class="mt-2"><strong>首评</strong>
                <textarea id="draftFirstCommentInput" class="form-control mt-1" rows="2" placeholder="15~50字，问句优先">${escapeHtml(draft.first_comment || '')}</textarea>
                <button type="button" class="btn btn-sm btn-outline-primary mt-1" id="saveFirstCommentBtn">保存首评</button>
            </div>`);
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
                <div class="small text-muted mb-1">发布封面</div>
                <img src="${mediaUrl(article.generated_cover_path)}" alt="发布封面"
                     style="max-width:100%;max-height:240px;border-radius:8px;border:1px solid #e2e8f0;" />
                <div class="mt-1 d-flex flex-wrap gap-2">
                    <a class="btn btn-sm btn-outline-secondary" href="${mediaUrl(article.generated_cover_path)}" download>下载封面</a>
                    <button type="button" class="btn btn-sm btn-outline-primary" id="retryCoverBtn">重做封面</button>
                </div>
               </div>`
            : `<div class="mt-2">
                <div class="small text-muted mb-1">发布封面</div>
                <p class="small text-muted mb-1">尚未生成封面</p>
                <button type="button" class="btn btn-sm btn-outline-primary" id="retryCoverBtn">生成封面</button>
               </div>`;
        const bgm = article.selected_bgm_path ? `<div class="small text-muted">BGM: ${escapeHtml(article.selected_bgm_path)}</div>` : '';
        return `<div class="video-draft-panel mb-3 p-2 border rounded">
            <div class="d-flex align-items-center gap-2 mb-2"><strong>AI 成片素材</strong>${statusBadge}</div>
            ${lines.join('')}
            ${renderDraftCopyButtons(article)}
            ${bgm}
            ${coverBlock}
            ${videoBlock}
            <div class="mt-2">
                <select id="retryTemplateSelect" class="form-control mb-2" style="max-width:280px;">
                    <option value="">成片模板（系统默认）</option>
                </select>
                <button class="btn btn-sm btn-outline-secondary" id="retryMediaBtn">重新出片</button>
                <label class="btn btn-sm btn-outline-secondary mb-0 ml-1" style="cursor:pointer;">
                    <input type="checkbox" id="useStoryImagesCheck" class="mr-1" style="vertical-align:middle;" />
                    使用同题图片
                </label>
                <label class="btn btn-sm btn-outline-secondary mb-0 ml-1" style="cursor:pointer;" title="勾选后会重新调用视觉模型评分，较慢">
                    <input type="checkbox" id="forceScoreImagesCheck" class="mr-1" style="vertical-align:middle;" />
                    重新评估配图
                </label>
                ${article.generated_video_path ? '<button class="btn btn-sm btn-success ml-1" id="publishVideoBtn" type="button">一键发布</button>' : ''}
                <a class="btn btn-sm btn-primary ml-1" href="/?from=ingestion&article_id=${encodeURIComponent(article.id)}">打开主页编辑</a>
            </div>
        </div>`;
    }

    async function selectArticle(id) {
        selectedArticleId = id;
        selectedPrepare = null;
        $('useOnHomeBtn').disabled = false;
        if (viewMode === 'list') {
            renderArticleList();
        } else {
            renderStoryTree();
        }
        const [article, related] = await Promise.all([
            api(`/api/ingestion/articles/${id}`),
            api(`/api/ingestion/articles/${id}/related`).catch(() => ({ articles: [], assets: [] })),
        ]);
        detailImageCache = [];
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
                content_description: asset.content_description,
                cover_fit_score: asset.cover_fit_score,
                flash_fit_score: asset.flash_fit_score,
                figure_prominence_score: asset.figure_prominence_score,
                orientation: asset.orientation,
                is_animated: asset.is_animated,
                width: asset.width,
                height: asset.height,
                score_breakdown: asset.score_breakdown,
            }));
        const failedCount = (article.images || []).filter((img) => img.download_status !== 'ok').length;
        const relatedArticles = (related.articles || [])
            .map((a) => `<li class="small">${escapeHtml(a.title)} <span class="text-muted">(${a.role})</span></li>`)
            .join('');
        const views = formatViewCount(article.view_count);
        const prepNote = article.generated_video_path
            ? `<p class="small text-success mb-2">✓ 已自动生成视频 · ${article.generated_video_at ? formatBeijingDateTime(article.generated_video_at) : ''}</p>`
            : article.video_prep_at
            ? `<p class="small text-success mb-2">✓ 主页素材已就绪 · ${formatBeijingDateTime(article.video_prep_at)}</p>`
            : (article.media_pipeline_status === 'pending' || article.media_pipeline_status === 'running'
                ? '<p class="small text-warning mb-2">媒体流水线处理中（配图/文案/出片）…</p>'
                : (article.score_grade === 'S' || (article.score_total != null && article.score_total >= 80)
                    ? '<p class="small text-muted mb-2">高分文章将自动排队出片（需 worker 运行 + API Key）</p>'
                    : ''));
        $('articleDetail').innerHTML = `
            <h5>${escapeHtml(article.title)}</h5>
            <p class="small text-muted">${views || '浏览量未知'} · ${article.published_at ? formatBeijingDateTime(article.published_at) : '—'}</p>
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
            <div class="mt-3 d-flex flex-wrap align-items-center gap-2">
                <button class="btn btn-sm btn-outline-secondary" id="scoreRuleBtn">规则评分</button>
                <button class="btn btn-sm btn-outline-primary" id="scoreLlmBtn">规则+AI评语</button>
                <button class="btn btn-sm btn-outline-info" id="scoreImagesBtn">评估配图</button>
                <button class="btn btn-sm btn-outline-primary" id="markSelectBtn">标记已选</button>
                <button class="btn btn-sm btn-primary" id="prepareBtn">准备主页数据（含同题图）</button>
                <button class="btn btn-sm btn-outline-warning" id="rerenderVideoBtn">重新出片</button>
                <label class="small mb-0 d-inline-flex align-items-center" style="cursor:pointer;">
                    <input type="checkbox" id="rerenderUseStoryImagesCheck" class="mr-1" />
                    使用同题图片
                </label>
                <label class="small mb-0 d-inline-flex align-items-center" style="cursor:pointer;" title="勾选后会重新调用视觉模型评分，较慢">
                    <input type="checkbox" id="rerenderForceScoreImagesCheck" class="mr-1" />
                    重新评估配图
                </label>
            </div>
            <pre class="meta mt-2" id="prepareMeta" style="display:none"></pre>
        `;
        $('markSelectBtn').onclick = async () => {
            await api(`/api/ingestion/articles/${id}/select`, { method: 'POST' });
            setStatus('已标记为 selected', 'ok');
            refreshMainList();
        };
        $('scoreRuleBtn').onclick = () => runScore(id, false);
        $('scoreLlmBtn').onclick = () => runScore(id, true);
        $('scoreImagesBtn').onclick = () => runScoreImages(id);
        $('prepareBtn').onclick = () => prepareForHome(id);
        const rerenderBtn = document.getElementById('rerenderVideoBtn');
        if (rerenderBtn) {
            rerenderBtn.onclick = () => retryMediaPipeline(id, {
                storyCheckboxId: 'rerenderUseStoryImagesCheck',
                forceScoreCheckboxId: 'rerenderForceScoreImagesCheck',
                button: rerenderBtn,
            });
        }
        const retryBtn = document.getElementById('retryMediaBtn');
        if (retryBtn) {
            retryBtn.onclick = () => retryMediaPipeline(id, {
                storyCheckboxId: 'useStoryImagesCheck',
                forceScoreCheckboxId: 'forceScoreImagesCheck',
                button: retryBtn,
            });
        }
        fillRetryTemplateSelect();
        const retryCoverBtn = document.getElementById('retryCoverBtn');
        if (retryCoverBtn) {
            retryCoverBtn.onclick = async () => {
                setStatus('正在生成封面…', 'muted');
                retryCoverBtn.disabled = true;
                try {
                    const res = await api(`/api/ingestion/articles/${id}/cover/retry`, { method: 'POST' });
                    setStatus(res.cover_path ? '封面已更新' : '封面生成完成', 'ok');
                    selectArticle(id);
                    refreshMainList();
                } catch (e) {
                    setStatus(e.message, 'error');
                } finally {
                    retryCoverBtn.disabled = false;
                }
            };
        }
        const saveFirstCommentBtn = document.getElementById('saveFirstCommentBtn');
        if (saveFirstCommentBtn) {
            saveFirstCommentBtn.onclick = async () => {
                const input = document.getElementById('draftFirstCommentInput');
                const value = input ? input.value.trim() : '';
                saveFirstCommentBtn.disabled = true;
                try {
                    await api(`/api/ingestion/articles/${id}/video-draft`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ first_comment: value }),
                    });
                    setStatus('首评已保存', 'ok');
                    selectArticle(id);
                } catch (e) {
                    setStatus(e.message, 'error');
                } finally {
                    saveFirstCommentBtn.disabled = false;
                }
            };
        }
        if (article.generated_video_path && article.video_draft) {
            wireDraftCopyButtons(article.video_draft);
        }
        bindImagePreviewEvents();
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
                `评分完成：行业 ${res.score_grade} ${Math.round(res.score_total)} 分` +
                    (res.viral_score_grade
                        ? ` · 传播 ${res.viral_score_grade} ${Math.round(res.viral_score_total || 0)} 分`
                        : '') +
                    (res.publish_tier
                        ? ` · ${PUBLISH_TIER_LABELS[res.publish_tier] || res.publish_tier}`
                        : '') +
                    (res.rule_grade && res.rule_grade !== res.score_grade
                        ? `（规则 ${res.rule_grade}→LLM 修正）`
                        : '') +
                    (res.llm_used ? '（含 AI 评语）' : ''),
                'ok'
            );
            selectArticle(id);
            refreshMainList();
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
            refreshMainList();
        } catch (e) {
            setStatus(e.message, 'error');
        }
    }

    async function retryMediaPipeline(id, { storyCheckboxId, forceScoreCheckboxId, button } = {}) {
        const storyCheckbox = storyCheckboxId ? document.getElementById(storyCheckboxId) : null;
        const forceScoreCheckbox = forceScoreCheckboxId ? document.getElementById(forceScoreCheckboxId) : null;
        const useStoryImages = Boolean(storyCheckbox && storyCheckbox.checked);
        const forceScoreImages = Boolean(forceScoreCheckbox && forceScoreCheckbox.checked);
        const busyLabel = forceScoreImages
            ? (useStoryImages ? '正在评估同题配图并重新出片…' : '正在重新评估配图并出片…')
            : (useStoryImages ? '正在用同题配图重新出片…' : '正在重新出片…');
        setStatus(busyLabel, 'muted');
        if (button) button.disabled = true;
        if (storyCheckbox) storyCheckbox.disabled = true;
        if (forceScoreCheckbox) forceScoreCheckbox.disabled = true;
        try {
            const qsParts = [];
            if (useStoryImages) qsParts.push('include_story_images=true');
            if (forceScoreImages) qsParts.push('force_score_images=true');
            const templateSelect = document.getElementById('retryTemplateSelect');
            if (templateSelect && templateSelect.value) {
                qsParts.push(`template_id=${encodeURIComponent(templateSelect.value)}`);
            }
            const qs = qsParts.length ? `?${qsParts.join('&')}` : '';
            const res = await api(`/api/ingestion/articles/${id}/media-pipeline/retry${qs}`, { method: 'POST' });
            const bits = [];
            if (useStoryImages) bits.push('含同题图');
            if (forceScoreImages) bits.push('重评配图');
            const suffix = bits.length ? `（${bits.join('，')}）` : '';
            setStatus(res.enqueued ? `已提交出片任务${suffix}` : `出片已执行${suffix}`, 'ok');
            selectArticle(id);
            refreshMainList();
        } catch (e) {
            setStatus(e.message, 'error');
        } finally {
            if (button) button.disabled = false;
            if (storyCheckbox) storyCheckbox.disabled = false;
            if (forceScoreCheckbox) forceScoreCheckbox.disabled = false;
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
                refreshMainList();
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

    $('refreshBtn').addEventListener('click', () => {
        refreshMainList().catch((e) => setStatus(e.message, 'error'));
    });
    $('runSourceBtn').addEventListener('click', runSource);
    $('scoreBatchBtn').addEventListener('click', scoreBatch);
    $('useOnHomeBtn').addEventListener('click', useOnHome);
    $('viewListBtn')?.addEventListener('click', () => setViewMode('list'));
    $('viewTreeBtn')?.addEventListener('click', () => setViewMode('tree'));
    $('treeMultiOnly')?.addEventListener('change', () => {
        if (viewMode === 'tree') renderStoryTree();
    });
    $('loadMoreStoriesBtn')?.addEventListener('click', () => {
        loadStories(true).catch((e) => setStatus(e.message, 'error'));
    });
    $('loadMoreArticlesBtn')?.addEventListener('click', () => {
        loadArticles(true).catch((e) => setStatus(e.message, 'error'));
    });
    $('aiReviewBtn')?.addEventListener('click', () => {
        runAiReview().catch((e) => setStatus(e.message, 'error'));
    });
    $('closeAiReviewBtn')?.addEventListener('click', () => {
        const panel = $('aiReviewPanel');
        if (panel) panel.style.display = 'none';
    });
    if ($('sourceSelect')) {
        $('sourceSelect').addEventListener('change', () => {
            updateSourceToolbar();
            if (viewMode === 'list') {
                refreshMainList().catch((e) => setStatus(e.message, 'error'));
            }
        });
    }
    if ($('sortSelect')) {
        $('sortSelect').addEventListener('change', () => {
            if (viewMode === 'list') refreshMainList().catch((e) => setStatus(e.message, 'error'));
        });
    }
    if ($('gradeSelect')) {
        $('gradeSelect').addEventListener('change', () => {
            if (viewMode === 'list') refreshMainList().catch((e) => setStatus(e.message, 'error'));
        });
    }
    async function applyQueryFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const articleId = params.get('article_id');
        const q = params.get('q');
        const sourceId = params.get('source_id');
        if (sourceId && $('sourceSelect')) {
            $('sourceSelect').value = sourceId;
            updateSourceToolbar();
        }
        if (q && $('searchInput')) {
            $('searchInput').value = q;
        }
        if (q || sourceId) {
            await loadArticles();
        }
        if (articleId) {
            try {
                await selectArticle(articleId);
            } catch (err) {
                setStatus(`无法打开文章 ${articleId}: ${err.message}`, 'error');
            }
        }
    }

    $('searchInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') refreshMainList().catch((err) => setStatus(err.message, 'error'));
    });
    $('searchInput').addEventListener('input', () => {
        if (viewMode === 'tree') renderStoryTree();
    });

    loadSources().then(async () => {
        const params = new URLSearchParams(window.location.search);
        const hasDeepLink = params.has('article_id') || params.has('q') || params.has('source_id');
        if (hasDeepLink) {
            await applyQueryFromUrl();
        } else {
            await loadArticles();
        }
        await loadIngestionWorkerHealth();
    }).catch((e) => setStatus(e.message, 'error'));

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
