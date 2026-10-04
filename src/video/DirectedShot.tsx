import React, { useEffect, useState } from 'react';
import { fitTextOnNLines } from '@remotion/layout-utils';
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  spring,
  useCurrentFrame,
  useVideoConfig,
  delayRender,
  continueRender,
  cancelRender,
} from 'remotion';
import '@fontsource-variable/inter';
import type { ShotProps } from './LaunchShot';

export type MotionState = {
  beat: number;
  x: number;
  y: number;
  w: number;
  h: number;
  radius: number;
  rotation: number;
  opacity: number;
  ease: 'spring' | 'smooth' | 'linear' | 'hold';
};
export type MotionLayer = {
  id: string;
  kind: 'footage' | 'product' | 'detail-0' | 'detail-1' | 'detail-2' | 'text' | 'shape';
  states: MotionState[];
  text: string;
  color: string;
  size: number;
  weight: number;
  align: 'left' | 'center' | 'right';
  entrance: 'none' | 'words' | 'mask' | 'type';
};
export type ShotDirection = {
  purpose: string;
  composition: 'product' | 'detail' | 'type' | 'graphic' | 'split';
  entry: 'cut' | 'match';
  background: string;
  bpm: number;
  beats: number;
  layers: MotionLayer[];
  hits: { beat: number; kind: 'whoosh' | 'thump' | 'tick' }[];
};

const clamp = (value: number) => Math.max(0, Math.min(1, value));
const smooth = (t: number) => {
  const p = clamp(t);
  return p * p * (3 - 2 * p);
};

// Every state is a pure function of the requested frame. No wall clock or CSS animation.
function stateAt(layer: MotionLayer, frame: number, fps: number, bpm: number): MotionState {
  const beatFrame = (fps * 60) / bpm;
  const next = layer.states.findIndex((s) => s.beat * beatFrame > frame);
  if (next < 0) return layer.states[layer.states.length - 1];
  if (next === 0) return layer.states[0];
  const from = layer.states[next - 1];
  const to = layer.states[next];
  const local = frame - from.beat * beatFrame;
  const duration = (to.beat - from.beat) * beatFrame;
  const ratio = local / duration;
  const progress =
    to.ease === 'hold'
      ? 0
      : to.ease === 'linear'
        ? clamp(ratio)
        : to.ease === 'spring'
          ? spring({
              frame: local,
              fps,
              durationInFrames: duration,
              config: { damping: 22, stiffness: 170, mass: 0.8, overshootClamping: true },
            })
          : smooth(ratio);
  const state = { ...from };
  for (const property of ['x', 'y', 'w', 'h', 'radius', 'rotation', 'opacity'] as const)
    state[property] = from[property] + (to[property] - from[property]) * progress;
  return state;
}

function Type({ layer, frame, fps }: { layer: MotionLayer; frame: number; fps: number }) {
  if (layer.entrance === 'type')
    return <>{layer.text.slice(0, Math.floor(frame / (fps * 0.035)))}</>;
  if (layer.entrance === 'words')
    return (
      <>
        {layer.text.split(/\s+/).map((word, i) => {
          const p = smooth((frame - i * fps * 0.045) / (fps * 0.28));
          return (
            <span
              key={i}
              style={{
                display: 'inline-block',
                overflow: 'hidden',
                verticalAlign: 'top',
                paddingBottom: '.15em',
                marginBottom: '-.15em',
                marginRight: '.22em',
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  transform: `translateY(${(1 - p) * 110}%)`,
                  opacity: p,
                }}
              >
                {word}
              </span>
            </span>
          );
        })}
      </>
    );
  return (
    <span
      style={{
        display: 'block',
        clipPath:
          layer.entrance === 'mask'
            ? `inset(0 ${(1 - smooth(frame / (fps * 0.4))) * 100}% 0 0)`
            : undefined,
      }}
    >
      {layer.text}
    </span>
  );
}

