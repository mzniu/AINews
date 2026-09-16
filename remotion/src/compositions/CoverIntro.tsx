import React from 'react';
import {AbsoluteFill} from 'remotion';
import {ChronicleTemplate, Draft} from '../lib/types';
import {ChronicleFrame} from './ChronicleFrame';

type Props = {
  draft: Draft;
  template: ChronicleTemplate;
  heroSrc: string;
};

/** Static chronicle cover intro — matches Python render_chronicle_cover layout with Remotion fonts. */
export const CoverIntro: React.FC<Props> = ({draft, template, heroSrc}) => {
  return (
    <AbsoluteFill style={{backgroundColor: '#070B10'}}>
      <ChronicleFrame
        draft={draft}
        template={template}
        heroSrc={heroSrc}
        frame={0}
        fps={24}
        durationInFrames={24}
        motionEffect="zoom_in"
        endScale={1}
        pan={0}
        includeHero={true}
        includeSummary={false}
      />
    </AbsoluteFill>
  );
};
