import React from 'react';
import {AbsoluteFill} from 'remotion';
import {hexToRgb} from '../lib/colors';

type Props = {
  width: number;
  height: number;
  palette: Record<string, string | undefined>;
};

export const TechBackdrop: React.FC<Props> = ({width, height, palette}) => {
  const bg = hexToRgb(palette.bg, 'rgb(7, 11, 16)');
  const glow = hexToRgb(palette.bg_glow, 'rgb(22, 90, 130)');
  const accent = hexToRgb(palette.accent, 'rgb(61, 220, 255)');
  const accentDim = hexToRgb(palette.accent_dim, 'rgb(26, 106, 138)');
  const frame = hexToRgb(palette.frame, accentDim);

  const inset = Math.round(width * 0.024);

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse 80% 70% at 50% 48%, ${glow} 0%, ${bg} 72%)`,
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(${accentDim}33 1px, transparent 1px),
            linear-gradient(90deg, ${accentDim}33 1px, transparent 1px)
          `,
          backgroundSize: '54px 48px',
          opacity: 0.55,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '48%',
          width: width * 0.52,
          height: height * 0.36,
          transform: 'translate(-50%, -50%)',
          borderRadius: '50%',
          border: `2px solid ${accent}66`,
          boxShadow: `0 0 0 1px ${accentDim}55, 0 0 80px ${glow}55`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: inset,
          top: inset,
          right: inset,
          bottom: inset,
          border: `2px solid ${frame}`,
          pointerEvents: 'none',
        }}
      />
    </AbsoluteFill>
  );
};
