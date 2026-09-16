export type SummaryAnimationConfig = {
  mode: 'static' | 'typewriter';
  scope: string;
  chars_per_second: number;
  start_delay_sec: number;
  show_cursor: boolean;
  cursor_blink_hz: number;
  cursor_hide_after_done_sec: number;
  fit_video_duration: boolean;
  max_chars_per_second: number;
  tail_margin_sec: number;
};

const DEFAULT_SUMMARY_ANIMATION: SummaryAnimationConfig = {
  mode: 'static',
  scope: 'once',
  chars_per_second: 14,
  start_delay_sec: 0.35,
  show_cursor: true,
  cursor_blink_hz: 2,
  cursor_hide_after_done_sec: 0.5,
  fit_video_duration: false,
  max_chars_per_second: 28,
  tail_margin_sec: 0.5,
};

export const parseSummaryAnimationConfig = (
  videoCfg?: {summary_animation?: Record<string, unknown>},
): SummaryAnimationConfig => {
  const raw = {...((videoCfg || {}).summary_animation || {})};
  const merged = {...DEFAULT_SUMMARY_ANIMATION, ...raw};
  const mode = String(merged.mode || 'static').trim().toLowerCase();
  return {
    ...merged,
    mode: mode === 'typewriter' ? 'typewriter' : 'static',
  };
};

export const chronicleContentGlobalT = ({
  coverIntroSec,
  clipDurations,
  clipIndex,
  tWithinClip,
}: {
  coverIntroSec: number;
  clipDurations: number[];
  clipIndex: number;
  tWithinClip: number;
}): number => {
  let elapsed = coverIntroSec;
  for (let idx = 0; idx < Math.max(0, clipIndex); idx += 1) {
    if (idx < clipDurations.length) {
      elapsed += clipDurations[idx];
    }
  }
  return elapsed + tWithinClip;
};

export const summaryVisibleChars = (
  globalT: number,
  {
    totalChars,
    animCfg,
    contentStartT = 0,
    videoDuration,
  }: {
    totalChars: number;
    animCfg: SummaryAnimationConfig;
    contentStartT?: number;
    videoDuration?: number;
  },
): number => {
  if (totalChars <= 0) {
    return 0;
  }
  if (animCfg.mode !== 'typewriter') {
    return totalChars;
  }
  const delay = animCfg.start_delay_sec;
  const cps = Math.max(0.1, animCfg.chars_per_second);
  const typingT = globalT - contentStartT - delay;
  if (typingT <= 0) {
    return 0;
  }
  if (animCfg.fit_video_duration && videoDuration !== undefined) {
    const tail = animCfg.tail_margin_sec;
    const maxCps = Math.max(cps, animCfg.max_chars_per_second);
    const budget = Math.max(0.1, videoDuration - contentStartT - delay - tail);
    const neededCps = totalChars / budget;
    const effectiveCps = Math.min(maxCps, Math.max(cps, neededCps));
    const visible = Math.floor(typingT * effectiveCps);
    if (globalT >= videoDuration - tail) {
      return totalChars;
    }
    return Math.min(totalChars, visible);
  }
  return Math.min(totalChars, Math.floor(typingT * cps));
};

export const partialSummaryLines = (lines: string[], visibleCharCount: number): string[] => {
  if (visibleCharCount <= 0) {
    return [];
  }
  let remaining = visibleCharCount;
  const partial: string[] = [];
  for (const line of lines) {
    if (remaining <= 0) {
      break;
    }
    const take = Math.min(line.length, remaining);
    partial.push(line.slice(0, take));
    remaining -= take;
  }
  return partial;
};

export const cursorBlinkOn = (globalT: number, animCfg: SummaryAnimationConfig): boolean => {
  const hz = Math.max(0.1, animCfg.cursor_blink_hz);
  const period = 1 / hz;
  return Math.floor(globalT / (period / 2)) % 2 === 0;
};

export const shouldDrawSummaryCursor = (
  globalT: number,
  visibleCharCount: number,
  totalChars: number,
  animCfg: SummaryAnimationConfig,
  contentStartT = 0,
): boolean => {
  if (!animCfg.show_cursor || visibleCharCount <= 0) {
    return false;
  }
  if (visibleCharCount < totalChars) {
    return cursorBlinkOn(globalT, animCfg);
  }
  const delay = animCfg.start_delay_sec;
  const cps = Math.max(0.1, animCfg.chars_per_second);
  const hideAfter = animCfg.cursor_hide_after_done_sec;
  const doneT = contentStartT + delay + totalChars / cps;
  if (globalT > doneT + hideAfter) {
    return false;
  }
  return cursorBlinkOn(globalT, animCfg);
};
