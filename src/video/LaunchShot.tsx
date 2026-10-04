import React from 'react';
import { AbsoluteFill, Img, OffthreadVideo, useCurrentFrame, useVideoConfig } from 'remotion';
import '@fontsource-variable/inter';

export type MotionPreset = 'reveal' | 'panels' | 'detail' | 'resolve';
export type ShotProps = {
  preset: MotionPreset;
  theme: 'paper' | 'midnight';
  headline: string;
  subtitle: string;
  product: string;
  details: string[];
  footage?: string;
  frames: number;
  focus?: { x: number; y: number };
};

const clamp = (n: number) => Math.min(1, Math.max(0, n));
const ease = (n: number) => 1 - Math.pow(1 - clamp(n), 4);
const mix = (a: number, b: number, n: number) => a + (b - a) * n;
const segment = (t: number, a: number, b: number) => ease((t - a) / (b - a));

function Words({
  text,
  frame,
  size,
  color,
}: {
  text: string;
  frame: number;
  size: number;
  color: string;
}) {
  return (
    <div
      style={{
        fontSize: size,
        fontWeight: 650,
        letterSpacing: '-0.065em',
        lineHeight: 1.04,
        color,
        display: 'flex',
        flexWrap: 'wrap',
        gap: '0 .24em',
      }}
    >
      {text.split(/\s+/).map((word, i) => {
        const p = ease((frame - i * 2) / 17);
        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              overflow: 'hidden',
              paddingBottom: '.12em',
              marginBottom: '-.12em',
            }}
          >
            <span
              style={{
                display: 'inline-block',
                transform: `translateY(${(1 - p) * 115}%) rotate(${(1 - p) * 4}deg)`,
                opacity: p,
              }}
            >
              {word}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function Product({ props, style }: { props: ShotProps; style?: React.CSSProperties }) {
  return (
    <div style={{ position: 'absolute', width: 1920, height: 1080, overflow: 'hidden', ...style }}>
      {props.footage ? (
        <OffthreadVideo
          src={props.footage}
          muted
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      ) : (
        <Img src={props.product} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      )}
    </div>
  );
}

export function LaunchShot(props: ShotProps) {
  const f = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = f / Math.max(1, durationInFrames - 1);
  const dark = props.theme === 'midnight';
  const bg = dark ? '#0a0a0e' : '#f7f8fc';
  const ink = dark ? '#f7f6f2' : '#19191f';
  const accent = dark ? '#c4b5ff' : '#5144ed';
  const muted = dark ? '#9995a8' : '#73717d';
  const titleSize = Math.min(146, 680 / Math.sqrt(Math.max(1, props.headline.length)));
  const handoff = segment(t, 0.73, 1);
  const focus = props.focus || { x: 0.55, y: 0.5 };

  if (props.preset === 'detail') {
    const move = segment(t, 0.04, 0.34);
    const release = segment(t, 0.7, 1);
    const zoom = 1 + 0.62 * move * (1 - release);
    const travel = move * (1 - release);
    const offset = (center: number, size: number) =>
      Math.max(
        (-(zoom - 1) * size) / 2,
        Math.min(((zoom - 1) * size) / 2, (0.5 - center) * size * zoom * travel),
      );
    return (
      <AbsoluteFill style={{ background: bg }}>
        <Product
          props={props}
          style={{
            transform: `translate(${offset(focus.x, 1920)}px, ${offset(focus.y, 1080)}px) scale(${zoom})`,
            transformOrigin: '50% 50%',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            boxShadow: `inset 0 0 ${100 * move * (1 - release)}px #0000000c`,
            pointerEvents: 'none',
          }}
        />
      </AbsoluteFill>
    );
  }

  if (props.preset === 'resolve') {
    const p = segment(t, 0, 0.4);
    return (
      <AbsoluteFill
        style={{
          background: bg,
          color: ink,
          fontFamily: 'Inter Variable, sans-serif',
          overflow: 'hidden',
        }}
      >
        {props.product && (
          <Product
            props={{ ...props, footage: undefined }}
            style={{
              transform: `translate(860px, 170px) perspective(1600px) rotateY(-14deg) rotateZ(-5deg) scale(${mix(0.48, 0.52, p)})`,
              transformOrigin: '0 0',
              opacity: 0.2,
            }}
          />
        )}
        <div style={{ position: 'absolute', left: 120, right: 260, top: 350 }}>
          <Words text={props.headline} frame={f} size={titleSize} color={ink} />
        </div>
        <div
          style={{
            position: 'absolute',
            left: 125,
            top: 760,
            color: muted,
            fontSize: 30,
            opacity: segment(t, 0.2, 0.45),
            transform: `translateY(${24 * (1 - p)}px)`,
          }}
        >
          {props.subtitle}
        </div>
        <div
          style={{
            position: 'absolute',
            left: 125,
            top: 858,
            height: 8,
            width: 116 * p,
            background: accent,
          }}
        />
      </AbsoluteFill>
    );
  }

  // Both openings finish on the exact product canvas, ready for the next recorded shot.
  if (f === durationInFrames - 1)
    return (
      <AbsoluteFill>
        <Product props={{ ...props, footage: undefined }} />
      </AbsoluteFill>
    );

  if (props.preset === 'panels') {
    const leave = segment(t, 0.58, 0.84);
    const rows = props.details.length
      ? props.details.slice(0, 3)
      : [props.product, props.product, props.product];
    return (
      <AbsoluteFill
        style={{
          background: bg,
          fontFamily: 'Inter Variable, sans-serif',
          overflow: 'hidden',
          perspective: 1800,
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `radial-gradient(ellipse at 70% 45%, ${accent}24, transparent 65%)`,
          }}
        />
        <Product
          props={{ ...props, footage: undefined }}
          style={{
            transform: `translate(${mix(450, 0, handoff)}px, ${mix(160, 0, handoff)}px) scale(${mix(0.8, 1, handoff)})`,
            transformOrigin: '0 0',
            opacity: mix(0.08, 1, handoff),
            filter: `blur(${8 * (1 - handoff)}px)`,
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: 110,
            top: 130,
            width: 940,
            opacity: 1 - leave,
            transform: `translateY(${-100 * leave}px)`,
          }}
        >
          <Words text={props.headline} frame={f} size={titleSize} color={ink} />
        </div>
        {rows.map((src, i) => {
          const enter = segment(t, 0.06 + i * 0.075, 0.38 + i * 0.075);
          const x = [1020, 660, 190][i];
          const y = [370, 570, 660][i];
          return (
            <div
              key={i}
              style={{
                position: 'absolute',
                left: x,
                top: y,
                width: [740, 830, 630][i],
                height: [360, 380, 300][i],
                borderRadius: 22,
                overflow: 'hidden',
                background: '#fff',
                boxShadow: '0 28px 100px #00000038',
                border: '1px solid #ffffff66',
                opacity: enter * (1 - leave),
                transform: `translate(${(1 - enter) * 380 + leave * (i - 1) * 650}px, ${(1 - enter) * 180 + leave * 280}px) rotateX(${mix(16, 0, enter)}deg) rotateY(${mix(-14, -3, enter)}deg) rotateZ(${[-5, 3, -3][i]}deg) scale(${mix(0.88, 1, enter)})`,
              }}
            >
              <Img src={src} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
            </div>
          );
        })}
        <div
          style={{
            position: 'absolute',
            left: 114,
            bottom: 72,
            fontSize: 24,
            color: muted,
            opacity: 1 - leave,
          }}
        >
          {props.subtitle}
        </div>
      </AbsoluteFill>
    );
  }

  const enter = segment(t, 0, 0.34);
  const textOut = segment(t, 0.43, 0.66);
  const screenScale = mix(mix(0.69, 0.77, enter), 1, handoff);
  return (
    <AbsoluteFill
      style={{ background: bg, fontFamily: 'Inter Variable, sans-serif', overflow: 'hidden' }}
    >
      <div
        style={{
          position: 'absolute',
          width: 1300,
          height: 1000,
          left: 650,
          top: 250,
          borderRadius: '50%',
          background: accent,
          opacity: 0.12,
          filter: 'blur(150px)',
          transform: `scale(${mix(0.6, 1.3, enter)})`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 100,
          right: 140,
          top: 105,
          zIndex: 2,
          opacity: 1 - textOut,
          transform: `translateY(${-110 * textOut}px)`,
        }}
      >
        <Words text={props.headline} frame={f} size={titleSize} color={ink} />
      </div>
      <Product
        props={{ ...props, footage: undefined }}
        style={{
          left: 0,
          top: 0,
          borderRadius: 24 * (1 - handoff),
          boxShadow: '0 50px 120px #00000036',
          transformOrigin: '0 0',
          transform: `translate(${mix(mix(310, 230, enter), 0, handoff)}px, ${mix(mix(570, 430, enter), 0, handoff)}px) perspective(1800px) rotateX(${mix(13 * (1 - enter), 0, handoff)}deg) rotateY(${mix(-8 * (1 - enter), 0, handoff)}deg) rotateZ(${mix(-4 * (1 - enter), 0, handoff)}deg) scale(${screenScale})`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: 108,
          top: 930,
          color: muted,
          fontSize: 24,
          opacity: (1 - handoff) * (1 - textOut),
        }}
      >
        {props.subtitle}
      </div>
    </AbsoluteFill>
  );
}
