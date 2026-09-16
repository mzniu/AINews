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
  const cx = width / 2;
  const cy = height * 0.48;
  const tick = 14;

  const rings = [
    {rx: width * 0.26, ry: height * 0.144, sw: 1, alpha: 0.16},
    {rx: width * 0.4, ry: height * 0.216, sw: 2, alpha: 0.22},
    {rx: width * 0.56, ry: height * 0.302, sw: 1, alpha: 0.15},
    {rx: width * 0.74, ry: height * 0.398, sw: 1, alpha: 0.12},
  ];

  return (
    <AbsoluteFill style={{backgroundColor: bg}}>
      <svg width={width} height={height} style={{position: 'absolute', inset: 0}}>
        <defs>
          <radialGradient id="well" cx="50%" cy="48%" r="55%">
            <stop offset="0%" stopColor={glow} stopOpacity="0.72" />
            <stop offset="55%" stopColor={glow} stopOpacity="0.28" />
            <stop offset="100%" stopColor={bg} stopOpacity="1" />
          </radialGradient>
          <radialGradient id="core" cx="50%" cy="48%" r="35%">
            <stop offset="0%" stopColor={accent} stopOpacity="0.14" />
            <stop offset="100%" stopColor={accent} stopOpacity="0" />
          </radialGradient>
          <radialGradient id="vignette" cx="50%" cy="50%" r="70%">
            <stop offset="55%" stopColor="#000" stopOpacity="0" />
            <stop offset="100%" stopColor="#000" stopOpacity="0.42" />
          </radialGradient>
        </defs>

        <rect width={width} height={height} fill="url(#well)" />
        <rect width={width} height={height} fill="url(#core)" />

        {Array.from({length: Math.ceil(width / 54) + 1}).map((_, i) => {
          const x = i * 54;
          const major = i % 4 === 0;
          return (
            <line
              key={`gx-${i}`}
              x1={x}
              y1={0}
              x2={x}
              y2={height}
              stroke={major ? accent : accentDim}
              strokeOpacity={major ? 0.11 : 0.07}
              strokeWidth={1}
            />
          );
        })}
        {Array.from({length: Math.ceil(height / 48) + 1}).map((_, i) => {
          const y = i * 48;
          const major = i % 4 === 0;
          return (
            <line
              key={`gy-${i}`}
              x1={0}
              y1={y}
              x2={width}
              y2={y}
              stroke={major ? accent : accentDim}
              strokeOpacity={major ? 0.11 : 0.07}
              strokeWidth={1}
            />
          );
        })}

        {rings.map((ring, i) => (
          <ellipse
            key={`ring-${i}`}
            cx={cx}
            cy={cy}
            rx={ring.rx}
            ry={ring.ry}
            fill="none"
            stroke={i % 2 === 0 ? accent : accentDim}
            strokeOpacity={ring.alpha}
            strokeWidth={ring.sw}
          />
        ))}

        <line x1={cx} y1={cy - height * 0.144 - tick} x2={cx} y2={cy - height * 0.144 + tick} stroke={accent} strokeOpacity={0.28} />
        <line x1={cx} y1={cy + height * 0.144 - tick} x2={cx} y2={cy + height * 0.144 + tick} stroke={accent} strokeOpacity={0.28} />
        <line x1={cx - width * 0.2 - tick} y1={cy} x2={cx - width * 0.2 + tick} y2={cy} stroke={accent} strokeOpacity={0.28} />
        <line x1={cx + width * 0.2 - tick} y1={cy} x2={cx + width * 0.2 + tick} y2={cy} stroke={accent} strokeOpacity={0.28} />

        {Array.from({length: 15}).map((_, i) => {
          const idx = i - 7;
          const xBottom = cx + idx * width * 0.11;
          return (
            <line
              key={`persp-${i}`}
              x1={cx}
              y1={height * 0.6}
              x2={xBottom}
              y2={height + 30}
              stroke={accentDim}
              strokeOpacity={0.16}
              strokeWidth={1}
            />
          );
        })}

        {[0.76, 0.82, 0.88, 0.93, 0.97].map((frac) => {
          const y = height * frac;
          const span = width * Math.max(0.18, frac - 0.52);
          return (
            <line
              key={`floor-${frac}`}
              x1={cx - span}
              y1={y}
              x2={cx + span}
              y2={y}
              stroke={accentDim}
              strokeOpacity={0.13}
              strokeWidth={1}
            />
          );
        })}

        <rect width={width} height={height} fill="url(#vignette)" />

        <rect
          x={inset}
          y={inset}
          width={width - inset * 2}
          height={height - inset * 2}
          fill="none"
          stroke={frame}
          strokeWidth={2}
        />
        {[
          [inset, inset],
          [width - inset - tick, inset],
          [inset, height - inset - tick],
          [width - inset - tick, height - inset - tick],
        ].map(([x, y], i) => (
          <rect key={`corner-${i}`} x={x} y={y} width={tick} height={tick} fill="none" stroke={accentDim} strokeWidth={2} />
        ))}
      </svg>

      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'repeating-linear-gradient(0deg, rgba(255,255,255,0.02) 0px, rgba(255,255,255,0.02) 1px, transparent 1px, transparent 3px)',
          opacity: 0.45,
          pointerEvents: 'none',
        }}
      />
    </AbsoluteFill>
  );
};
