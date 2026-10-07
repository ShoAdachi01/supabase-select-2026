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
import '@fontsource/instrument-serif/400.css';
import '@fontsource-variable/jetbrains-mono';
import { contentBox, drifted, project } from './camera';
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
  cam_x?: number;
  cam_y?: number;
  cam_zoom?: number;
  focus?: string | null;
  elevation?: number;
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
  depth?: number;
  shape?: 'rect' | 'line' | 'segments' | 'ring';
  stroke?: number;
  count?: number;
  gap?: number;
  font?: 'sans' | 'display' | 'mono';
  target_layer?: string | null;
  target?: string | null;
  target_x?: number | null;
  target_y?: number | null;
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
  drift?: { x: number; y: number; zoom: number };
  backdrop?: {
    kind: 'flat' | 'radial';
    x: number;
    y: number;
    color2: string | null;
    grain: number;
  };
};

const FONTS = {
  sans: { family: 'Inter Variable', weight: null, spacing: '-.045em' },
  display: { family: 'Instrument Serif', weight: 400, spacing: '-.02em' },
  mono: { family: 'JetBrains Mono Variable', weight: null, spacing: '0' },
} as const;
const NO_DRIFT = { x: 0, y: 0, zoom: 0 };

type Camera = MotionState & { cam_x: number; cam_y: number; cam_zoom: number; elevation: number };
const withCamera = (state: MotionState): Camera => ({
  ...state,
  cam_x: state.cam_x ?? 0.5,
  cam_y: state.cam_y ?? 0.5,
  cam_zoom: state.cam_zoom ?? 1,
  elevation: state.elevation ?? 0,
});

const clamp = (value: number) => Math.max(0, Math.min(1, value));
const smooth = (t: number) => {
  const p = clamp(t);
  return p * p * (3 - 2 * p);
};

