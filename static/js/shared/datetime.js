/**
 * 全站时间展示统一为北京时间（Asia/Shanghai）。
 * 服务端 naive ISO 时间默认按 UTC 解析（与 datetime.utcnow 入库一致）。
 */
(function (global) {
    const TZ = 'Asia/Shanghai';
    const NAIVE_ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/;
    const DATETIME_LOCAL_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

    function parseBeijingDatetimeLocal(value) {
        if (!value) return null;
        const text = String(value).trim();
        if (!DATETIME_LOCAL_RE.test(text)) return null;
        const [datePart, timePart] = text.split('T');
        const [year, month, day] = datePart.split('-').map(Number);
        const [hour, minute] = timePart.split(':').map(Number);
        return new Date(Date.UTC(year, month - 1, day, hour - 8, minute, 0, 0));
    }

    function parseServerDateTime(value) {
        if (value == null || value === '') return null;
        if (value instanceof Date) return value;
        const text = String(value).trim();
        if (!text) return null;
        if (DATETIME_LOCAL_RE.test(text)) {
            return parseBeijingDatetimeLocal(text);
        }
        const normalized = text.includes(' ') && !text.includes('T')
            ? text.replace(' ', 'T')
            : text;
        if (NAIVE_ISO_RE.test(normalized)) {
            return new Date(`${normalized}Z`);
        }
        const parsed = new Date(normalized);
        return Number.isNaN(parsed.getTime()) ? null : parsed;
    }

    function formatBeijingDateTime(value, options) {
        const date = parseServerDateTime(value);
        if (!date) return '—';
        const opts = {
            timeZone: TZ,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            ...(options || {}),
        };
        if (opts.second === false) delete opts.second;
        return date.toLocaleString('zh-CN', opts);
    }

    function formatBeijingDate(value, options) {
        const date = parseServerDateTime(value);
        if (!date) return '—';
        return date.toLocaleDateString('zh-CN', {
            timeZone: TZ,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            ...(options || {}),
        });
    }

    function toBeijingDatetimeLocalValue(value) {
        const date = value ? parseServerDateTime(value) : new Date();
        if (!date) return '';
        const parts = new Intl.DateTimeFormat('en-CA', {
            timeZone: TZ,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        }).formatToParts(date);
        const get = (type) => parts.find((part) => part.type === type)?.value || '';
        return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
    }

    function beijingNowPlusMinutes(minutes) {
        return new Date(Date.now() + Number(minutes || 0) * 60 * 1000);
    }

    global.parseServerDateTime = parseServerDateTime;
    global.parseBeijingDatetimeLocal = parseBeijingDatetimeLocal;
    global.formatBeijingDateTime = formatBeijingDateTime;
    global.formatBeijingDate = formatBeijingDate;
    global.toBeijingDatetimeLocalValue = toBeijingDatetimeLocalValue;
    global.beijingNowPlusMinutes = beijingNowPlusMinutes;
})(typeof window !== 'undefined' ? window : globalThis);
