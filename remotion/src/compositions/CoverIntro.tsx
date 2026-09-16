import React from 'react';
import {AbsoluteFill, Img} from 'remotion';
import {resolveMediaSrc} from './MediaLayer';

type Props = {
  coverImagePath: string;
};

export const CoverIntro: React.FC<Props> = ({coverImagePath}) => {
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <Img
        src={resolveMediaSrc(coverImagePath)}
        style={{width: '100%', height: '100%', objectFit: 'cover'}}
      />
    </AbsoluteFill>
  );
};
