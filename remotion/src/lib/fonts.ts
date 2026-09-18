/**
 * System font stack for offline Remotion renders.
 * Avoids @remotion/google-fonts network fetches (294 requests) that often
 * time out on Windows CI / local builds.
 */
const NOTO_SC = '"Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif';
const INTER = 'Inter, "Segoe UI", system-ui, sans-serif';

export const fonts = {
  notoSansSc: NOTO_SC,
  inter: INTER,
};

export const fontStyles = {
  title: {
    fontFamily: NOTO_SC,
    fontWeight: 700 as const,
  },
  body: {
    fontFamily: NOTO_SC,
    fontWeight: 400 as const,
  },
  brandLatin: {
    fontFamily: INTER,
    fontWeight: 600 as const,
  },
  badge: {
    fontFamily: INTER,
    fontWeight: 400 as const,
  },
};
