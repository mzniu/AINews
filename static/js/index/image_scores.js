/**
 * 资讯库配图评分 — 主页选图参考（与 ingestion_library 字段对齐）
 */
(function (global) {
    function normalizeIngestionImage(img, index) {
        if (typeof img === 'string') {
            return { url: img, local_path: img, success: true };
        }
        const localPath = img.local_path || '';
        const remoteUrl = img.url || localPath;
        return {
            url: remoteUrl,
            local_path: localPath || remoteUrl,
            success: img.success !== false,
            alt: img.alt || `图片 ${index + 1}`,
            source: img.source || 'ingestion',
            auto_selected: img.auto_selected === true,
            relevance_score: img.relevance_score ?? null,
            relevance_grade: img.relevance_grade ?? null,
            relevance_rank: img.relevance_rank ?? null,
            cover_fit_score: img.cover_fit_score ?? null,
            figure_prominence_score: img.figure_prominence_score ?? null,
            flash_fit_score: img.flash_fit_score ?? null,
            orientation: img.orientation ?? null,
            is_animated: img.is_animated === true,
            caption: img.caption ?? null,
            verdict: img.verdict ?? null,
            source_type: img.source_type ?? null,
        };
    }

    function hasImageScores(images) {
        return Array.isArray(images) && images.some(
            (img) => img && (img.relevance_grade != null || img.relevance_score != null)
        );
    }

    function sortImagesByRelevance(images) {
        if (!hasImageScores(images)) return images;
        return [...images].sort((a, b) => {
            const ra = a.relevance_rank ?? 9999;
            const rb = b.relevance_rank ?? 9999;
            if (ra !== rb) return ra - rb;
            return (b.relevance_score ?? 0) - (a.relevance_score ?? 0);
        });
    }

    function buildImageScoreBadgesHtml(img) {
        const parts = [];
        if (img.relevance_grade) {
            const score = img.relevance_score != null ? Math.round(img.relevance_score) : '';
            const label = score !== '' ? `${img.relevance_grade} ${score}` : img.relevance_grade;
            parts.push(`<span class="isb isb-grade isb-${String(img.relevance_grade).toLowerCase()}">${label}</span>`);
        }
        if (img.flash_fit_score != null) {
            parts.push(`<span class="isb isb-flash" title="短视频主画面适配">主画面 ${Math.round(img.flash_fit_score)}</span>`);
        }
        if (img.cover_fit_score != null) {
            parts.push(`<span class="isb isb-cover" title="封面适配度">封面 ${Math.round(img.cover_fit_score)}</span>`);
        }
        if (img.figure_prominence_score != null) {
            parts.push(`<span class="isb isb-figure" title="人物突出度">人物 ${Math.round(img.figure_prominence_score)}</span>`);
        }
        if (img.is_animated) {
            parts.push('<span class="isb isb-animated" title="动图/GIF，短视频优先">动图</span>');
        }
        if (img.orientation === 'landscape') {
            parts.push('<span class="isb isb-landscape">横图</span>');
        } else if (img.orientation === 'portrait') {
            parts.push('<span class="isb isb-portrait">竖图</span>');
        }
        if (!parts.length) return '';
        return `<div class="image-score-badges">${parts.join('')}</div>`;
    }

    function imageScoreTooltip(img) {
        const lines = [];
        if (img.verdict) lines.push(img.verdict);
        if (img.caption) lines.push(img.caption);
        if (img.relevance_rank != null) lines.push(`排序 #${img.relevance_rank}`);
        return lines.join(' · ');
    }

    function renderImageScoreLegend() {
        return `<div class="image-score-legend">
            <strong>配图评分参考</strong>
            <span class="text-muted">8–12 秒短视频 · 建议 3–4 张主画面 · 动图优先 · 已按相关度排序</span>
        </div>`;
    }

    global.ImageScoreUI = {
        normalizeIngestionImage,
        hasImageScores,
        sortImagesByRelevance,
        buildImageScoreBadgesHtml,
        imageScoreTooltip,
        renderImageScoreLegend,
    };
})(typeof window !== 'undefined' ? window : globalThis);
