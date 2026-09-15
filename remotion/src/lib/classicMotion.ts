export const ENTRANCE_DUR = 0.4;
export const HOLD_NO_TEXT = 0.8;
export const TEXT_FADE_IN = 0.4;
export const HOLD_WITH_TEXT = 1.4;
export const TITLE_SLIDE_DURATION = 0.68;
export const SCROLL_UP_PX_PER_SEC = 380;

export const ANIM_TYPES = [
  'zoom_in',
  'zoom_out',
  'unfold',
  'scroll_up',
  'slide_left',
  'slide_right',
  'fade_in',
  'drop_bounce',
] as const;

export type AnimType = (typeof ANIM_TYPES)[number];

const easeOutCubic = (p: number): number => 1 - (1 - p) ** 3;
const easeOutQuad = (p: number): number => 1 - (1 - p) ** 2;

export const pickAnimType = (index: number, seed = 0): AnimType => {
  const shuffled = [...ANIM_TYPES];
  const offset = seed % shuffled.length;
  return shuffled[(index + offset) % shuffled.length];
};

export type ImageMotionState = {
  opacity: number;
  transform: string;
  clipPath?: string;
};

export const computeImageMotion = (
  t: number,
  duration: number,
  anim: AnimType,
  viewportW: number,
  viewportH: number,
): ImageMotionState => {
  const entrance = ENTRANCE_DUR;
  const progress = duration <= 0 ? 1 : Math.max(0, Math.min(1, t / entrance));
  const ease = easeOutCubic(progress);

  if (t < entrance) {
    switch (anim) {
      case 'zoom_in': {
        const scale = 0.3 + 0.7 * ease;
        const bounce = 1 + 0.08 * Math.sin(Math.PI * progress) * (1 - progress);
        return {opacity: 1, transform: `scale(${scale * bounce})`};
      }
      case 'zoom_out': {
        const scale = 1.6 - 0.6 * ease;
        const bounce = 1 + 0.06 * Math.sin(Math.PI * progress) * (1 - progress);
        return {opacity: 1, transform: `scale(${scale * bounce})`};
      }
      case 'unfold': {
        const revealW = Math.max(0.05, ease);
        const revealH = 0.4 + 0.6 * ease;
        return {
          opacity: 1,
          transform: 'scale(1)',
          clipPath: `inset(${(1 - revealH) * 50}% ${(1 - revealW) * 50}% ${(1 - revealH) * 50}% ${(1 - revealW) * 50}%)`,
        };
      }
      case 'scroll_up': {
        const startY = viewportH * 0.55;
        const endY = 0;
        const y = startY + (endY - startY) * ease;
        return {opacity: 1, transform: `translateY(${y}px)`};
      }
      case 'slide_left': {
        const x = viewportW * 0.9 * (1 - ease);
        return {opacity: 1, transform: `translateX(${x}px)`};
      }
      case 'slide_right': {
        const x = -viewportW * 0.9 * (1 - ease);
        return {opacity: 1, transform: `translateX(${x}px)`};
      }
      case 'fade_in':
        return {opacity: ease, transform: 'scale(1)'};
      case 'drop_bounce': {
        const bounce = Math.max(0, Math.min(1.3, 1 - Math.exp(-5 * progress) * Math.cos(3 * Math.PI * progress)));
        const y = -viewportH * 0.35 * (1 - bounce);
        return {opacity: 1, transform: `translateY(${y}px)`};
      }
      default:
        return {opacity: 1, transform: 'scale(1)'};
    }
  }

  if (anim === 'scroll_up' && duration > entrance) {
    const scrollPhase = duration - entrance;
    const scrollProgress = Math.max(0, Math.min(1, (t - entrance) / scrollPhase));
    const maxDist = Math.min(viewportH * 0.28, SCROLL_UP_PX_PER_SEC * scrollPhase);
    const offset = maxDist * scrollProgress;
    return {opacity: 1, transform: `translateY(${-offset}px)`};
  }

  if (anim === 'zoom_in' && duration > entrance) {
    const zoomProgress = Math.max(0, Math.min(1, (t - entrance) / (duration - entrance)));
    const zoomEase = easeOutQuad(zoomProgress);
    const scale = 1 + 0.15 * zoomEase;
    return {opacity: 1, transform: `scale(${scale})`};
  }

  return {opacity: 1, transform: 'scale(1)'};
};

export const computeTitleSlideOffset = (
  t: number,
  slidePx = 120,
  delay = ENTRANCE_DUR,
): number => {
  const tt = t - delay;
  if (tt < 0) {
    return -slidePx;
  }
  if (tt >= TITLE_SLIDE_DURATION) {
    return 0;
  }
  const progress = tt / TITLE_SLIDE_DURATION;
  const ease = 1 - (1 - progress) ** 3;
  return -Math.round(slidePx * (1 - ease));
};

export const textFadeAlpha = (t: number): number => {
  const start = HOLD_NO_TEXT;
  if (t < start) {
    return 0;
  }
  if (t >= start + TEXT_FADE_IN) {
    return 1;
  }
  return (t - start) / TEXT_FADE_IN;
};
