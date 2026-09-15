export const DEFAULT_CARD_MOTION_END_SCALE = 1.22;
export const DEFAULT_CARD_MOTION_PAN = 0.7;

export const DEFAULT_CARD_MOTION_EFFECTS = [
  'zoom_in',
  'zoom_out',
  'pan_left',
  'pan_right',
  'pan_up',
  'pan_down',
  'zoom_in_left',
  'zoom_in_right',
  'zoom_in_up',
  'zoom_in_down',
] as const;

export type MotionEffect = (typeof DEFAULT_CARD_MOTION_EFFECTS)[number];

const easeOutQuad = (progress: number): number => 1 - (1 - progress) ** 2;

export const heroMotionAt = (
  t: number,
  duration: number,
  effect: string,
  endScale = DEFAULT_CARD_MOTION_END_SCALE,
  pan = DEFAULT_CARD_MOTION_PAN,
): {scale: number; offsetX: number; offsetY: number} => {
  const progress = duration <= 0 ? 1 : Math.max(0, Math.min(1, t / duration));
  const ease = easeOutQuad(progress);
  const scale = Math.max(1, endScale);
  const amp = Math.max(0, Math.min(1, pan));
  const name = (effect || 'zoom_in').trim().toLowerCase();
  const zoom = 1 + (scale - 1) * ease;

  switch (name) {
    case 'zoom_out':
      return {scale: scale + (1 - scale) * ease, offsetX: 0, offsetY: 0};
    case 'pan_left':
      return {scale, offsetX: amp * (1 - 2 * ease), offsetY: 0};
    case 'pan_right':
      return {scale, offsetX: -amp * (1 - 2 * ease), offsetY: 0};
    case 'pan_up':
      return {scale, offsetX: 0, offsetY: amp * (1 - 2 * ease)};
    case 'pan_down':
      return {scale, offsetX: 0, offsetY: -amp * (1 - 2 * ease)};
    case 'zoom_in_left':
      return {scale: zoom, offsetX: -amp * ease, offsetY: 0};
    case 'zoom_in_right':
      return {scale: zoom, offsetX: amp * ease, offsetY: 0};
    case 'zoom_in_up':
      return {scale: zoom, offsetX: 0, offsetY: -amp * ease};
    case 'zoom_in_down':
      return {scale: zoom, offsetX: 0, offsetY: amp * ease};
    default:
      return {scale: zoom, offsetX: 0, offsetY: 0};
  }
};

const hashString = (input: string): number => {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    hash = (hash * 31 + input.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
};

export const pickCardMotionEffect = (
  effects: string[],
  seed: string,
  index: number,
): string => {
  const names = effects.filter((item) => item.trim());
  if (names.length === 0) {
    return 'zoom_in';
  }
  const idx = hashString(`${seed}:${index}`) % names.length;
  return names[idx];
};
