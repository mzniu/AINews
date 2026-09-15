import React from 'react';
import {AbsoluteFill} from 'remotion';
import {ChronicleTemplate, Draft} from '../lib/types';
import {hexToRgb} from '../lib/colors';
import {mergeHighlightKeywords, splitHighlightSegments, wrapLine} from '../lib/text';
import {HeroImage} from './HeroImage';
import {TechBackdrop} from './TechBackdrop';

type Props = {
  draft: Draft;
  template: ChronicleTemplate;
  heroSrc?: string;
  heroWidth?: number;
  heroHeight?: number;
  frame?: number;
  fps?: number;
  durationInFrames?: number;
  motionEffect?: string;
  endScale?: number;
  pan?: number;
  includeHero?: boolean;
  includeSummary?: boolean;
};

const pct = (value: number, total: number): number => Math.round(total * value);

export const ChronicleFrame: React.FC<Props> = ({
  draft,
  template,
  heroSrc,
  heroWidth = 0,
  heroHeight = 0,
  frame = 0,
  fps = 24,
  durationInFrames = 60,
  motionEffect = 'zoom_in',
  endScale = 1.22,
  pan = 0.7,
  includeHero = true,
  includeSummary = true,
}) => {
  const canvas = template.canvas || {};
  const width = canvas.width || 1080;
  const height = canvas.height || 1920;
  const palette = template.palette || {};
  const chrome = template.chrome || {};
  const typo = template.typography || {};
  const layout = template.layout || {};

  const textColor = hexToRgb(String(typo.main_line1_color || palette.text), 'rgb(244, 247, 250)');
  const muted = hexToRgb(String(palette.text_muted), 'rgb(139, 150, 168)');
  const accent = hexToRgb(String(palette.accent), 'rgb(61, 220, 255)');
  const accentDim = hexToRgb(String(palette.accent_dim), 'rgb(26, 106, 138)');
  const titleHi = hexToRgb(String(typo.title_highlight_color), 'rgb(255, 236, 48)');
  const hookColor = hexToRgb(String(typo.subtitle2_color), accent);
  const cardColor = hexToRgb(String(palette.card), 'rgb(255, 255, 255)');
  const summaryColor = hexToRgb(String(typo.summary_color || palette.text), textColor);

  const inset = pct(0.024, width);
  const titleSize = Number(typo.title_font_size || 64);
  const subSize = Number(typo.subtitle_font_size || 47);
  const brandSize = Number(typo.brand_font_size || 43);
  const brandSubSize = Number(typo.brand_sub_font_size || 28);
  const footerSize = Number(typo.footer_font_size || 40);

  const cardTop = pct(Number(layout.card_top_percent || 32) / 100, height);
  const cardBottom = pct(Number(layout.card_bottom_percent || 68) / 100, height);
  const cardLeft = pct(Number(layout.card_left_percent || 8) / 100, width);
  const cardRight = pct(Number(layout.card_right_percent || 92) / 100, width);
  const cardInset = Number(layout.card_inset_px || 16);

  const innerLeft = cardLeft + cardInset;
  const innerTop = cardTop + cardInset;
  const innerWidth = cardRight - cardLeft - cardInset * 2;
  const innerHeight = cardBottom - cardTop - cardInset * 2;

  const titleTop = layout.title_top_percent
    ? pct(Number(layout.title_top_percent) / 100, height)
    : pct(0.11 + Number(typo.top_pad_percent || 5) / 100, height);

  const titleKeywords = mergeHighlightKeywords(
    draft.highlight_keywords || [],
    draft.tags || '',
  );

  const renderHighlighted = (line: string, size: number, base: string, hi: string) => {
    const segments = splitHighlightSegments(line, titleKeywords);
    return (
      <span style={{fontSize: size, lineHeight: 1.15}}>
        {segments.map((seg, i) => (
          <span key={i} style={{color: seg.highlight ? hi : base}}>{seg.text}</span>
        ))}
      </span>
    );
  };

  const titleLines = [
    ...wrapLine(draft.main_line1 || '', 16).slice(0, 2),
    ...(draft.main_line2 ? wrapLine(draft.main_line2, 16).slice(0, 1) : []),
  ];

  const footerText = (draft.summary || '').replace(/^小牛说：/, '').trim();
  const footerLines = wrapLine(footerText, 22).slice(0, 3);
  const summaryY = pct(Number(typo.summary_y_percent || 75.2) / 100, height);
  const footerY = pct(Number(typo.footer_y_percent || 85.2) / 100, height);
  const placement = String(layout.title_placement || 'above_card');

  return (
    <AbsoluteFill>
      <TechBackdrop width={width} height={height} palette={palette} />
      <div style={{position: 'absolute', left: inset + 16, top: pct(0.038, height) + pct(Number(typo.top_pad_percent || 5) / 100, height), display: 'flex', alignItems: 'center', gap: 16}}>
        <div style={{width: 64, height: 64, border: `2px solid ${accent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: textColor, fontSize: brandSize, fontWeight: 700}}>
          {String(chrome.mark_glyph || '牛')}
        </div>
        <div>
          <div style={{color: textColor, fontSize: brandSize, fontWeight: 700}}>{String(chrome.brand || '小牛聊AI')}</div>
          {chrome.brand_sub ? (
            <div style={{color: muted, fontSize: brandSubSize, marginTop: 6}}>{String(chrome.brand_sub)}</div>
          ) : null}
        </div>
      </div>

      {placement === 'above_card' ? (
        <div style={{position: 'absolute', left: pct(0.045, width) + 18, top: titleTop, maxWidth: width - inset - 40, color: textColor}}>
          <div style={{position: 'absolute', left: -18, top: 0, width: 2, height: pct(0.14, height), background: accentDim}} />
          {titleLines.map((line, i) => (
            <div key={i} style={{marginBottom: 8}}>
              {renderHighlighted(line, i < 2 ? titleSize : subSize, textColor, titleHi)}
            </div>
          ))}
          {draft.sub_title ? <div style={{fontSize: subSize, marginTop: 4}}>{draft.sub_title}</div> : null}
          {draft.sub_title2 ? <div style={{fontSize: subSize, marginTop: 4, color: hookColor}}>{draft.sub_title2}</div> : null}
        </div>
      ) : null}

      <div
        style={{
          position: 'absolute',
          left: cardLeft,
          top: cardTop,
          width: cardRight - cardLeft,
          height: cardBottom - cardTop,
          background: cardColor,
          borderRadius: 12,
          overflow: 'hidden',
        }}
      >
        {includeHero && heroSrc ? (
          <div style={{position: 'absolute', left: cardInset, top: cardInset}}>
            <HeroImage
              src={heroSrc}
              width={innerWidth}
              height={innerHeight}
              frame={frame}
              fps={fps}
              durationInFrames={durationInFrames}
              effect={motionEffect}
              endScale={endScale}
              pan={pan}
            />
          </div>
        ) : null}
      </div>

      {placement === 'below_card' ? (
        <div style={{position: 'absolute', left: pct(0.045, width) + 18, top: cardBottom + 24, maxWidth: width - inset - 40, color: textColor}}>
          {titleLines.map((line, i) => (
            <div key={i} style={{marginBottom: 8}}>
              {renderHighlighted(line, i < 2 ? titleSize : subSize, textColor, titleHi)}
            </div>
          ))}
        </div>
      ) : null}

      {includeSummary && footerLines.length > 0 ? (
        <div style={{position: 'absolute', left: 0, right: 0, top: summaryY, textAlign: 'center', padding: '0 10%'}}>
          {footerLines.map((line, i) => (
            <div key={i} style={{fontSize: footerSize, color: summaryColor, marginBottom: 8}}>
              {renderHighlighted(line, footerSize, summaryColor, accent)}
            </div>
          ))}
        </div>
      ) : null}

      <div style={{position: 'absolute', left: pct(0.045, width), top: footerY, display: 'flex', alignItems: 'center', gap: 14}}>
        <div style={{width: 2, height: pct(0.1, height), background: accentDim}} />
        <div style={{fontSize: Math.round(footerSize * 0.9), color: muted}}>{String(chrome.footer_left || '快讯档案')}</div>
      </div>
    </AbsoluteFill>
  );
};
