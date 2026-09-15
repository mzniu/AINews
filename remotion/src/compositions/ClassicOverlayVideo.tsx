import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, staticFile, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {ClassicOverlayProps} from '../lib/types';
import {hexToRgb} from '../lib/colors';

const resolveSrc = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('file://')) {
    return path;
  }
  return staticFile(path.replace(/^\//, '').replace(/^workspace\//, ''));
};

const ImageSlide: React.FC<{src: string; durationInFrames: number}> = ({src, durationInFrames}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, durationInFrames], [1, 1.15], {
    extrapolateRight: 'clamp',
  });

  return (
    <Img
      src={resolveSrc(src)}
      style={{
        width: '88%',
        margin: '0 auto',
        display: 'block',
        marginTop: '34%',
        borderRadius: 12,
        transform: `scale(${scale})`,
        transformOrigin: 'center center',
      }}
    />
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
  showSummary = true,
  titleYPercent = 12,
  mainLine1Color = '#FFFFFF',
  mainLine2Color = '#FFFFFF',
}) => {
  const {fps, height} = useVideoConfig();
  let cursor = 0;

  return (
    <AbsoluteFill>
      <Img
        src={resolveSrc(backgroundImagePath)}
        style={{width: '100%', height: '100%', objectFit: 'cover'}}
      />
      <div
        style={{
          position: 'absolute',
          left: '8%',
          right: '8%',
          top: `${titleYPercent}%`,
          color: hexToRgb(mainLine1Color, '#FFFFFF'),
          fontSize: 60,
          fontWeight: 700,
          lineHeight: 1.2,
          textShadow: '0 2px 8px rgba(0,0,0,0.45)',
        }}
      >
        {main_line1 ? <div>{main_line1}</div> : null}
        {main_line2 ? <div style={{color: hexToRgb(mainLine2Color, '#FFFFFF')}}>{main_line2}</div> : null}
        {subtitle ? (
          <div style={{marginTop: 12, fontSize: 42, background: '#FFEC30', color: '#111', display: 'inline-block', padding: '4px 12px', borderRadius: 8}}>
            {subtitle}
          </div>
        ) : null}
        {subtitle2 ? (
          <div style={{marginTop: 8, fontSize: 38, background: '#FFEC30', color: '#111', display: 'inline-block', padding: '4px 12px', borderRadius: 8}}>
            {subtitle2}
          </div>
        ) : null}
      </div>

      {images.map((clip, index) => {
        const durationInFrames = Math.max(1, Math.round(clip.duration * fps));
        const from = cursor;
        cursor += durationInFrames;
        return (
          <Sequence key={`${clip.path}-${index}`} from={from} durationInFrames={durationInFrames}>
            <ImageSlide src={clip.path} durationInFrames={durationInFrames} />
          </Sequence>
        );
      })}

      {showSummary && summary ? (
        <div
          style={{
            position: 'absolute',
            left: '8%',
            right: '8%',
            bottom: height * 0.12,
            color: '#FFFFFF',
            fontSize: 34,
            lineHeight: 1.35,
            textAlign: 'center',
            textShadow: '0 2px 8px rgba(0,0,0,0.5)',
          }}
        >
          {summary}
        </div>
      ) : null}

      {audioPath ? <Audio src={resolveSrc(audioPath)} /> : null}
    </AbsoluteFill>
  );
};
