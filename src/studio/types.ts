export type Scene = {
  start: number;
  end: number;
  label: string;
  narration: string;
  thumbnail: string;
  duration?: number;
  thumbnail_url?: string;
  timeline_start?: number;
  kind?: 'browser' | 'title' | 'generated';
};
export type TimelineClip = {
  id: string;
  kind: 'browser' | 'title' | 'generated';
  scene_id?: string;
  asset_id?: string;
  label: string;
  narration: string;
  headline: string;
  subtitle: string;
  layout: 'hook' | 'benefit' | 'outro';
  duration: number;
  camera?: 'wide' | 'push';
  motion?: 'none' | 'reveal' | 'panels' | 'detail' | 'resolve' | 'directed';
  direction?: import('../video/DirectedShot').ShotDirection;
  trim_start: number;
  trim_end?: number | null;
  enabled: boolean;
  transition: 'cut' | 'fade' | 'dissolve';
};
export type AnimationAsset = {
  id: string;
  status: string;
  provider: string;
  duration: number;
  prompt: string;
  error?: string;
  thumbnail_url?: string;
  url?: string;
};
export type Video = {
  id: string;
  title: string;
  status: string;
  created_at: string;
  payload: {
    url: string;
    host: string;
    brief: string;
    voice: string;
    music: 'ambient' | 'momentum' | 'none';
    theme: 'midnight' | 'paper';
    progress: number;
    updated_at?: string;
    duration: number;
    demo: boolean;
    revision: number;
    scenes: Scene[];
    timeline?: TimelineClip[];
    assets?: AnimationAsset[];
    rendered_scenes?: Scene[];
    use_uploaded_narration?: boolean;
    format?: 'launch' | 'walkthrough';
    events: { at: string; stage: string; message: string }[];
    export?: { duration_seconds: number; bytes: number; resolution: string; fps: number };
    narration_source?: string;
    uploaded_narration?: boolean;
  };
};
export type Voice = {
  id: string;
  name: string;
  description: string;
  kind: 'stock' | 'custom';
  provider: string;
};
export type Features = {
  reasoning: boolean;
  narration: boolean;
  voice_cloning: boolean;
  video_generation?: { sora: boolean; veo: boolean };
};
export type Playback = {
  url: string;
  poster_url?: string;
  scenes: Scene[];
  assets?: AnimationAsset[];
  expires_in: number;
};
