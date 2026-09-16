import React from 'react';
import {CalculateMetadataFunction, Composition} from 'remotion';
import {ChronicleVideo} from './compositions/ChronicleVideo';
import {ClassicOverlayVideo} from './compositions/ClassicOverlayVideo';
import {defaultChronicleTemplate} from './lib/defaultChronicleTemplate';
import {ChronicleVideoProps, ClassicOverlayProps} from './lib/types';

const defaultChronicleProps: ChronicleVideoProps = {
  articleId: 'sample',
  draft: {
    main_line1: 'OpenAI 发布新模型',
    main_line2: '多模态能力再升级',
    sub_title: 'AI 快讯',
    summary: '小牛说：新模型在推理与视觉理解上均有提升，开发者 API 同步开放。',
    tags: '#OpenAI #多模态',
    highlight_keywords: ['OpenAI', '多模态'],
  },
  images: [
    {path: 'static/imgs/bg.png', duration: 3.5},
    {path: 'static/imgs/bg.png', duration: 3.5},
  ],
  audioPath: '',
  template: defaultChronicleTemplate,
};

const defaultClassicProps: ClassicOverlayProps = {
  summary: '这是一条用于 Remotion 预览的示例摘要。',
  main_line1: '突发！AI 行业',
  main_line2: '又有大动作',
  subtitle: '快讯',
  images: [{path: 'static/imgs/bg.png', duration: 3.5}],
  backgroundImagePath: 'static/imgs/bg.png',
  showSummary: true,
};

const clipDurationSec = (images: {duration: number}[]): number =>
  Math.max(0.1, images.reduce((sum, img) => sum + img.duration, 0));

const chronicleMetadata: CalculateMetadataFunction<ChronicleVideoProps> = ({props}) => {
  const fps = props.template?.canvas?.fps || 24;
  const intro = props.coverImagePath ? props.coverIntroDurationSec || 1 : 0;
  return {
    durationInFrames: Math.max(1, Math.round((intro + clipDurationSec(props.images)) * fps)),
    fps,
    width: props.template?.canvas?.width || 1080,
    height: props.template?.canvas?.height || 1920,
  };
};

const classicMetadata: CalculateMetadataFunction<ClassicOverlayProps> = ({props}) => {
  const intro = props.coverImagePath ? props.coverIntroDurationSec || 1 : 0;
  return {
    durationInFrames: Math.max(1, Math.round((intro + clipDurationSec(props.images)) * 24)),
    fps: 24,
    width: 1080,
    height: 1920,
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ChronicleVideo"
        component={ChronicleVideo}
        durationInFrames={Math.round(clipDurationSec(defaultChronicleProps.images) * 24)}
        fps={24}
        width={1080}
        height={1920}
        defaultProps={defaultChronicleProps}
        calculateMetadata={chronicleMetadata}
      />
      <Composition
        id="ClassicOverlayVideo"
        component={ClassicOverlayVideo}
        durationInFrames={Math.round(clipDurationSec(defaultClassicProps.images) * 24)}
        fps={24}
        width={1080}
        height={1920}
        defaultProps={defaultClassicProps}
        calculateMetadata={classicMetadata}
      />
    </>
  );
};
