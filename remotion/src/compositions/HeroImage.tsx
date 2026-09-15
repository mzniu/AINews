import React from 'react';
import {Img, staticFile} from 'remotion';
import {heroMotionAt} from '../lib/motion';

type Props = {
  src: string;
  width: number;
  height: number;
  frame: number;
  fps: number;
  durationInFrames: number;
  effect: string;
  endScale: number;
  pan: number;
};

const resolveSrc = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('file://')) {
    return path;
  }
  const cleaned = path.replace(/^\//, '').replace(/^workspace\//, '');
  return staticFile(cleaned);
};

export const HeroImage: React.FC<Props> = ({
  src,
  width,
  height,
  frame,
  fps,
  durationInFrames,
  effect,
  endScale,
  pan,
}) => {
  const t = frame / fps;
  const durationSec = durationInFrames / fps;
  const {scale, offsetX, offsetY} = heroMotionAt(t, durationSec, effect, endScale, pan);

  const zoom = Math.max(1, scale);
  const transform = `scale(${zoom}) translate(${offsetX * 12}%, ${offsetY * 12}%)`;

  return (
    <div
      style={{
        width,
        height,
        overflow: 'hidden',
        borderRadius: 4,
        backgroundColor: '#111',
      }}
    >
      <Img
        src={resolveSrc(src)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform,
          transformOrigin: 'center center',
        }}
      />
    </div>
  );
};
