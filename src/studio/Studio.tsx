import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  ArrowDownToLine,
  ArrowRight,
  AudioLines,
  Check,
  ChevronDown,
  ChevronLeft,
  CircleHelp,
  Clapperboard,
  Code2,
  Copy,
  ExternalLink,
  Film,
  Globe2,
  LayoutGrid,
  Link2,
  LoaderCircle,
  LockKeyhole,
  Mic,
  MoreHorizontal,
  MousePointer2,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Square,
  Upload,
  WandSparkles,
  X,
} from 'lucide-react';
import { accessToken, api, initialize } from '../api';
import type { Features, Playback, TimelineClip, Video, Voice } from './types';
import TimelineEditor, { initialClips, newTitle } from './TimelineEditor';

const DEMO_BRIEF =
  'Show how Meridian brings projects together. Open Projects, explore the Website refresh project, switch to its Board, and finish with Analytics. Explain the benefit of a clearer view of team progress.';
const BUSY = new Set([
  'queued',
  'exploring',
  'recording',
  'scripting',
  'narrating',
  'rendering',
  'generating',
]);
const duration = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;

function Logo({ small = false }: { small?: boolean }) {
  return (
    <div className={`logo ${small ? 'small' : ''}`}>
      <span>
        <Clapperboard size={small ? 16 : 20} strokeWidth={1.7} />
      </span>
      {!small && <>cutroom</>}
    </div>
  );
}

