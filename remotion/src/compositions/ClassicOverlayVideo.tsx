import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {ClassicOverlayProps} from '../lib/types';
import {hexToRgb} from '../lib/colors';
import {fontStyles} from '../lib/fonts';
import {mergeHighlightKeywords, splitHighlightSegments} from '../lib/text';
import {
  ANIM_TYPES,
  computeImageMotion,
  computeTitleSlideOffset,
  pickAnimType,
  textFadeAlpha,
} from '../lib/classicMotion';

const resolveSrc = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('file://')) {
    return path;
  }
  return staticFile(path.replace(/^\//, '').replace(/^workspace\//, ''));
};

const isVideoPath = (path: string): boolean => /\.(mp4|webm|mov)$/i.test(path);
const isGifPath = (path: string): boolean => /\.gif$/i.test(path);

type ClipProps = {
  src: string;
  durationInFrames: number;
  anim: string;
  imageYPercent: number;
  titleSlideEntrance: boolean;
  showSummary: boolean;
  summary: string;
  summaryKeywords: string[];
  titleBlock: React.ReactNode;
  backgroundImagePath: string;
};

const ClassicClip: React.FC<ClipProps> = ({
  src,
  durationInFrames,
  anim,
  imageYPercent,
  titleSlideEntrance,
  showSummary,
  summary,
  summaryKeywords,
  titleBlock,
  backgroundImagePath,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const slotTop = height * 0.28;
  const slotBottom = height * 0.78;
  const slotH = slotBottom - slotTop;
  const motion = computeImageMotion(t, durationInFrames / fps, anim as typeof ANIM_TYPES[number], width * 0.84, slotH);
  const titleOffset = titleSlideEntrance ? computeTitleSlideOffset(t) : 0;
  const summaryAlpha = textFadeAlpha(t);

  const imgStyle: React.CSSProperties = {
    width: '84%',
    maxHeight: slotH,
    objectFit: 'contain',
    margin: '0 auto',
    display: 'block',
    opacity: motion.opacity,
    transform: motion.transform,
    transformOrigin: 'center center',
    clipPath: motion.clipPath,
  };

  const summaryLines = summary.split('\n').filter(Boolean);

  return (
    <AbsoluteFill>
      <Img src={resolveSrc(backgroundImagePath)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: 0, transform: `translateY(${titleOffset}px)`}}>
        {titleBlock}
      </div>
      <div
        style={{
          position: 'absolute',
          left: '8%',
          right: '8%',
          top: slotTop + imageYPercent * height * 0.01,
          height: slotH,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {isVideoPath(src) ? (
          <OffthreadVideo src={resolveSrc(src)} style={imgStyle} muted />
        ) : isGifPath(src) ? (
          <Img src={resolveSrc(src)} style={imgStyle} />
        ) : (
          <Img src={resolveSrc(src)} style={imgStyle} />
        )}
      </div>
      {showSummary && summary ? (
        <div
          style={{
            position: 'absolute',
            left: '8%',
            right: '8%',
            bottom: height * 0.1,
            opacity: summaryAlpha,
            color: '#FFFFFF',
            fontSize: 34,
            lineHeight: 1.35,
            textAlign: 'center',
            textShadow: '0 2px 8px rgba(0,0,0,0.5)',
            ...fontStyles.body,
          }}
        >
          {summaryLines.map((line, i) => {
            const segments = splitHighlightSegments(line, summaryKeywords);
            return (
              <div key={i}>
                {segments.map((seg, j) => (
                  <span key={j} style={{color: seg.highlight ? '#FFEC30' : '#FFFFFF'}}>{seg.text}</span>
                ))}
              </div>
            );
          })}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const ClassicOverlayVideo: React.FC<ClassicOverlayProps> = ({
  summary,
  main_line1,
  main_line2,
  subtitle,
  subtitle2,
  images,
  audioPath,
  backgroundImagePath = 'static/imgs/bg.png',
  tags = '',
  summaryHighlightKeywords = [],
  showSummary = true,
  titleFontSize = 60,
  titleYPercent = 12,
  mainLine1Color = '#FFFFFF',
  mainLine2Color = '#FFFFFF',
}) => {
  const {fps} = useVideoConfig();
  const keywords = mergeHighlightKeywords(summaryHighlightKeywords, tags);
  let cursor = 0;

  const titleBlock = (
    <div
      style={{
        position: 'absolute',
        left: '8%',
        right: '8%',
        top: `${titleYPercent}%`,
        ...fontStyles.title,
        fontSize: titleFontSize,
        lineHeight: 1.2,
        textShadow: '0 2px 8px rgba(0,0,0,0.45)',
      }}
    >
      {main_line1 ? <div style={{color: hexToRgb(mainLine1Color, '#FFFFFF')}}>{main_line1}</div> : null}
      {main_line2 ? <div style={{color: hexToRgb(mainLine2Color, '#FFFFFF')}}>{main_line2}</div> : null}
      {subtitle ? (
        <div
          style={{
            marginTop: 12,
            fontSize: Math.round(titleFontSize * 0.7),
            background: '#FFEC30',
            color: '#111',
            display: 'inline-block',
            padding: '4px 12px',
            borderRadius: 8,
            fontWeight: 700,
          }}
        >
          {subtitle}
        </div>
      ) : null}
      {subtitle2 ? (
        <div
          style={{
            marginTop: 8,
            fontSize: Math.round(titleFontSize * 0.63),
            background: '#FFEC30',
            color: '#111',
            display: 'inline-block',
            padding: '4px 12px',
            borderRadius: 8,
            fontWeight: 700,
          }}
        >
          {subtitle2}
        </div>
      ) : null}
    </div>
  );

  return (
    <AbsoluteFill>
      {images.map((clip, index) => {
        const durationInFrames = Math.max(1, Math.round(clip.duration * fps));
        const from = cursor;
        cursor += durationInFrames;
        const anim = clip.animation && clip.animation !== 'auto'
          ? clip.animation
          : pickAnimType(index, images.length);
        return (
          <Sequence key={`${clip.path}-${index}`} from={from} durationInFrames={durationInFrames}>
            <ClassicClip
              src={clip.path}
              durationInFrames={durationInFrames}
              anim={anim}
              imageYPercent={clip.imageYPercent ?? 0}
              titleSlideEntrance={index === 0}
              showSummary={showSummary}
              summary={summary}
              summaryKeywords={keywords}
              titleBlock={titleBlock}
              backgroundImagePath={backgroundImagePath}
            />
          </Sequence>
        );
      })}
      {audioPath ? <Audio src={resolveSrc(audioPath)} /> : null}
    </AbsoluteFill>
  );
};
