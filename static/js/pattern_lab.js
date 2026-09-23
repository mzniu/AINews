(function () {
    const harnessBox = document.getElementById('harnessBox');
    const workBox = document.getElementById('workBox');
    let currentVersionId = '';
    let pollTimer = null;
    let logFollowTail = true;

    function setCurateBusy(busy) {
        const btn = document.getElementById('curateBtn');
        if (!btn) return;
        btn.disabled = busy;
        btn.textContent = busy ? '拆卡进行中…' : '拆成打法';
    }

    function renderProgress(progress) {
        const box = document.getElementById('jobProgressBox');
        const fill = document.getElementById('jobProgressFill');
        const phase = document.getElementById('jobPhase');
        const turnStep = document.getElementById('jobTurnStep');
        const list = document.getElementById('jobEvents');
        if (!box || !progress || !progress.phase) {
            if (box) box.hidden = true;
            return;
        }
        box.hidden = false;
        const percent = Math.max(0, Math.min(100, Number(progress.percent) || 0));
        if (fill) fill.style.width = percent + '%';
        if (phase) phase.textContent = progress.phase_label || '';
        const turn = progress.turn || 0;
        const step = progress.step || 0;
        const artifacts = progress.artifacts || {};
        const bits = [];
        if (turn) bits.push('第 ' + turn + ' 轮');
        if (step) bits.push('步骤 ' + step);
        if (artifacts.analysis_md) bits.push('结构标注已写出');
        if (artifacts.card_yaml) bits.push('模式卡已写出');
        if (artifacts.playbook_diff) bits.push('打法差异已写出');
        if (turnStep) turnStep.textContent = bits.join(' · ');
        if (list) {
            list.innerHTML = '';
            (progress.events || []).forEach((event) => {
                const item = document.createElement('li');
                item.textContent = event.label || '';
                list.appendChild(item);
            });
        }
    }

    async function loadSessionLog(jobId) {
        const box = document.getElementById('sessionLogDetails');
        const pre = document.getElementById('sessionLogText');
        if (!box || !pre || !jobId) return;
        const nearBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 48;
        try {
            const res = await fetch('/api/copy-agent/jobs/' + jobId + '/log');
            const data = await res.json();
            pre.textContent = data.text || '（等待智能体输出…）';
            box.hidden = false;
            if (logFollowTail || nearBottom) {
                pre.scrollTop = pre.scrollHeight;
            }
        } catch (err) {
            pre.textContent = '日志加载失败';
            box.hidden = false;
        }
    }

    function bindSessionLogScroll() {
        const pre = document.getElementById('sessionLogText');
        if (!pre || pre.dataset.logScrollBound === '1') return;
        pre.dataset.logScrollBound = '1';
        pre.addEventListener('scroll', () => {
            logFollowTail = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 48;
        });
    }

    function renderJobResult(job) {
        document.getElementById('jobSummary').textContent = job.summary || '';
        const issuesBox = document.getElementById('schemaIssuesDetails');
        const issuesList = document.getElementById('schemaIssuesList');
        const issues = job.schema_issues || [];
        if (issuesBox && issuesList) {
            issuesList.innerHTML = '';
            issues.forEach((line) => {
                const li = document.createElement('li');
                li.textContent = line;
                issuesList.appendChild(li);
            });
            issuesBox.hidden = !issues.length;
        }
        const bodyBox = document.getElementById('bodyIssuesDetails');
        const bodyList = document.getElementById('bodyIssuesList');
        const bodyIssues = job.body_issues || [];
        if (bodyBox && bodyList) {
            bodyList.innerHTML = '';
            bodyIssues.forEach((line) => {
                const li = document.createElement('li');
                li.textContent = line;
                bodyList.appendChild(li);
            });
            bodyBox.hidden = !bodyIssues.length;
        }
        const details = document.getElementById('pathDetails');
        const paths = job.paths || [];
        details.hidden = !paths.length;
        document.getElementById('pathList').textContent = paths.join('\n');
        document.getElementById('publishBox').hidden = job.status !== 'candidate';
        currentVersionId = job.playbook_version_id || '';
        renderProgress(job.progress);
        const resultDetails = document.getElementById('resultDetails');
        const trapNote = document.getElementById('trapNote');
        const cardPreview = document.getElementById('cardPreview');
        const bodyPreview = document.getElementById('playbookBodyPreview');
        const showResult = job.status === 'candidate' && (job.playbook_body || job.card_preview);
        resultDetails.hidden = !showResult;
        if (showResult) {
            cardPreview.textContent = formatCardPreviewText(job.card_preview || {});
            bodyPreview.textContent = job.playbook_body || '';
            if (job.trap_passed === false) {
                trapNote.hidden = false;
                trapNote.textContent = '这版打法里有固定陷阱句，自动出片开关打开前请先改掉。';
            } else {
                trapNote.hidden = true;
                trapNote.textContent = '';
            }
        }
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    async function fetchJob(jobId) {
        const res = await fetch('/api/copy-agent/jobs/' + jobId);
        if (!res.ok) return null;
        return res.json();
    }

    function startPolling(jobId) {
        stopPolling();
        setCurateBusy(true);
        logFollowTail = true;
        bindSessionLogScroll();
        const progressBox = document.getElementById('jobProgressBox');
        const logBox = document.getElementById('sessionLogDetails');
        if (progressBox) progressBox.hidden = false;
        if (logBox) {
            logBox.hidden = false;
            logBox.open = true;
        }
        const logPre = document.getElementById('sessionLogText');
        if (logPre) logPre.textContent = '（正在连接会话…）';
        loadSessionLog(jobId);
        pollTimer = setInterval(async () => {
            const job = await fetchJob(jobId);
            if (!job) return;
            renderJobResult(job);
            loadSessionLog(jobId);
            if (job.status !== 'running') {
                stopPolling();
                setCurateBusy(false);
                if (job.progress && job.progress.phase === 'done') {
                    document.getElementById('jobProgressBox').hidden = false;
                }
                loadSessionLog(job.job_id);
            }
        }, 2000);
        fetchJob(jobId).then((job) => {
            if (job) renderJobResult(job);
            loadSessionLog(jobId);
        });
    }

    async function loadHarness() {
        const res = await fetch('/api/copy-agent/harness');
        const data = await res.json();
        harnessBox.innerHTML = '';
        data.lines.forEach((line) => {
            const p = document.createElement('p');
            p.textContent = line;
            harnessBox.appendChild(p);
        });
        if (!data.ready) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = '重新检测';
            button.onclick = loadHarness;
            harnessBox.appendChild(button);
            workBox.style.display = 'none';
            return;
        }
        workBox.style.display = 'block';
        loadVersions();
        loadPatterns();
        const active = await fetch('/api/copy-agent/jobs/active').then((r) => r.json());
        if (active.job_id) {
            startPolling(active.job_id);
        }
    }

    async function curate() {
        const text = document.getElementById('materialText').value || '';
        document.getElementById('jobSummary').textContent = '';
        document.getElementById('resultDetails').hidden = true;
        document.getElementById('publishBox').hidden = true;
        document.getElementById('schemaIssuesDetails').hidden = true;
        document.getElementById('sessionLogDetails').hidden = true;
        const logPre = document.getElementById('sessionLogText');
        if (logPre) logPre.textContent = '';
        const res = await fetch('/api/copy-agent/materials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                include_battle: !document.getElementById('learnAgainBtn').hidden,
            }),
        });
        const created = await res.json();
        if (!res.ok) {
            document.getElementById('jobSummary').textContent = created.detail || created.message || '拆卡失败';
            if (created.job_id) {
                startPolling(created.job_id);
            }
            return;
        }
        if (created.status === 'running') {
            startPolling(created.job_id);
            return;
        }
        const job = await fetchJob(created.job_id);
        if (job) {
            renderJobResult(job);
            loadSessionLog(job.job_id);
        }
        setCurateBusy(false);
    }

    async function publishVersion() {
        const message = document.getElementById('publishMessage');
        message.textContent = '';
        const res = await fetch('/api/copy-agent/versions/' + currentVersionId + '/publish', { method: 'POST' });
        const data = await res.json();
        if (res.status === 409 && data.hint === 'disable_auto_switch') {
            message.textContent = data.message || '先关掉「自动出片也用这一版」，再发布这一版。';
            return;
        }
        if (!res.ok) {
            message.textContent = data.message || '发布失败';
            return;
        }
        message.textContent = '已发布为当前打法。';
        loadVersions();
        loadPatterns();
    }

    function formatCardPreviewText(card) {
        if (!card || card.legacy_card) {
            const forbidden = (card.forbidden_transfers || []).map((line) => '- ' + line).join('\n');
            return [
                '（旧版模式卡，建议重新拆卡）',
                '判断功能：' + (card.verdict_function_label || card.verdict_function || '—'),
                forbidden ? '不宜照搬：\n' + forbidden : '',
                card.evidence_excerpt ? '实例锚点：' + card.evidence_excerpt : '',
            ].filter(Boolean).join('\n\n');
        }
        const lines = [];
        if (card.pattern_name) {
            lines.push('模式：' + card.pattern_name + (card.genre_label ? '（' + card.genre_label + '）' : ''));
        }
        if (card.purpose) lines.push('目的：' + card.purpose);
        if (card.moves && card.moves.length) {
            lines.push(
                '结构（moves）：\n' +
                    card.moves.map((m) => '- ' + (m.id || '?') + '：' + (m.function || '')).join('\n')
            );
        }
        const hook = card.hook || {};
        if (hook.archetype || hook.archetype_label) {
            lines.push(
                '钩子：' +
                    (hook.archetype_label || hook.archetype) +
                    (hook.opening_slots && hook.opening_slots.length
                        ? '\n  槽位：' + hook.opening_slots.join('、')
                        : '') +
                    (hook.payoff_contract ? '\n  兑现：' + hook.payoff_contract : '')
            );
        }
        const motives = card.motives || {};
        if (motives.primary_label || motives.primary) {
            lines.push(
                '传播动机：' +
                    (motives.primary_label || motives.primary) +
                    (motives.arousal ? ' · 唤醒 ' + motives.arousal : '')
            );
        }
        if (card.verdict_function_label || card.verdict_function) {
            lines.push('体裁功能：' + (card.verdict_function_label || card.verdict_function));
        }
        const forbidden = (card.forbidden_transfers || []).map((line) => '- ' + line).join('\n');
        if (forbidden) lines.push('不宜照搬：\n' + forbidden);
        if (card.evidence_excerpt) lines.push('实例锚点（不进出稿）：' + card.evidence_excerpt);
        return lines.join('\n\n') || '（模式卡为空）';
    }

    function formatVersionTime(iso) {
        if (!iso) return '';
        try {
            return new Date(iso).toLocaleString();
        } catch (err) {
            return iso;
        }
    }

    function appendDetailSection(container, title, text, emptyHint) {
        const heading = document.createElement('h3');
        heading.style.fontSize = '14px';
        heading.style.margin = '12px 0 4px';
        heading.textContent = title;
        container.appendChild(heading);
        const pre = document.createElement('pre');
        pre.style.whiteSpace = 'pre-wrap';
        pre.style.fontSize = '13px';
        pre.style.margin = '0 0 8px';
        pre.style.padding = '10px 12px';
        pre.style.borderRadius = '8px';
        pre.style.background = 'var(--surface-muted,#f8fafc)';
        pre.style.border = '1px solid var(--border-subtle,#e2e8f0)';
        const value = (text || '').trim();
        pre.textContent = value || emptyHint || '（无）';
        container.appendChild(pre);
    }

    function renderVersionDetail(detail, container) {
        const card = detail.card_preview || {};
        container.innerHTML = '';
        const meta = document.createElement('p');
        meta.style.fontSize = '13px';
        meta.style.color = 'var(--text-muted,#64748b)';
        meta.style.margin = '0 0 8px';
        meta.textContent = [
            detail.is_current ? '当前版本' : '历史版本',
            detail.status === 'candidate' ? '候选' : detail.status === 'published' ? '已发布' : detail.status,
            detail.trap_passed ? '陷阱检查通过' : '陷阱检查未过',
            formatVersionTime(detail.created_at),
            detail.id ? 'ID ' + detail.id : '',
        ].filter(Boolean).join(' · ');
        container.appendChild(meta);
        appendDetailSection(container, '模式卡（抽象模式）', formatCardPreviewText(card), '（未关联模式卡，可能是早期版本）');
        appendDetailSection(
            container,
            '写法说明（出稿时注入模型的打法正文）',
            detail.body || '',
            '（正文为空）'
        );
        const qualityIssues = detail.quality_issues || [];
        if (qualityIssues.length) {
            appendDetailSection(
                container,
                '质量提示（建议重新拆卡）',
                qualityIssues.map((line) => '- ' + line).join('\n'),
                ''
            );
        }
        const bodyIssues = detail.body_issues || [];
        if (bodyIssues.length) {
            appendDetailSection(
                container,
                '一致性提示',
                bodyIssues.map((line) => '- ' + line).join('\n'),
                ''
            );
        }
        appendDetailSection(
            container,
            '差异稿（拆卡时的 playbook.diff.yaml 原文）',
            detail.diff_yaml || '',
            '（无差异稿存档）'
        );
        container.dataset.loaded = '1';
    }

    async function fillVersionDetail(versionId, container) {
        const res = await fetch('/api/copy-agent/versions/' + versionId);
        if (!res.ok) {
            container.textContent = '加载失败';
            return;
        }
        const detail = await res.json();
        renderVersionDetail(detail, container);
    }

    async function loadPatterns() {
        const box = document.getElementById('patternsBox');
        const list = document.getElementById('patternsList');
        const empty = document.getElementById('patternsEmpty');
        if (!box || !list) return;
        try {
            const res = await fetch('/api/copy-agent/patterns');
            const data = await res.json();
            const rows = data.patterns || [];
            box.style.display = 'block';
            list.innerHTML = '';
            if (!rows.length) {
                if (empty) empty.hidden = false;
                return;
            }
            if (empty) empty.hidden = true;
            rows.forEach((row) => {
                const p = document.createElement('p');
                p.style.margin = '0 0 6px';
                p.textContent = [
                    row.pattern_name,
                    row.genre_label || row.genre,
                    row.count + ' 个版本',
                    row.motives_primary || '',
                    row.hook_archetype || '',
                ]
                    .filter(Boolean)
                    .join(' · ');
                list.appendChild(p);
            });
        } catch (err) {
            box.style.display = 'block';
            if (empty) {
                empty.hidden = false;
                empty.textContent = '模式库加载失败';
            }
        }
    }

    async function loadVersions() {
        const box = document.getElementById('versionsBox');
        const list = document.getElementById('versionsList');
        const empty = document.getElementById('versionsEmpty');
        if (!box || !list) return;
        try {
            const res = await fetch('/api/copy-agent/versions');
            const data = await res.json();
            box.style.display = 'block';
            list.innerHTML = '';
            const rows = data.versions || [];
            if (!rows.length) {
                if (empty) empty.hidden = false;
                return;
            }
            if (empty) empty.hidden = true;
            rows.forEach((version) => {
                const details = document.createElement('details');
                details.style.marginBottom = '8px';
                const summary = document.createElement('summary');
                const tags = [];
                if (version.is_current) tags.push('当前');
                if (version.status === 'candidate') tags.push('候选');
                else if (version.status === 'published') tags.push('已发布');
                else tags.push(version.status);
                if (!version.trap_passed) tags.push('陷阱未过');
                const when = formatVersionTime(version.created_at);
                const name = version.pattern_name || '';
                const motive = version.motives_primary_label || '';
                const hook = version.hook_archetype_label || '';
                const tagsExtra = [motive, hook].filter(Boolean).join(' · ');
                const preview = version.body_preview || '（空正文）';
                const prefix = name ? '【' + name + '】' : '';
                const label = prefix + (tagsExtra ? '(' + tagsExtra + ') ' : '') + preview;
                summary.textContent =
                    tags.join(' · ') + (when ? ' · ' + when : '') + ' — ' + label + '（展开查看详情）';
                details.appendChild(summary);
                const inner = document.createElement('div');
                inner.style.paddingTop = '8px';
                inner.textContent = '正在加载…';
                details.appendChild(inner);
                details.addEventListener('toggle', () => {
                    if (details.open && inner.dataset.loaded !== '1') {
                        fillVersionDetail(version.id, inner);
                    }
                });
                if (version.is_current) {
                    details.open = true;
                    fillVersionDetail(version.id, inner);
                }
                list.appendChild(details);
            });
        } catch (err) {
            box.style.display = 'block';
            list.innerHTML = '';
            if (empty) {
                empty.hidden = false;
                empty.textContent = '版本列表加载失败';
            }
        }
    }

    async function toggleAuto() {
        const enabled = document.getElementById('autoSwitch').checked;
        const res = await fetch('/api/copy-agent/auto-switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled }),
        });
        if (!res.ok) {
            const data = await res.json();
            document.getElementById('publishMessage').textContent = data.message || '现在不能打开';
            document.getElementById('autoSwitch').checked = false;
        }
    }

    async function loadRankingSettings() {
        try {
            const res = await fetch('/api/copy-agent/settings');
            const data = await res.json();
            const autoMat = document.getElementById('autoMaterialAdaptive');
            const mat = document.getElementById('materialAdaptive');
            if (autoMat) autoMat.checked = !!data.auto_material_adaptive_playbook;
            if (mat) mat.checked = data.material_adaptive_playbook !== false;
            const autoSw = document.getElementById('autoSwitch');
            if (autoSw && data.auto_uses_current_playbook != null) {
                autoSw.checked = !!data.auto_uses_current_playbook;
            }
        } catch (_e) {
            /* ignore */
        }
    }

    async function patchRankingSettings(body) {
        const res = await fetch('/api/copy-agent/settings', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const data = await res.json();
            document.getElementById('publishMessage').textContent = data.message || '设置保存失败';
        }
    }

    async function loadReport() {
        const res = await fetch('/api/copy-agent/battle-report');
        const data = await res.json();
        const rollupsBox = document.getElementById('patternRollups');
        if (rollupsBox) {
            rollupsBox.innerHTML = '';
            (data.pattern_rollups || []).forEach((row) => {
                const p = document.createElement('p');
                p.style.margin = '0 0 4px';
                p.textContent = [
                    '模式「' + row.pattern_name + '」',
                    row.job_count + ' 次打法发布',
                    '转发合计 ' + (row.share_count ?? 0),
                    (row.platforms || []).join('/'),
                ]
                    .filter(Boolean)
                    .join(' · ');
                rollupsBox.appendChild(p);
            });
        }
        const box = document.getElementById('reportRows');
        box.innerHTML = '';
        (data.rows || []).forEach((row) => {
            const p = document.createElement('p');
            const ratio = row.ratio == null ? (row.ratio_note || '') : String(row.ratio);
            const pattern = row.pattern_name ? '模式「' + row.pattern_name + '」' : '';
            const motive = row.motives_primary_label ? row.motives_primary_label : '';
            p.textContent = [
                row.attribution || '宪法版',
                pattern,
                motive,
                row.platform,
                '转发 ' + (row.share_count ?? '—'),
                '赞 ' + (row.like_count ?? '—'),
                ratio,
            ]
                .filter(Boolean)
                .join(' · ');
            box.appendChild(p);
        });
        document.getElementById('learnAgainBtn').hidden = !(data.learn_again && data.learn_again.length);
        const fb = document.getElementById('selectionFallbackCount');
        if (fb) {
            fb.textContent =
                '选型回退次数（CopyDraft）：' + String(data.selection_fallback_count ?? 0);
        }
    }

    document.getElementById('curateBtn').onclick = curate;
    document.getElementById('publishBtn').onclick = publishVersion;
    document.getElementById('autoSwitch').onchange = toggleAuto;
    const autoMatEl = document.getElementById('autoMaterialAdaptive');
    if (autoMatEl) {
        autoMatEl.onchange = () =>
            patchRankingSettings({
                auto_material_adaptive_playbook: autoMatEl.checked,
            });
    }
    const matEl = document.getElementById('materialAdaptive');
    if (matEl) {
        matEl.onchange = () =>
            patchRankingSettings({ material_adaptive_playbook: matEl.checked });
    }
    document.getElementById('learnAgainBtn').onclick = () => {
        document.getElementById('materialText').focus();
    };
    loadHarness();
    loadRankingSettings();
    loadReport();
})();
