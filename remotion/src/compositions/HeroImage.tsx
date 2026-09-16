import React from 'react';
import {heroMotionAt} from '../lib/motion';
import {MediaLayer} from './MediaLayer';

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
      <MediaLayer
        src={src}
        width="100%"
        height="100%"
        objectFit="cover"
        playbackRate={1}
        style={{
          transform,
          transformOrigin: 'center center',
        }}
      />
    </div>
  );
};