// Every state is a pure function of the requested frame. No wall clock or CSS animation.
function stateAt(layer: MotionLayer, frame: number, fps: number, bpm: number): Camera {
  const beatFrame = (fps * 60) / bpm;
  const next = layer.states.findIndex((s) => s.beat * beatFrame > frame);
  if (next < 0) return withCamera(layer.states[layer.states.length - 1]);
  if (next === 0) return withCamera(layer.states[0]);
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
  const a = withCamera(from);
  const b = withCamera(to);
  const state = { ...a };
  for (const property of [
    'x',
    'y',
    'w',
    'h',
    'radius',
    'rotation',
    'opacity',
    'cam_x',
    'cam_y',
    'cam_zoom',
    'elevation',
  ] as const)
    state[property] = a[property] + (b[property] - a[property]) * progress;
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
            <React.Fragment key={i}>
              <span
                style={{
                  display: 'inline-block',
                  overflow: 'hidden',
                  verticalAlign: 'top',
                  paddingBottom: '.15em',
                  marginBottom: '-.15em',
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
              {i < layer.text.split(/\s+/).length - 1 ? ' ' : null}
            </React.Fragment>
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

function ShapeBody({
  shape,
  color,
  stroke,
  count,
  gap,
  vertical,
}: {
  shape: NonNullable<MotionLayer['shape']>;
  color: string;
  stroke: number;
  count: number;
  gap: number;
  vertical: boolean;
}) {
  if (shape === 'line')
    return (
      <div
        style={{
          position: 'absolute',
          background: color,
          ...(vertical
            ? { left: '50%', top: 0, bottom: 0, width: stroke, marginLeft: -stroke / 2 }
            : { top: '50%', left: 0, right: 0, height: stroke, marginTop: -stroke / 2 }),
        }}
      />
    );
  if (shape === 'segments')
    return (
      <div style={{ display: 'flex', flexDirection: vertical ? 'column' : 'row', height: '100%' }}>
        {Array.from({ length: Math.max(1, count) }, (_, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'stretch',
              justifyContent: 'center',
              flexDirection: vertical ? 'column' : 'row',
            }}
          >
            <div style={{ background: color, flex: `0 0 ${(1 - gap) * 100}%` }} />
          </div>
        ))}
      </div>
    );
  return null;
}

export function DirectedShot(props: ShotProps) {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const direction = props.direction!;
  const [fontReady, setFontReady] = useState(false);
  const [fontHandle] = useState(() => delayRender('Loading motion typography'));
  useEffect(() => {
    Promise.all([
      document.fonts.load('600 100px "Inter Variable"'),
      document.fonts.load('400 100px "Instrument Serif"'),
      document.fonts.load('500 100px "JetBrains Mono Variable"'),
    ])
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
  const drift = direction.drift ?? NO_DRIFT;
  const backdrop = direction.backdrop;
  const background =
    backdrop?.kind === 'radial' && backdrop.color2
      ? `radial-gradient(circle at ${backdrop.x * 100}% ${backdrop.y * 100}%, ${backdrop.color2} 0%, ${direction.background} 70%)`
      : direction.background;
  const seconds = clock / fps;
  const aspectOf = (kind: MotionLayer['kind']): readonly [number, number] =>
    kind.startsWith('detail-')
      ? (props.detail_sizes?.[Number(kind.slice(-1))] ?? [1920, 1080])
      : [props.viewport?.width ?? 1920, props.viewport?.height ?? 1080];
  const placed = (layer: MotionLayer) =>
    drifted(stateAt(layer, clock, fps, direction.bpm), drift, layer.depth ?? 1, seconds);
  return (
    <AbsoluteFill
      style={{
        background,
        overflow: 'hidden',
        fontFamily: 'Inter Variable, sans-serif',
      }}
    >
      {direction.layers.map((layer) => {
        const s = placed(layer);
        const font = FONTS[layer.font ?? 'sans'];
        const fontWeight = font.weight ?? layer.weight;
        const isText = layer.kind === 'text';
        const shape = layer.shape ?? 'rect';
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
          background: layer.kind === 'shape' && shape === 'rect' ? layer.color : undefined,
          boxShadow:
            s.elevation > 0
              ? `0 ${s.elevation * 40}px ${s.elevation * 90}px rgba(0,0,0,${0.12 + s.elevation * 0.22}), 0 ${s.elevation * 6}px ${s.elevation * 14}px rgba(0,0,0,${0.08 + s.elevation * 0.1})`
              : undefined,
        };
        const stroke = layer.stroke ?? 4;
        if (layer.kind === 'shape' && shape === 'ring') {
          style.background = 'transparent';
          style.border = `${stroke}px solid ${layer.color}`;
          style.boxSizing = 'border-box';
          style.overflow = 'visible';
          const target = direction.layers.find((l) => l.id === layer.target_layer);
          if (target && layer.target_x != null && layer.target_y != null) {
            const at = project(
              placed(target),
              aspectOf(target.kind),
              layer.target_x,
              layer.target_y,
            );
            style.left = at.x * 1920 - (s.w * 1920) / 2;
            style.top = at.y * 1080 - (s.h * 1080) / 2;
          }
        }
        const inner = (l: MotionLayer, st: Camera): React.CSSProperties => {
          const box = contentBox(st, aspectOf(l.kind));
          return {
            position: 'absolute',
            left: box.left,
            top: box.top,
            width: box.width,
            height: box.height,
          };
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
        // Preserve deliberate line breaks. Canvas fitting treats embedded newlines
        // differently from HTML whitespace, which previously pushed settled text off-canvas.
        const paragraphs = layer.text
          .split(/\n+/)
          .map((line) => line.trim())
          .filter(Boolean);
        const maxLines = Math.max(
          paragraphs.length,
          Math.min(4, Math.floor((s.h * 1080) / (layer.size * 1.08))),
        );
        const layouts = isText
          ? paragraphs.map((text) =>
              fitTextOnNLines({
                text: text.replace(/\s+/g, ' '),
                fontFamily: font.family,
                fontWeight,
                letterSpacing: font.spacing,
                maxBoxWidth: Math.max(1, s.w * 1920 - 8),
                maxLines: Math.max(1, Math.floor(maxLines / paragraphs.length)),
                maxFontSize: Math.min(layer.size, (s.h * 1080) / (Math.max(1, maxLines) * 1.08)),
              }),
            )
          : [];
        const textLayout = isText
          ? {
              fontSize: Math.min(...layouts.map((layout) => layout.fontSize)),
              lines: layouts.flatMap((layout) => layout.lines),
            }
          : null;
        return (
          <div key={layer.id} style={style}>
            {isText ? (
              <div
                data-motion-text={layer.id}
                style={{
                  color: layer.color,
                  fontSize: textLayout!.fontSize,
                  fontFamily: `"${font.family}", sans-serif`,
                  fontWeight,
                  textAlign: layer.align,
                  lineHeight: 1.08,
                  letterSpacing: font.spacing,
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
            ) : layer.kind === 'shape' ? (
              <ShapeBody
                shape={shape}
                color={layer.color}
                stroke={stroke}
                count={layer.count ?? 8}
                gap={layer.gap ?? 0.4}
                vertical={s.h > s.w}
              />
            ) : layer.kind === 'footage' && props.footage ? (
              <div style={inner(layer, s)}>
                <OffthreadVideo
                  src={props.footage}
                  muted
                  style={{ width: '100%', height: '100%' }}
                />
              </div>
            ) : src ? (
              <div style={inner(layer, s)}>
                <Img src={src} style={{ width: '100%', height: '100%' }} />
              </div>
            ) : null}
          </div>
        );
      })}
      {backdrop && backdrop.grain > 0 ? (
        <svg
          width="100%"
          height="100%"
          style={{ position: 'absolute', inset: 0, mixBlendMode: 'overlay', pointerEvents: 'none' }}
        >
          <filter id="g">
            <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed={frame} />
          </filter>
          <rect width="100%" height="100%" filter="url(#g)" opacity={backdrop.grain} />
        </svg>
      ) : null}
    </AbsoluteFill>
  );
}
