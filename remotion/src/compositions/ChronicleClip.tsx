import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {ChronicleTemplate, Draft} from '../lib/types';
import {ChronicleFrame} from './ChronicleFrame';

type Props = {
  draft: Draft;
  template: ChronicleTemplate;
  heroSrc: string;
  motionEffect: string;
  endScale: number;
  pan: number;
  includeSummary?: boolean;
};

export const ChronicleClip: React.FC<Props> = ({
  draft,
  template,
  heroSrc,
  motionEffect,
  endScale,
  pan,
  includeSummary = false,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  return (
    <ChronicleFrame
      draft={draft}
      template={template}
      heroSrc={heroSrc}
      frame={frame}
      fps={fps}
      durationInFrames={durationInFrames}
      motionEffect={motionEffect}
      endScale={endScale}
      pan={pan}
      includeHero={true}
      includeSummary={includeSummary}
    />
  );
};
