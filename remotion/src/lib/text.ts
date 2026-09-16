export const mergeHighlightKeywords = (
  explicit: string[] = [],
  tags = '',
): string[] => {
  const out: string[] = [];
  for (const entry of explicit) {
    const s = (entry || '').trim();
    if (s) {
      out.push(s);
    }
  }
  if (tags) {
    for (const part of tags.replace(/，/g, ' ').split(/\s+/)) {
      const w = part.trim().replace(/^#/, '');
      if (w) {
        out.push(w);
      }
    }
  }
  const seen = new Set<string>();
  const uniq: string[] = [];
  for (const item of out) {
    if (!seen.has(item)) {
      seen.add(item);
      uniq.push(item);
    }
  }
  return uniq;
};

export const wrapLine = (text: string, maxChars = 18): string[] => {
  const cleaned = (text || '').trim();
  if (!cleaned) {
    return [];
  }
  const lines: string[] = [];
  let current = '';
  for (const char of cleaned) {
    const trial = current + char;
    if (trial.length <= maxChars || !current) {
      current = trial;
    } else {
      lines.push(current);
      current = char;
    }
    if (lines.length >= 3) {
      break;
    }
  }
  if (current && lines.length < 3) {
    lines.push(current);
  }
  return lines;
};

export const splitHighlightSegments = (
  line: string,
  keywords: string[],
): Array<{text: string; highlight: boolean}> => {
  if (!line || keywords.length === 0) {
    return [{text: line, highlight: false}];
  }
  const sorted = [...keywords].sort((a, b) => b.length - a.length);
  const pattern = sorted.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const regex = new RegExp(pattern, 'g');
  const segments: Array<{text: string; highlight: boolean}> = [];
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(line)) !== null) {
    if (match.index > last) {
      segments.push({text: line.slice(last, match.index), highlight: false});
    }
    segments.push({text: match[0], highlight: true});
    last = match.index + match[0].length;
  }
  if (last < line.length) {
    segments.push({text: line.slice(last), highlight: false});
  }
  return segments.length > 0 ? segments : [{text: line, highlight: false}];
};
