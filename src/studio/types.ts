export type Scene = {
  start: number;
  end: number;
  label: string;
  narration: string;
  thumbnail: string;
  duration?: number;
  thumbnail_url?: string;
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
    duration: number;
    demo: boolean;
    revision: number;
    scenes: Scene[];
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
};
export type Playback = { url: string; poster_url?: string; scenes: Scene[]; expires_in: number };
