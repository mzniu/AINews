import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import {ChronicleVideoProps} from '../lib/types';
import {
  DEFAULT_CARD_MOTION_EFFECTS,
  DEFAULT_CARD_MOTION_END_SCALE,
  DEFAULT_CARD_MOTION_PAN,
  pickCardMotionEffect,
} from '../lib/motion';
import {parseSummaryAnimationConfig} from '../lib/summaryTypewriter';
import {ChronicleClip} from './ChronicleClip';
import {CoverIntro} from './CoverIntro';

const resolveAudio = (path?: string): string | undefined => {
  if (!path) {
    return undefined;
  }
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  return staticFile(path.replace(/^\//, ''));
};

export const ChronicleVideo: React.FC<ChronicleVideoProps> = ({
  articleId,
  draft,
  images,
  audioPath,
  template,
  seed,
  coverImagePath,
  coverIntroDurationSec = 0,
}) => {
  const {fps} = useVideoConfig();
  const videoCfg = template.video || {};
  const motionCfg = videoCfg.card_motion || {};
  const motionEnabled = motionCfg.enabled ?? true;
  const endScale = motionCfg.end_scale ?? DEFAULT_CARD_MOTION_END_SCALE;
  const pan = (motionCfg.pan_percent ?? DEFAULT_CARD_MOTION_PAN * 100) / 100;
  const effects = motionCfg.effects || [...DEFAULT_CARD_MOTION_EFFECTS];
  const motionSeed = seed || articleId;
  const summaryAnimCfg = parseSummaryAnimationConfig(videoCfg);
  const useTypewriter = summaryAnimCfg.mode === 'typewriter';

  const introFrames =
    coverImagePath && coverIntroDurationSec > 0
      ? Math.max(1, Math.round(coverIntroDurationSec * fps))
      : 0;
  const coverIntroSec = introFrames / fps;
  const clipDurations = images.map((clip) => clip.duration);
  const videoDurationSec =
    coverIntroSec + clipDurations.reduce((sum, duration) => sum + duration, 0);

  let cursor = introFrames;
  let clipGlobalStartSec = coverIntroSec;

  return (
    <AbsoluteFill style={{backgroundColor: '#070B10'}}>
      {coverImagePath && introFrames > 0 && images.length > 0 ? (
        <Sequence from={0} durationInFrames={introFrames}>
          <CoverIntro draft={draft} template={template} heroSrc={images[0].path} />
        </Sequence>
      ) : null}

      {images.map((clip, index) => {
        const durationInFrames = Math.max(1, Math.round(clip.duration * fps));
        const from = cursor;
        const clipStartSec = clipGlobalStartSec;
        cursor += durationInFrames;
        clipGlobalStartSec += clip.duration;
        const effect =
          clip.motionEffect ||
          (motionCfg.random
            ? pickCardMotionEffect(effects, motionSeed, index)
            : effects[index % effects.length]);

        return (
          <Sequence key={`${clip.path}-${index}`} from={from} durationInFrames={durationInFrames}>
            <ChronicleClip
              draft={draft}
              template={template}
              heroSrc={clip.path}
              motionEffect={motionEnabled ? effect : 'zoom_in'}
              endScale={motionEnabled ? endScale : 1}
              pan={motionEnabled ? pan : 0}
              includeSummary={!useTypewriter}
              clipGlobalStartSec={clipStartSec}
              summaryAnimCfg={useTypewriter ? summaryAnimCfg : undefined}
              videoDurationSec={useTypewriter ? videoDurationSec : undefined}
            />
          </Sequence>
        );
      })}
      {resolveAudio(audioPath) ? <Audio src={resolveAudio(audioPath)!} /> : null}
    </AbsoluteFill>
  );
};
