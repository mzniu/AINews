export const hexToRgb = (value: string | undefined, fallback: string): string => {
  const raw = (value || '').trim().replace('#', '');
  if (raw.length !== 6) {
    return fallback;
  }
  const r = parseInt(raw.slice(0, 2), 16);
  const g = parseInt(raw.slice(2, 4), 16);
  const b = parseInt(raw.slice(4, 6), 16);
  if ([r, g, b].some((n) => Number.isNaN(n))) {
    return fallback;
  }
  return `rgb(${r}, ${g}, ${b})`;
};