export function DirectedShot(props: ShotProps) {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const direction = props.direction!;
  const [fontReady, setFontReady] = useState(false);
  const [fontHandle] = useState(() => delayRender('Loading motion typography'));
  useEffect(() => {
    document.fonts
      .load('600 100px "Inter Variable"')
      .then(() => {
        setFontReady(true);
        continueRender(fontHandle);
      })
      .catch(cancelRender);
    return () => continueRender(fontHandle);
  }, [fontHandle]);
  if (!fontReady) return null;
  // Reach the exact terminal geometry at the final encoded frame for reliable match cuts.
  const clock =
    frame === durationInFrames - 1 ? (direction.beats * fps * 60) / direction.bpm : frame;
  return (
    <AbsoluteFill
      style={{
        background: direction.background,
        overflow: 'hidden',
        fontFamily: 'Inter Variable, sans-serif',
      }}
    >
      {direction.layers.map((layer) => {
        const s = stateAt(layer, clock, fps, direction.bpm);
        const isText = layer.kind === 'text';
        const style: React.CSSProperties = {
          position: 'absolute',
          left: s.x * 1920,
          top: s.y * 1080,
          width: s.w * 1920,
          height: s.h * 1080,
          borderRadius: s.radius,
          opacity: s.opacity,
          transform: `rotate(${s.rotation}deg)`,
          overflow: isText ? 'visible' : 'hidden',
          background: layer.kind === 'shape' ? layer.color : undefined,
        };
        const src = layer.kind.startsWith('detail-')
          ? props.details[Number(layer.kind.slice(-1))]
          : props.product;
        const firstVisible = layer.states.findIndex((state) => state.opacity > 0);
        // Begin the type entrance WITH its opacity ramp, not after the ramp completes.
        const textStart = layer.states[Math.max(0, firstVisible - 1)]?.beat || 0;
        const naturalEntrance =
          fps *
          (layer.entrance === 'type'
            ? layer.text.length * 0.035
            : layer.entrance === 'words'
              ? layer.text.split(/\s+/).length * 0.045 + 0.28
              : 0.4);
        const remaining = durationInFrames - (textStart * fps * 60) / direction.bpm;
        const entranceFrames = Math.max(1, Math.min(naturalEntrance, remaining - fps * 0.8));
        const typeFrame =
          (Math.max(0, frame - (textStart * fps * 60) / direction.bpm) * naturalEntrance) /
          entranceFrames;
        const textLayout = isText
          ? fitTextOnNLines({
              text: layer.text,
              fontFamily: 'Inter Variable',
              fontWeight: layer.weight,
              letterSpacing: '-.045em',
              maxBoxWidth: Math.max(1, s.w * 1920 - 8),
              maxLines: Math.max(1, Math.min(4, Math.floor((s.h * 1080) / (layer.size * 1.08)))),
              maxFontSize: Math.min(layer.size, (s.h * 1080) / 1.08),
            })
          : null;
        return (
          <div key={layer.id} style={style}>
            {isText ? (
              <div
                data-motion-text={layer.id}
                style={{
                  color: layer.color,
                  fontSize: textLayout!.fontSize,
                  fontWeight: layer.weight,
                  textAlign: layer.align,
                  lineHeight: 1.08,
                  letterSpacing: '-.045em',
                  overflowWrap: 'break-word',
                }}
              >
                {textLayout!.lines.map((line, index) => (
                  <div key={index} style={{ whiteSpace: 'nowrap' }}>
                    <Type
                      layer={{ ...layer, text: line }}
                      frame={Math.max(0, typeFrame - index * 3)}
                      fps={fps}
                    />
                  </div>
                ))}
              </div>
            ) : layer.kind === 'shape' ? null : layer.kind === 'footage' && props.footage ? (
              <OffthreadVideo
                src={props.footage}
                muted
                style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              />
            ) : src ? (
              <Img src={src} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
            ) : null}
          </div>
        );
      })}
    </AbsoluteFill>
  );
}
