export type Draft = {
  main_line1?: string;
  main_line2?: string;
  sub_title?: string;
  sub_title2?: string;
  summary?: string;
  tags?: string;
  highlight_keywords?: string[];
};

export type ImageClip = {
  path: string;
  duration: number;
  motionEffect?: string;
  animation?: string;
  imageYPercent?: number;
};

export type ChronicleTemplate = {
  canvas?: {width?: number; height?: number; fps?: number};
  palette?: Record<string, string>;
  chrome?: Record<string, string | string[]>;
  typography?: Record<string, number | string>;
  layout?: Record<string, number | string | boolean>;
  video?: {
    card_motion?: {
      enabled?: boolean;
      random?: boolean;
      end_scale?: number;
      pan_percent?: number;
      effects?: string[];
    };
    summary_animation?: {
      mode?: string;
      scope?: string;
      chars_per_second?: number;
      start_delay_sec?: number;
      show_cursor?: boolean;
      cursor_blink_hz?: number;
      cursor_hide_after_done_sec?: number;
      fit_video_duration?: boolean;
      max_chars_per_second?: number;
      tail_margin_sec?: number;
    };
  };
};

export type ChronicleVideoProps = {
  articleId: string;
  draft: Draft;
  images: ImageClip[];
  audioPath?: string;
  template: ChronicleTemplate;
  seed?: string;
  coverImagePath?: string;
  coverIntroDurationSec?: number;
};

export type ClassicOverlayProps = {
  summary: string;
  main_line1?: string;
  main_line2?: string;
  subtitle?: string;
  subtitle2?: string;
  images: ImageClip[];
  audioPath?: string;
  backgroundImagePath?: string;
  tags?: string;
  summaryHighlightKeywords?: string[];
  showSummary?: boolean;
  titleFontSize?: number;
  titleYPercent?: number;
  mainLine1Color?: string;
  mainLine2Color?: string;
  subtitleBarColor?: string;
  subtitleTextColor?: string;
  coverImagePath?: string;
  coverIntroDurationSec?: number;
};