function MiniApp() {
  return (
    <div className="mini-browser">
      <div className="mini-toolbar">
        <i />
        <i />
        <i />
        <span>meridian.app / projects</span>
      </div>
      <div className="mini-app">
        <div className="mini-sidebar">
          <b>m &nbsp;meridian</b>
          <span>⌂ &nbsp; Overview</span>
          <span className="active">▦ &nbsp; Projects</span>
          <span>↗ &nbsp; Analytics</span>
          <small>STUDIO WORKSPACE</small>
          <span>◌ &nbsp; Design studio</span>
          <span>◌ &nbsp; Product team</span>
        </div>
        <div className="mini-content">
          <div className="mini-top">
            Workspace &nbsp; / &nbsp; <b>Projects</b>
            <span>Studio team ⌄</span>
          </div>
          <h3>
            A little clarity.
            <br />A lot of momentum.
          </h3>
          <p>A clear home for every idea, task, and team.</p>
          <div className="mini-projects">
            {['Website refresh', 'Mobile experience', 'Brand system'].map((name, index) => (
              <div key={name}>
                <i>{['◈', '▤', '✳'][index]}</i>
                <b>{name}</b>
                <p>
                  {
                    [
                      'A thoughtful new home for our brand.',
                      'Small screens. A bigger experience.',
                      'One language for everything we make.',
                    ][index]
                  }
                </p>
                <div className="mini-progress">
                  <span style={{ width: `${[72, 45, 91][index]}%` }} />
                </div>
                <small>{[72, 45, 91][index]}% complete</small>
                <div className="mini-avatars">
                  <i>AC</i>
                  <i>JL</i>
                  <i>MK</i>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <MousePointer2 className="mini-cursor" size={30} fill="white" />
    </div>
  );
}

export default function Studio() {
  const [tab, setTab] = useState<'videos' | 'voices' | 'agents'>('videos');
  const [creating, setCreating] = useState(false);
  const [videos, setVideos] = useState<Video[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [features, setFeatures] = useState<Features>({
    reasoning: false,
    narration: false,
    voice_cloning: false,
  });
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [playback, setPlayback] = useState<Playback | null>(null);
  const [posters, setPosters] = useState<Record<string, string>>({});
  const [clips, setClips] = useState<TimelineClip[]>([]);
  const [audioSource, setAudioSource] = useState<'generated' | 'uploaded'>('generated');
  const [planning, setPlanning] = useState(false);
  const [animationProvider, setAnimationProvider] = useState<'veo' | 'sora'>('veo');
  const [animationPrompt, setAnimationPrompt] = useState(
    'Ivory background, coral and sage geometric panels gently organizing into one elegant frame. Soft studio lighting, precise smooth motion. End on a clean ivory background for a dissolve into the product.',
  );
  const [voice, setVoice] = useState('none');
  const [music, setMusic] = useState<'ambient' | 'momentum' | 'none'>('momentum');
  const [theme, setTheme] = useState<'midnight' | 'paper'>('midnight');
  const [editorTab, setEditorTab] = useState<'script' | 'style' | 'animation' | 'activity'>(
    'script',
  );
  const [copied, setCopied] = useState('');
  const [tokenVisible, setTokenVisible] = useState(false);
  const [token, setToken] = useState('');
  const [previewing, setPreviewing] = useState('');
  const [voiceModal, setVoiceModal] = useState(false);
  const [consent, setConsent] = useState(false);
  const [voiceName, setVoiceName] = useState('My voice');
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    url: '',
    title: '',
    brief: '',
    creative_direction: '',
    reference_urls: '',
    username: '',
    password: '',
    login_url: '',
    credentials: false,
    duration: 30,
    format: 'launch' as 'launch' | 'walkthrough',
  });
  const videoElement = useRef<HTMLVideoElement>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const job = videos.find((v) => v.id === selected);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [tab, creating, selected]);

  async function refresh() {
    const [items, narrators, config] = await Promise.all([
      api<Video[]>('/api/videos'),
      api<Voice[]>('/api/voices'),
      fetch('/api/config').then((r) => r.json()),
    ]);
    setVideos((current) =>
      items.map((item) => {
        const existing = current.find((v) => v.id === item.id);
        return existing?.payload.updated_at &&
          item.payload.updated_at &&
          existing.payload.updated_at > item.payload.updated_at
          ? existing
          : item;
      }),
    );
    setVoices(narrators);
    setFeatures(config.video);
  }
  useEffect(() => {
    let active = true;
    initialize()
      .then(async () => {
        await refresh();
        if (active) setReady(true);
      })
      .catch((e) => setError(e.message));
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!ready) return;
    const timer = setInterval(() => refresh().catch((e) => setError(e.message)), 3000);
    return () => clearInterval(timer);
  }, [ready]);
  useEffect(() => {
    for (const video of videos) {
      const key = `${video.id}-${video.payload.revision}`;
      if (video.status === 'complete' && !posters[key]) {
        api<Playback>(`/api/videos/${video.id}/playback`)
          .then((info) => {
            if (info.scenes[0]?.thumbnail_url)
              setPosters((current) => ({ ...current, [key]: info.scenes[0].thumbnail_url! }));
          })
          .catch(() => {});
      }
    }
  }, [videos, posters]);
  useEffect(() => {
    if (!job) return;
    setVoice(job.payload.voice);
    setMusic(job.payload.music);
    setTheme(job.payload.theme);
    setClips(job.payload.timeline || initialClips(job.payload.scenes));
    setAudioSource(
      job.payload.uploaded_narration && job.payload.use_uploaded_narration !== false
        ? 'uploaded'
        : 'generated',
    );
  }, [job?.id, job?.payload.revision, job?.payload.scenes.length]);
  useEffect(() => {
    let active = true;
    setPlayback(null);
    if (job?.status === 'complete') {
      api<Playback>(`/api/videos/${job.id}/playback`)
        .then((info) => {
          if (active) setPlayback(info);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    }
    return () => {
      active = false;
    };
  }, [job?.id, job?.status, job?.payload.revision]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 4500);
    return () => clearTimeout(timer);
  }, [notice]);

  async function create(demo = false) {
    setSaving(true);
    setError('');
    try {
      const result = await api<Video>('/api/videos', {
        url: demo ? `${location.origin}/sample/` : form.url,
        title: demo ? 'A clearer way to work' : form.title || 'Product walkthrough',
        brief: demo ? DEMO_BRIEF : form.brief,
        voice,
        music,
        theme,
        creative_direction: form.creative_direction,
        reference_urls: form.reference_urls
          .split(/\n/)
          .map((url) => url.trim())
          .filter(Boolean),
        duration: form.duration,
        format: form.format,
        demo,
        credentials:
          form.credentials && !demo
            ? { username: form.username, password: form.password, login_url: form.login_url }
            : null,
      });
      setForm((f) => ({ ...f, password: '' }));
      setVideos((v) => [result, ...v]);
      setSelected(result.id);
      setCreating(false);
      setTab('videos');
      setEditorTab('activity');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    await create();
  }
  async function rerender() {
    if (!job) return;
    setSaving(true);
    setError('');
    try {
      const result = await api<Video>('/api/videos/render', {
        video_id: job.id,
        clips,
        audio_source: audioSource,
        voice,
        music,
        theme,
      });
      setVideos((v) => v.map((item) => (item.id === job.id ? result : item)));
      setEditorTab('activity');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function download() {
    if (!playback || !job) return;
    setSaving(true);
    try {
      const response = await fetch(playback.url);
      if (!response.ok)
        throw new Error('The download link expired. Reopen the film and try again.');
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${job.title.replace(/[^\w -]/g, '') || 'cutroom'}-v${job.payload.revision}.mp4`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function planLaunch() {
    if (!job) return;
    setPlanning(true);
    setError('');
    try {
      const plan = await api<{ clips: TimelineClip[] }>(`/api/videos/${job.id}/launch-plan`, {});
      const titles = plan.clips.filter((c) => c.kind === 'title');
      const footage = clips.filter((c) => c.kind !== 'title');
      const middle = Math.min(2, footage.length);
      setClips([
        titles[0],
        ...footage.slice(0, middle),
        titles[1],
        ...footage.slice(middle),
        titles[2],
      ]);
      setNotice('Launch sequence added to your draft. Edit the headlines and render changes.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPlanning(false);
    }
  }
  async function generateAnimation() {
    if (!job) return;
    setSaving(true);
    setError('');
    try {
      const result = await api<Video>(`/api/videos/${job.id}/animations`, {
        provider: animationProvider,
        prompt: animationPrompt,
        seconds: 4,
      });
      setVideos((items) => items.map((v) => (v.id === job.id ? result : v)));
      setNotice('Generating a four-second visual. Your timeline draft stays intact.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function previewVoice(id: string, text?: string) {
    if (id === 'none') {
      setNotice('This style uses music and interaction sounds, with no voiceover.');
      return;
    }
    if (!features.narration && !id.includes('-')) {
      setNotice('Connect an OpenAI API key to hear the stock voices.');
      return;
    }
    setPreviewing(id);
    try {
      const response = await fetch('/api/voices/preview', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${await accessToken()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ voice: id, ...(text ? { text } : {}) }),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail);
      }
      const url = URL.createObjectURL(await response.blob());
      const audio = new Audio(url);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPreviewing('');
      };
      await audio.play();
    } catch (e) {
      setError((e as Error).message);
      setPreviewing('');
    }
  }
  async function uploadVoice() {
    if (!voiceFile) return;
    setSaving(true);
    setError('');
    try {
      const body = new FormData();
      body.set('name', voiceName);
      body.set('consent', String(consent));
      body.set('file', voiceFile);
      const result = await api<Voice>('/api/voices/upload', undefined, body);
      setVoices((v) => [...v, result]);
      setVoice(result.id);
      setVoiceModal(false);
      setVoiceFile(null);
      setConsent(false);
      setNotice('Your voice is ready to narrate.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function uploadNarration(file: File) {
    if (!job) return;
    try {
      const body = new FormData();
      body.set('file', file);
      await api(`/api/videos/${job.id}/narration`, undefined, body);
      await refresh();
      setAudioSource('uploaded');
      setNotice('Narration uploaded. Render changes to use your recording.');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function copy(text: string, key: string) {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(''), 2000);
  }
  function navigate(next: typeof tab) {
    setTab(next);
    setSelected(null);
    setCreating(false);
    setError('');
  }
  const completed = videos.filter((v) => v.status === 'complete');

  return (
    <div className="studio-shell">
      <aside className="studio-sidebar">
        <Logo />
        <button className="workspace-switch">
          <span className="workspace-avatar">S</span>
          <span>
            Studio workspace<small>Your personal studio</small>
          </span>
          <ChevronDown size={13} />
        </button>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          <button className={tab === 'videos' ? 'active' : ''} onClick={() => navigate('videos')}>
            <Film size={17} />
            My videos<span>{videos.length}</span>
          </button>
          <button className={tab === 'voices' ? 'active' : ''} onClick={() => navigate('voices')}>
            <AudioLines size={17} />
            Voice library
          </button>
          <button className={tab === 'agents' ? 'active' : ''} onClick={() => navigate('agents')}>
            <Code2 size={17} />
            Agent connector<span className="mcp-badge">MCP</span>
          </button>
        </nav>
        <div className="sidebar-note">
          <button onClick={() => navigate('agents')}>
            <Code2 size={16} /> Connect your agent <ArrowRight size={14} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <span className={`connection-dot ${ready ? 'online' : ''}`} />
          {ready
            ? 'Workspace connected'
            : error
              ? 'Workspace unavailable'
              : 'Connecting workspace…'}
          <button
            title="Refresh connection"
            onClick={() => refresh().catch((e) => setError(e.message))}
          >
            <RefreshCw size={12} />
          </button>
        </div>
        <div className="profile">
          <span>S</span>
          <div>
            Your studio<small>Make something worth watching.</small>
          </div>
          <MoreHorizontal size={17} />
        </div>
      </aside>
      <div className="studio-main">
        <header className="studio-topbar">
          <div>
            <span>Workspace</span>
            <span className="crumb-divider">/</span>
            <b>
              {tab === 'voices'
                ? 'Voice library'
                : tab === 'agents'
                  ? 'Agent connector'
                  : creating
                    ? 'New video'
                    : job
                      ? job.title
                      : 'My videos'}
            </b>
          </div>
          <div className="topbar-right">
            <span className="beta-label">EARLY ACCESS</span>
            <a href="/sample/" target="_blank" rel="noreferrer" title="Open the sample app">
              <ExternalLink size={15} />
            </a>
            <span className="top-avatar">S</span>
          </div>
        </header>
        {error && (
          <div className="message error" role="alert">
            <span>{error}</span>
            <button onClick={() => setError('')}>
              <X size={15} />
            </button>
          </div>
        )}
        {notice && (
          <div className="toast">
            <Check size={15} />
            {notice}
          </div>
        )}

        {tab === 'videos' && !creating && !job && (
          <div className="dashboard">
            <div className="page-heading">
              <div>
                <div className="eyebrow">YOUR WORKSPACE</div>
                <h1>Studio</h1>
                <p>Everything you need for your next launch.</p>
              </div>
              <button
                className="button dark"
                disabled={!ready}
                onClick={() => {
                  setCreating(true);
                  setVoice('marin');
                }}
              >
                <Plus size={16} />
                Create a video
              </button>
            </div>
            <section className="launch-hero">
              <div className="launch-symbol" aria-hidden="true">
                <Clapperboard size={28} strokeWidth={1.4} />
              </div>
              <h2>
                You built it.
                <br />
                <span>Now let it move.</span>
              </h2>
              <p>
                Turn your product into a video worth sharing.
                <br />A link, a little direction. Your agent handles the rest.
              </p>
              <form
                className="launch-link"
                onSubmit={(event) => {
                  event.preventDefault();
                  setCreating(true);
                }}
              >
                <Globe2 size={20} />
                <input
                  aria-label="Product link"
                  type="url"
                  placeholder="Paste your product link"
                  value={form.url}
                  onChange={(event) => setForm({ ...form, url: event.target.value })}
                />
                <button aria-label="Start your video" disabled={!ready}>
                  <ArrowRight size={20} />
                </button>
              </form>
              <div className="launch-shortcuts">
                <button
                  onClick={() => {
                    setForm({ ...form, format: 'launch' });
                    setCreating(true);
                  }}
                >
                  <Sparkles size={14} /> Feature launch
                </button>
                <button
                  onClick={() => {
                    setForm({ ...form, format: 'walkthrough' });
                    setCreating(true);
                  }}
                >
                  <Film size={14} /> Product walkthrough
                </button>
                <button onClick={() => navigate('agents')}>
                  <Code2 size={14} /> Create with your agent
                </button>
              </div>
              <button
                className="text-button sample-link"
                disabled={saving || !ready}
                onClick={() => create(true)}
              >
                {saving ? <LoaderCircle size={14} className="spin" /> : <Play size={12} />}
                Try a real capture of our sample app
              </button>
            </section>
            <div className="library-header">
              <div>
                <h2>
                  Your films <span>{videos.length}</span>
                </h2>
                <p>Every take, in one place.</p>
              </div>
              <div className="library-controls">
                <span>{completed.length} ready to share</span>
                <LayoutGrid size={15} />
              </div>
            </div>
            {videos.length ? (
              <div className="video-grid">
                {videos.map((item) => (
                  <button
                    className="video-card"
                    key={item.id}
                    onClick={() => {
                      setSelected(item.id);
                      setEditorTab(item.status === 'complete' ? 'script' : 'activity');
                    }}
                  >
                    <div className={`card-preview ${item.payload.theme}`}>
                      {posters[`${item.id}-${item.payload.revision}`] ? (
                        <img
                          className="actual-poster"
                          src={posters[`${item.id}-${item.payload.revision}`]}
                          alt={`${item.title} captured product screen`}
                        />
                      ) : (
                        <MiniApp />
                      )}
                      <span className={`status-chip ${item.status}`}>
                        <span />
                        {item.status === 'complete'
                          ? 'Ready to share'
                          : item.status === 'failed'
                            ? 'Needs another take'
                            : item.status === 'cancelled'
                              ? 'Cancelled'
                              : 'In the cutroom'}
                      </span>
                      <span className="card-play">
                        {BUSY.has(item.status) ? (
                          <LoaderCircle className="spin" size={20} />
                        ) : (
                          <Play size={19} fill="currentColor" />
                        )}
                      </span>
                    </div>
                    <div className="card-info">
                      <h3>{item.title}</h3>
                      <MoreHorizontal size={17} />
                      <p>
                        {item.payload.demo ? 'Meridian · Sample app' : item.payload.host}
                        <span>
                          {item.payload.export
                            ? duration(item.payload.export.duration_seconds)
                            : `${item.payload.progress}%`}{' '}
                          · 1080p
                        </span>
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="empty-library">
                <div>
                  <Film size={23} strokeWidth={1.3} />
                </div>
                <h3>Your next great demo starts here.</h3>
                <p>No recording setup. No perfect take. Just a link and an idea.</p>
                <button className="text-button" onClick={() => setCreating(true)}>
                  Create a video <ArrowRight size={14} />
                </button>
              </div>
            )}
            <footer className="dashboard-footer">
              <span>Made for the way you build.</span>
              <span>
                <LockKeyhole size={12} />
                Private workspace. Real product footage.
              </span>
            </footer>
          </div>
        )}

        {tab === 'videos' && creating && (
          <div className="create-page">
            <button className="back-button" onClick={() => setCreating(false)}>
              <ChevronLeft size={15} />
              Back to videos
            </button>
            <div className="page-heading">
              <div>
                <div className="eyebrow">LET’S MAKE A GOOD FIRST IMPRESSION</div>
                <h1>
                  A new take<span>.</span>
                </h1>
                <p>You bring the product. We’ll bring it to life.</p>
              </div>
            </div>
            <div className="create-layout">
              <form className="brief-form" onSubmit={submit}>
                <div className="form-section">
                  <div className="form-section-title">
                    <span>01</span>
                    <h2>The product</h2>
                  </div>
                  <label>
                    Deployed app link
                    <div className="input-icon">
                      <Link2 size={16} />
                      <input
                        type="url"
                        required
                        placeholder="https://your-product.com"
                        value={form.url}
                        onChange={(e) => setForm({ ...form, url: e.target.value })}
                      />
                    </div>
                  </label>
                  <label>
                    Film format
                    <select
                      value={form.format}
                      onChange={(e) =>
                        setForm({ ...form, format: e.target.value as typeof form.format })
                      }
                    >
                      <option value="launch">
                        Launch film · directed motion and product footage
                      </option>
                      <option value="walkthrough">Product walkthrough · footage only</option>
                    </select>
                  </label>
                  <label>
                    Video title
                    <input
                      placeholder="Meet your next favorite feature"
                      maxLength={100}
                      value={form.title}
                      onChange={(e) => setForm({ ...form, title: e.target.value })}
                    />
                  </label>
                  <button
                    type="button"
                    className="credentials-toggle"
                    onClick={() => setForm({ ...form, credentials: !form.credentials })}
                  >
                    <LockKeyhole size={14} />
                    {form.credentials ? 'Demo login added' : 'Does your app need a demo login?'}
                    <Plus size={14} />
                  </button>
                  {form.credentials && (
                    <div className="credential-fields">
                      <p>Use a demo account. Login happens before the final footage.</p>
                      <label>
                        Email or username
                        <input
                          autoComplete="off"
                          value={form.username}
                          onChange={(e) => setForm({ ...form, username: e.target.value })}
                        />
                      </label>
                      <label>
                        Password
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={form.password}
                          onChange={(e) => setForm({ ...form, password: e.target.value })}
                        />
                      </label>
                      <label>
                        Login page <small>optional</small>
                        <input
                          type="url"
                          placeholder="https://your-product.com/login"
                          value={form.login_url}
                          onChange={(e) => setForm({ ...form, login_url: e.target.value })}
                        />
                      </label>
                    </div>
                  )}
                </div>
                <div className="form-section">
                  <div className="form-section-title">
                    <span>02</span>
                    <h2>The story</h2>
                  </div>
                  <label>
                    What feature are we showing?
                    <textarea
                      required
                      minLength={8}
                      maxLength={3000}
                      rows={4}
                      placeholder="Show how a new user creates a project, adds their first task, and sees it on the board. Focus on how easy it is to get started."
                      value={form.brief}
                      onChange={(e) => setForm({ ...form, brief: e.target.value })}
                    />
                  </label>
                  <p className="field-hint">
                    Tell us what to demonstrate and why your audience cares.
                  </p>
                  {form.format === 'launch' && (
                    <>
                      <label>
                        Art direction <span className="field-hint">Optional</span>
                        <textarea
                          rows={2}
                          maxLength={2000}
                          placeholder="What should this feel like? Mention the audience, mood, typography, pacing, or what you like about your reference."
                          value={form.creative_direction}
                          onChange={(e) => setForm({ ...form, creative_direction: e.target.value })}
                        />
                      </label>
                      <label>
                        Reference links <span className="field-hint">Optional · up to three</span>
                        <textarea
                          rows={2}
                          maxLength={6002}
                          placeholder="One public video, image, or reference page URL per line"
                          value={form.reference_urls}
                          onChange={(e) => setForm({ ...form, reference_urls: e.target.value })}
                        />
                      </label>
                      <p className="field-hint">
                        We study the visual style, not the reference’s branding. Direct MP4, WebM,
                        and image links work best. If a page blocks access, we’ll tell you.
                      </p>
                    </>
                  )}
                  <label>
                    Target length
                    <div className="segmented">
                      {[30, 60, 90].map((n) => (
                        <button
                          type="button"
                          className={form.duration === n ? 'active' : ''}
                          key={n}
                          onClick={() => setForm({ ...form, duration: n })}
                        >
                          {n} seconds
                        </button>
                      ))}
                    </div>
                  </label>
                </div>
                <div className="form-section">
                  <div className="form-section-title">
                    <span>03</span>
                    <h2>The finishing touches</h2>
                  </div>
                  <div className="two-fields">
                    <label>
                      Narrator
                      <select value={voice} onChange={(e) => setVoice(e.target.value)}>
                        {voices.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.name}
                            {v.kind === 'custom' ? ' · Your voice' : ''}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Music
                      <select
                        value={music}
                        onChange={(e) => setMusic(e.target.value as typeof music)}
                      >
                        <option value="ambient">Ambient · calm & warm</option>
                        <option value="momentum">Momentum · light & upbeat</option>
                        <option value="none">No music</option>
                      </select>
                    </label>
                  </div>
                  <button type="button" className="text-button" onClick={() => setVoiceModal(true)}>
                    <Upload size={13} />
                    Add my own voice
                  </button>
                </div>
                {!features.reasoning && (
                  <div className="setup-note">
                    <Code2 size={16} />
                    <span>
                      The director needs an API key before filming your app. You can try the sample
                      capture now.
                    </span>
                  </div>
                )}
                <button
                  className="button coral generate-button"
                  disabled={saving || !ready || !features.reasoning}
                >
                  {saving ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}
                  Create my video <ArrowRight size={16} />
                </button>
                <p className="form-footnote">
                  <LockKeyhole size={11} />
                  Credentials stay out of your script and saved project.
                </p>
              </form>
              <div className="create-preview">
                <div className="preview-heading">
                  <span>THE LOOK</span>
                  <span>1080p · 16:9</span>
                </div>
                <div className={`style-preview ${theme}`}>
                  <div className="style-preview-title">
                    {form.title || 'Your product, in motion.'}
                  </div>
                  <MiniApp />
                  <div className="preview-caption">
                    A good story. A smooth demo. A little magic.
                  </div>
                </div>
                <div className="theme-options">
                  <button
                    className={theme === 'midnight' ? 'selected' : ''}
                    onClick={() => setTheme('midnight')}
                  >
                    <i className="midnight" />
                    Midnight {theme === 'midnight' && <Check size={13} />}
                  </button>
                  <button
                    className={theme === 'paper' ? 'selected' : ''}
                    onClick={() => setTheme('paper')}
                  >
                    <i className="paper" />
                    Paper {theme === 'paper' && <Check size={13} />}
                  </button>
                </div>
                <div className="included-list">
                  <h3>Every film comes with</h3>
                  {[
                    ['Actual product footage', 'Your agent clicks through the real app.'],
                    [
                      'A story that fits the screen',
                      'Narration written from what was demonstrated.',
                    ],
                    [
                      'The polish, already there',
                      'Smooth cursor, zooms, cuts, captions, and music.',
                    ],
                  ].map(([title, text]) => (
                    <div key={title}>
                      <Check size={15} />
                      <span>
                        <b>{title}</b>
                        <p>{text}</p>
                      </span>
                    </div>
                  ))}
                </div>
                <div className="sample-note">
                  <span>Want to see the whole flow first?</span>
                  <button
                    className="text-button"
                    disabled={saving || !ready}
                    onClick={() => create(true)}
                  >
                    Film our sample app <ArrowRight size={13} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {tab === 'videos' && job && (
          <div className="editor-page">
            <div className="editor-heading">
              <div>
                <button className="back-button" onClick={() => setSelected(null)}>
                  <ChevronLeft size={14} />
                  All videos
                </button>
                <h1>
                  {job.title}
                  <span className="version-label">v{job.payload.revision}</span>
                </h1>
                <p>
                  {job.payload.demo ? 'Meridian · Sample app' : job.payload.host} <span>·</span>{' '}
                  {job.payload.export
                    ? `${duration(job.payload.export.duration_seconds)} · 1080p · 30 fps`
                    : 'A little work behind the scenes.'}
                </p>
              </div>
              <button className="button dark" disabled={!playback || saving} onClick={download}>
                <ArrowDownToLine size={15} />
                Download MP4
              </button>
            </div>
            <div className="editor-layout">
              <div className="film-panel">
                <div className={`film-player ${job.payload.theme}`}>
                  {playback ? (
                    <video
                      key={`${job.id}-${job.payload.revision}`}
                      ref={videoElement}
                      src={playback.url}
                      poster={playback.poster_url || playback.scenes[0]?.thumbnail_url}
                      controls
                      playsInline
                      preload="metadata"
                    />
                  ) : (
                    <div className="processing-preview">
                      <MiniApp />
                      <div className="processing-shade">
                        <div className="processing-orbit">
                          {BUSY.has(job.status) ? (
                            <LoaderCircle size={28} className="spin" />
                          ) : (
                            <Film size={28} />
                          )}
                        </div>
                        <h3>
                          {job.status === 'failed'
                            ? 'This take needs another try.'
                            : job.status === 'cancelled'
                              ? 'Take cancelled.'
                              : 'A good take takes a moment.'}
                        </h3>
                        <p>{job.payload.events.at(-1)?.message}</p>
                        {BUSY.has(job.status) && (
                          <div className="render-progress">
                            <span style={{ width: `${job.payload.progress}%` }} />
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
                <div className="player-meta">
                  <span>
                    <span
                      className={`connection-dot ${job.status === 'complete' ? 'online' : ''}`}
                    />
                    {job.status === 'complete'
                      ? 'Ready to share'
                      : job.status === 'failed'
                        ? 'Needs attention'
                        : job.status === 'cancelled'
                          ? 'Cancelled'
                          : `${job.status[0].toUpperCase()}${job.status.slice(1)} · ${job.payload.progress}%`}
                  </span>
                  <span>
                    {job.payload.theme === 'midnight' ? 'Midnight' : 'Paper'} /{' '}
                    {voices.find((v) => v.id === job.payload.voice)?.name || 'Custom voice'}
                  </span>
                </div>
                {job.payload.demo && (
                  <div className="demo-disclosure">
                    <CircleHelp size={14} />
                    <span>
                      This sample films Meridian, a fictional project app.
                      {job.payload.narration_source
                        ? ` Narrator: ${job.payload.narration_source}.`
                        : ''}
                    </span>
                  </div>
                )}
                <div className="timeline-heading">
                  <h3>The storyboard</h3>
                  <span>{(playback?.scenes || job.payload.scenes).length} scenes</span>
                </div>
                <div className="scene-strip">
                  {(playback?.scenes || job.payload.scenes).map((scene, i) => (
                    <button
                      key={i}
                      className="scene-tile"
                      onClick={() => {
                        if (videoElement.current)
                          videoElement.current.currentTime =
                            scene.timeline_start ??
                            (playback?.scenes || job.payload.scenes)
                              .slice(0, i)
                              .reduce((n, s) => n + (s.duration || 0), 0);
                      }}
                    >
                      <div>
                        {scene.thumbnail_url ? (
                          <img src={scene.thumbnail_url} alt={scene.label} />
                        ) : (
                          <MiniApp />
                        )}
                        <span>{String(i + 1).padStart(2, '0')}</span>
                      </div>
                      <b>{scene.label}</b>
                      <small>{scene.duration ? `${scene.duration}s` : 'Captured'}</small>
                    </button>
                  ))}
                </div>
                {BUSY.has(job.status) && (
                  <button
                    className="text-button cancel-link"
                    onClick={async () => {
                      await api(`/api/videos/${job.id}/cancel`, {});
                      await refresh();
                    }}
                  >
                    <Square size={11} />
                    Cancel this take
                  </button>
                )}
                {(job.status === 'failed' || job.status === 'cancelled') && (
                  <button
                    className="button coral"
                    onClick={() => {
                      setForm((f) => ({
                        ...f,
                        url: job.payload.demo ? '' : job.payload.url,
                        brief: job.payload.brief,
                        creative_direction: job.payload.creative_direction || '',
                        reference_urls: (job.payload.reference_urls || []).join('\n'),
                        title: job.title,
                      }));
                      setCreating(true);
                      setSelected(null);
                    }}
                  >
                    Start another take <ArrowRight size={14} />
                  </button>
                )}
              </div>
              <aside className="editor-inspector">
                <div className="inspector-tabs">
                  {(['script', 'style', 'animation', 'activity'] as const).map((t) => (
                    <button
                      className={editorTab === t ? 'active' : ''}
                      key={t}
                      onClick={() => setEditorTab(t)}
                    >
                      {t[0].toUpperCase() + t.slice(1)}
                    </button>
                  ))}
                </div>
                {editorTab === 'script' && (
                  <div className="script-editor">
                    <div className="inspector-intro">
                      <Mic size={16} />
                      <h3>A voice for your story.</h3>
                      <p>Tweak a line. We’ll match the scene to the new narration.</p>
                    </div>
                    <TimelineEditor
                      clips={clips}
                      scenes={job.payload.scenes}
                      onChange={setClips}
                      onPlan={planLaunch}
                      onPreview={(text) => previewVoice(voice, text)}
                      disabled={BUSY.has(job.status) || saving}
                      planning={planning}
                      previewing={Boolean(previewing)}
                    />
                    <input
                      ref={uploadRef}
                      type="file"
                      accept="audio/*"
                      hidden
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadNarration(file);
                      }}
                    />
                    <button
                      className="text-button"
                      disabled={job.status !== 'complete'}
                      onClick={() => uploadRef.current?.click()}
                    >
                      <Upload size={12} />
                      Upload finished narration
                    </button>
                    {job.payload.uploaded_narration && (
                      <label>
                        Audio source
                        <select
                          value={audioSource}
                          onChange={(e) => setAudioSource(e.target.value as typeof audioSource)}
                        >
                          <option value="generated">Generate speech from edited words</option>
                          <option value="uploaded">Use my uploaded recording</option>
                        </select>
                        <small className="field-hint">
                          Edited words change generated speech. Uploaded audio keeps its original
                          spoken words.
                        </small>
                      </label>
                    )}
                  </div>
                )}
                {editorTab === 'style' && (
                  <div className="style-editor">
                    <div className="inspector-intro">
                      <WandSparkles size={16} />
                      <h3>The finishing touches.</h3>
                      <p>Make it sound and feel like your product.</p>
                    </div>
                    <label>
                      Narrator
                      <select value={voice} onChange={(e) => setVoice(e.target.value)}>
                        {voices.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button className="text-button" onClick={() => previewVoice(voice)}>
                      <Play size={11} />
                      Hear this voice
                    </button>
                    <label>
                      Background music
                      <select
                        value={music}
                        onChange={(e) => setMusic(e.target.value as typeof music)}
                      >
                        <option value="ambient">Ambient</option>
                        <option value="momentum">Momentum</option>
                        <option value="none">No music</option>
                      </select>
                    </label>
                    <p className="field-hint">Automatically mixed beneath the narration.</p>
                    <label>
                      Visual style
                      <div className="theme-options">
                        <button
                          className={theme === 'midnight' ? 'selected' : ''}
                          onClick={() => setTheme('midnight')}
                        >
                          <i className="midnight" />
                          Midnight
                        </button>
                        <button
                          className={theme === 'paper' ? 'selected' : ''}
                          onClick={() => setTheme('paper')}
                        >
                          <i className="paper" />
                          Paper
                        </button>
                      </div>
                    </label>
                    <div className="export-detail">
                      <Film size={15} />
                      <span>
                        MP4 · 1920 × 1080 · 30 fps
                        <br />
                        <small>Ready for your website, launch, or pitch.</small>
                      </span>
                    </div>
                    <p className="voice-disclosure">Generated narration uses a synthetic voice.</p>
                  </div>
                )}
                {editorTab === 'animation' && (
                  <div className="animation-editor">
                    <div className="inspector-intro">
                      <Sparkles size={16} />
                      <h3>A little launch energy.</h3>
                      <p>Create a visual beat, then blend it into the real product.</p>
                    </div>
                    <p className="field-hint">
                      Animated titles and product reveals work without a video-generation API. Add
                      them in Script → Add launch sequence.
                    </p>
                    <label>
                      Video model
                      <select
                        value={animationProvider}
                        onChange={(e) =>
                          setAnimationProvider(e.target.value as typeof animationProvider)
                        }
                      >
                        <option value="veo">Google Veo 3.1 Fast</option>
                        <option value="sora">OpenAI Sora 2</option>
                      </select>
                    </label>
                    <label>
                      Visual direction
                      <textarea
                        rows={5}
                        maxLength={2000}
                        value={animationPrompt}
                        onChange={(e) => setAnimationPrompt(e.target.value)}
                        placeholder="Describe colors, shapes, movement and mood."
                      />
                    </label>
                    <p className="field-hint">
                      One 4s clip · 720p · Uses provider credits. Abstract visuals only; product
                      screens come from your real capture. Generated audio is replaced by your
                      selected narration and soundtrack.
                    </p>
                    <button
                      className="button coral"
                      disabled={
                        saving ||
                        BUSY.has(job.status) ||
                        !features.video_generation?.[animationProvider] ||
                        animationPrompt.trim().length < 12
                      }
                      onClick={generateAnimation}
                    >
                      <Sparkles size={14} />
                      Generate animation
                    </button>
                    {!features.video_generation?.[animationProvider] && (
                      <p className="field-hint">Configure this provider to enable generation.</p>
                    )}
                    <div className="animation-assets">
                      {(job.payload.assets || []).map((asset) => {
                        const preview = playback?.assets?.find((a) => a.id === asset.id);
                        return (
                          <div className="animation-asset" key={asset.id}>
                            {preview?.url && (
                              <video
                                src={preview.url}
                                poster={preview.thumbnail_url}
                                controls
                                muted
                                playsInline
                                preload="metadata"
                              />
                            )}
                            <b>
                              {asset.provider === 'veo' ? 'Veo animation' : 'Sora animation'} ·{' '}
                              {asset.duration}s
                            </b>
                            <small>{asset.status === 'failed' ? asset.error : asset.status}</small>
                            {asset.status === 'complete' && (
                              <button
                                className="text-button"
                                disabled={clips.length >= 24}
                                onClick={() => {
                                  const clip = {
                                    ...newTitle(),
                                    kind: 'generated' as const,
                                    asset_id: asset.id,
                                    duration: asset.duration,
                                    label: 'Generated launch visual',
                                    headline: job.title,
                                  };
                                  setClips((current) => [clip, ...current]);
                                  setEditorTab('script');
                                  setNotice(
                                    'Animation added to the start of your draft. Move it anywhere and render changes.',
                                  );
                                }}
                              >
                                <Plus size={12} />
                                Add to timeline
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {editorTab === 'activity' && (
                  <div className="activity-editor">
                    <div className="inspector-intro">
                      <Clapperboard size={16} />
                      <h3>Behind the scenes.</h3>
                      <p>From first click to final cut.</p>
                    </div>
                    <div className="activity-list">
                      {job.payload.events.map((item, i) => (
                        <div key={`${i}-${item.at}`}>
                          <span
                            className={
                              i === job.payload.events.length - 1 && BUSY.has(job.status)
                                ? 'working'
                                : ''
                            }
                          >
                            {i === job.payload.events.length - 1 && BUSY.has(job.status) ? (
                              <LoaderCircle size={12} className="spin" />
                            ) : (
                              <Check size={11} />
                            )}
                          </span>
                          <div>
                            <b>{item.stage[0].toUpperCase() + item.stage.slice(1)}</b>
                            <p>{item.message}</p>
                            <small>
                              {new Date(item.at).toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </small>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="inspector-footer">
                  <button
                    className="button coral"
                    disabled={saving || job.status !== 'complete'}
                    onClick={rerender}
                  >
                    {saving ? <LoaderCircle size={14} className="spin" /> : <RefreshCw size={14} />}
                    Render changes
                  </button>
                  <span>Keep the footage. Refine the story.</span>
                </div>
              </aside>
            </div>
          </div>
        )}

        {tab === 'voices' && (
          <div className="voices-page">
            <div className="page-heading">
              <div>
                <div className="eyebrow">A VOICE THAT SOUNDS LIKE YOU</div>
                <h1>
                  Voice library<span>.</span>
                </h1>
                <p>The right voice makes a good story feel effortless.</p>
              </div>
              <button className="button dark" onClick={() => setVoiceModal(true)}>
                <Plus size={15} />
                Add my voice
              </button>
            </div>
            <div className="voice-banner">
              <div className="voice-wave">
                {Array.from({ length: 27 }, (_, i) => (
                  <i key={i} style={{ height: `${12 + Math.abs(Math.sin(i * 1.7)) * 45}px` }} />
                ))}
              </div>
              <div>
                <h2>Your voice. Every take.</h2>
                <p>
                  Upload a clear sample once. Let your agent narrate
                  <br />
                  new scripts in your voice, without another recording.
                </p>
              </div>
              <button className="button light" onClick={() => setVoiceModal(true)}>
                Create my narrator <ArrowRight size={14} />
              </button>
            </div>
            <div className="section-heading">
              <h2>Studio voices</h2>
              <span>{voices.length} narrators</span>
            </div>
            <div className="voice-grid">
              {voices.map((v, i) => (
                <div className="voice-card" key={v.id}>
                  <div className={`voice-avatar voice-${i % 4}`}>
                    <AudioLines size={28} strokeWidth={1.3} />
                  </div>
                  <span className="voice-kind">
                    {v.kind === 'custom' ? 'YOUR VOICE' : 'STUDIO VOICE'}
                  </span>
                  <h3>{v.name}</h3>
                  <p>{v.description}</p>
                  <button
                    className="voice-preview"
                    disabled={previewing === v.id}
                    onClick={() => previewVoice(v.id)}
                  >
                    {previewing === v.id ? (
                      <LoaderCircle size={13} className="spin" />
                    ) : (
                      <Play size={11} fill="currentColor" />
                    )}
                    Listen to a sample
                  </button>
                </div>
              ))}
            </div>
            <p className="voice-disclosure">
              <Mic size={12} />
              Stock and cloned narrators use AI generated speech. Finished narration can also be
              uploaded in the editor.
            </p>
          </div>
        )}

        {tab === 'agents' && (
          <div className="agents-page">
            <div className="page-heading">
              <div>
                <div className="eyebrow">BUILT FOR WHAT AGENTS WANT</div>
                <h1>
                  Your agent’s cutroom<span>.</span>
                </h1>
                <p>Make product videos part of the way you ship.</p>
              </div>
              <span className="protocol-tag">
                <span />
                STREAMABLE HTTP MCP
              </span>
            </div>
            <div className="agent-hero">
              <span className="agent-icon">
                <Code2 size={33} strokeWidth={1.4} />
              </span>
              <h2>“Make a demo of what I just built.”</h2>
              <p>
                Your agent gives us the link and the brief. Cutroom handles the browser,
                <br />
                the narration, and the final film. Same studio. One less tab.
              </p>
              <div className="agent-flow">
                <span>
                  <Globe2 size={15} />
                  Deployed app
                </span>
                <ArrowRight size={14} />
                <span>
                  <MousePointer2 size={15} />
                  Agent captures
                </span>
                <ArrowRight size={14} />
                <span>
                  <Clapperboard size={15} />
                  Finished film
                </span>
              </div>
            </div>
            <div className="connector-layout">
              <section className="connector-card">
                <div className="section-heading">
                  <h2>Connect your agent</h2>
                  <span className="step-label">01 / SETUP</span>
                </div>
                <label>
                  Server URL
                  <div className="copy-field">
                    <code>{location.origin}/mcp</code>
                    <button onClick={() => copy(`${location.origin}/mcp`, 'url')}>
                      {copied === 'url' ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                </label>
                <label>
                  Authentication
                  <span className="field-hint">
                    Bearer token from this workspace’s Supabase session.
                  </span>
                  <div className="copy-field">
                    <code>{tokenVisible ? token : '••••••••••••••••••••••••••••'}</code>
                    <button
                      onClick={async () => {
                        const value = await accessToken();
                        setToken(value);
                        setTokenVisible(!tokenVisible);
                      }}
                    >
                      {tokenVisible ? 'Hide' : 'Show'}
                    </button>
                    <button onClick={async () => copy(await accessToken(), 'token')}>
                      {copied === 'token' ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                </label>
                <p className="field-hint">
                  Session tokens expire. Refresh the token when reconnecting.
                </p>
                <label>
                  Claude Code
                  <div className="code-example">
                    <code>
                      claude mcp add --transport http cutroom {location.origin}/mcp --header
                      "Authorization: Bearer &lt;your-token&gt;"
                    </code>
                    <button
                      onClick={() =>
                        copy(
                          `claude mcp add --transport http cutroom ${location.origin}/mcp --header "Authorization: Bearer <your-token>"`,
                          'command',
                        )
                      }
                    >
                      {copied === 'command' ? <Check size={13} /> : <Copy size={13} />}
                    </button>
                  </div>
                </label>
              </section>
              <section className="connector-card">
                <div className="section-heading">
                  <h2>Give it a little direction</h2>
                  <span className="step-label">02 / CREATE</span>
                </div>
                <div className="prompt-example">
                  <Sparkles size={16} />
                  <p>
                    Make a 30-second launch film of my deployed app. Use the demo login, show how a
                    user creates a project and views its board, narrate with Marin, and add quiet
                    ambient music. Return the MP4 when it’s ready.
                  </p>
                </div>
                <div className="tool-list">
                  {[
                    ['create_product_video', 'A link, credentials, and a feature brief.'],
                    ['get_video', 'Follow progress and review the story.'],
                    ['list_voices', 'Choose a stock or custom narrator.'],
                    ['render_video', 'Edit words, scene cuts, timing, music, and look.'],
                    ['plan_launch_video', 'Draft an animated opening, spotlight, and closing.'],
                    ['generate_animation', 'Create a short Veo or Sora visual for the timeline.'],
                    ['export_video', 'Get a private MP4 link.'],
                  ].map(([name, desc]) => (
                    <div key={name}>
                      <code>{name}</code>
                      <p>{desc}</p>
                    </div>
                  ))}
                </div>
              </section>
            </div>
            <div className="connector-footer">
              <LockKeyhole size={15} />
              <span>
                Agents use the same authenticated workspace as the app. Demo credentials are used
                for the recording and never saved in the project.
              </span>
            </div>
          </div>
        )}
      </div>
      {voiceModal && (
        <div className="modal-backdrop" onClick={() => setVoiceModal(false)}>
          <div
            className="voice-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="voice-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button className="modal-close" onClick={() => setVoiceModal(false)}>
              <X size={18} />
            </button>
            <span className="modal-icon">
              <Mic size={25} />
            </span>
            <div className="eyebrow">YOUR VOICE, WITHOUT THE RETAKES</div>
            <h2 id="voice-modal-title">Create your narrator.</h2>
            <p>
              Upload a clean recording of yourself speaking naturally. We’ll create a voice that can
              read each new demo script.
            </p>
            <label>
              Narrator name
              <input
                value={voiceName}
                maxLength={80}
                onChange={(e) => setVoiceName(e.target.value)}
              />
            </label>
            <label className="upload-zone">
              <Upload size={23} />
              <b>{voiceFile ? voiceFile.name : 'Choose an audio sample'}</b>
              <span>MP3, WAV, or M4A · up to 20 MB</span>
              <input
                type="file"
                accept="audio/*"
                onChange={(e) => setVoiceFile(e.target.files?.[0] || null)}
              />
            </label>
            <label className="consent">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span>
                This is my voice. I consent to creating a synthetic version for narration.
              </span>
            </label>
            {!features.voice_cloning && (
              <div className="setup-note">
                <Mic size={15} />
                <span>
                  Cloning requires an ElevenLabs API key with cloning access. You can use a studio
                  voice or upload finished narration in the meantime.
                </span>
              </div>
            )}
            <button
              className="button coral"
              disabled={!voiceFile || !consent || !features.voice_cloning || saving}
              onClick={uploadVoice}
            >
              {saving ? <LoaderCircle size={15} className="spin" /> : <AudioLines size={15} />}
              Create my voice
            </button>
            <small>Your sample is sent to the voice provider to create your narrator.</small>
          </div>
        </div>
      )}
    </div>
  );
}
