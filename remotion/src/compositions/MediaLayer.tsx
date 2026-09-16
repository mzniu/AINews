import React from 'react';
import {Gif} from '@remotion/gif';
import {Img, OffthreadVideo, staticFile} from 'remotion';

const PIP_PLAYBACK_RATE = 1.5;

export const isVideoPath = (path: string): boolean => /\.(mp4|webm|mov)$/i.test(path);
export const isGifPath = (path: string): boolean => /\.gif$/i.test(path);

export const resolveMediaSrc = (path: string): string => {
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('file://')) {
    return path;
  }
  return staticFile(path.replace(/^\//, '').replace(/^workspace\//, ''));
};

type Props = {
  src: string;
  width: number | string;
  height: number | string;
  style?: React.CSSProperties;
  objectFit?: 'contain' | 'cover';
  playbackRate?: number;
};

export const MediaLayer: React.FC<Props> = ({
  src,
  width,
  height,
  style,
  objectFit = 'contain',
  playbackRate = PIP_PLAYBACK_RATE,
}) => {
  const resolved = resolveMediaSrc(src);
  const baseStyle: React.CSSProperties = {
    width,
    height,
    objectFit,
    display: 'block',
    ...style,
  };

  if (isVideoPath(src)) {
    return (
      <OffthreadVideo
        src={resolved}
        style={baseStyle}
        playbackRate={playbackRate}
        muted
        volume={0}
      />
    );
  }

  if (isGifPath(src)) {
    const w = typeof width === 'number' ? width : 800;
    const h = typeof height === 'number' ? height : 600;
    return <Gif src={resolved} width={w} height={h} fit={objectFit === 'cover' ? 'cover' : 'contain'} />;
  }

  return <Img src={resolved} style={baseStyle} />;
};
