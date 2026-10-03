import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  BarChart3,
  BookOpen,
  Box,
  Braces,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Code2,
  Copy,
  Database,
  FileSpreadsheet,
  FlaskConical,
  Layers3,
  Loader2,
  Network,
  Plus,
  Radio,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Terminal,
  Upload,
  Waypoints,
  X,
  Zap,
} from 'lucide-react';
import { accessToken, api, downloadDataset, initialize, supabaseClient } from './api';
import type { Config, Dataset, ModelResult, Plan, Prediction, Run } from './types';

type View = 'library' | 'create' | 'activity' | 'connect';
const samples = [
  {
    id: 'shipments',
    title: 'Will this shipment be late?',
    description: 'Learn the patterns behind delivery delays.',
    rows: '1,600',
    kind: 'Classification',
    tag: 'Simulated data',
    icon: Box,
    color: 'purple',
  },
  {
    id: 'energy',
    title: 'How much energy will we use?',
    description: 'Estimate demand from building conditions.',
    rows: '1,200',
    kind: 'Regression',
    tag: 'Simulated data',
    icon: Zap,
    color: 'orange',
  },
  {
    id: 'wine',
    title: 'Which wine cultivar is this?',
    description: 'Recognize a cultivar from its measurements.',
    rows: '178',
    kind: 'Classification',
    tag: 'Public UCI data',
    icon: FlaskConical,
    color: 'green',
  },
];
const labels = {
  library: 'Skill library',
  create: 'Create a skill',
  activity: 'Activity',
  connect: 'Connect your agent',
};
const pretty = (value: string) => value.replaceAll('_', ' ');
const score = (value: number, result: ModelResult) =>
  result.higher_better ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
const when = (date: string) =>
  new Date(date).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

function Logo({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand ${small ? 'small' : ''}`}>
      <span className="brand-mark">
        <Layers3 size={small ? 16 : 22} strokeWidth={2.5} />
      </span>
      {!small && (
        <span>
          forge<span className="brand-dot">.</span>
        </span>
      )}
    </span>
  );
}

function Tag({ children, color = '' }: { children: ReactNode; color?: string }) {
  return <span className={`tag ${color}`}>{children}</span>;
}

function SkillGraphic() {
  return (
    <div className="skill-graphic" aria-hidden="true">
      <div className="graphic-grid" />
      <svg className="graphic-lines" viewBox="0 0 430 210">
        <path d="M80 80 C150 80 110 130 215 130 S300 65 350 65" />
        <path d="M85 160 C160 160 155 130 215 130 S300 170 355 170" />
        <circle cx="145" cy="100" r="4" />
        <circle cx="293" cy="104" r="4" />
      </svg>
      <div className="graphic-node data-node">
        <Database size={23} />
        <span>Your data</span>
        <i>1,600 rows</i>
      </div>
      <div className="graphic-node mini-node">
        <Braces size={17} />
        <span>Your goal</span>
      </div>
      <div className="graphic-node model-node">
        <Waypoints size={32} />
        <span>Learn & test</span>
        <div className="tiny-bars">
          <i />
          <i />
          <i />
          <i />
          <i />
          <i />
          <i />
        </div>
      </div>
      <div className="graphic-node tool-node">
        <Zap size={23} />
        <span>Agent skill</span>
        <i>
          <span className="dot" /> Ready to call
        </i>
      </div>
      <div className="graphic-caption">
        <span className="dot" /> DATA IN. CAPABILITY OUT.
      </div>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>('library');
  const [config, setConfig] = useState<Config | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [step, setStep] = useState<'data' | 'task' | 'train'>('data');
  const [objective, setObjective] = useState('');
  const [target, setTarget] = useState('');
  const [task, setTask] = useState<'classification' | 'regression'>('classification');
  const [features, setFeatures] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [split, setSplit] = useState<'random' | 'temporal'>('random');
  const [timeColumn, setTimeColumn] = useState('');
  const [planNote, setPlanNote] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [guide, setGuide] = useState(false);
  const [search, setSearch] = useState('');
  const [inputs, setInputs] = useState<Record<string, string | number | null>>({});
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [actual, setActual] = useState('');
  const [feedbackSaved, setFeedbackSaved] = useState(false);
  const [connectionTab, setConnectionTab] = useState<'playground' | 'api' | 'mcp'>('playground');
  const fileInput = useRef<HTMLInputElement>(null);
  const result = run?.payload.result;

  async function refresh() {
    const [newRuns, newDatasets] = await Promise.all([
      api<Run[]>('/api/runs'),
      api<Dataset[]>('/api/datasets'),
    ]);
    setRuns(newRuns);
    setDatasets(newDatasets);
  }

  useEffect(() => {
    initialize()
      .then((c) => {
        setConfig(c);
        return refresh();
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(''), 4000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (!run || !['queued', 'training'].includes(run.status)) return;
    let cancelled = false;
    const id = run.id;
    const update = (next: Run) => {
      if (cancelled) return;
      setRun(next);
      if (next.status === 'ready' || next.status === 'failed')
        refresh().catch((e) => setError(e.message));
    };
    const timer = setInterval(
      () =>
        api<Run>(`/api/runs/${id}`)
          .then(update)
          .catch((e) => !cancelled && setError(e.message)),
      1200,
    );
    const client = supabaseClient();
    const channel = client
      ?.channel(`run-${id}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'runs', filter: `id=eq.${id}` },
        () =>
          api<Run>(`/api/runs/${id}`)
            .then(update)
            .catch(() => {}),
      )
      .subscribe();
    return () => {
      cancelled = true;
      clearInterval(timer);
      if (channel && client) client.removeChannel(channel);
    };
  }, [run?.id, run?.status]);
  useEffect(() => {
    if (result) {
      setInputs(result.example_input);
      setPrediction(null);
      setFeedbackSaved(false);
      setActual('');
    }
  }, [run?.id, Boolean(result)]);

  async function action(key: string, operation: () => Promise<void>) {
    setBusy(key);
    setError('');
    try {
      await operation();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy('');
    }
  }

  function newSkill() {
    setRun(null);
    setDataset(null);
    setStep('data');
    setView('create');
    setObjective('');
    setPlanNote('');
    setSplit('random');
    setTimeColumn('');
  }

  function selectDataset(next: Dataset) {
    setDataset(next);
    setRun(null);
    setTarget(next.profile.suggested_target);
    setTask(next.profile.suggested_task);
    setFeatures(
      next.profile.columns
        .filter((c) => !c.excluded && c.name !== next.profile.suggested_target)
        .map((c) => c.name),
    );
    setName(`Predict ${pretty(next.profile.suggested_target)}`);
    setObjective(
      next.profile.suggested_target === 'delayed'
        ? 'Predict whether a shipment will be delayed using information available before dispatch.'
        : `Predict ${pretty(next.profile.suggested_target)} from the available measurements.`,
    );
    setStep('task');
    setView('create');
    setPlanNote('');
    setSplit('random');
    setTimeColumn('');
  }

  async function useSample(kind: string) {
    await action(`sample-${kind}`, async () => {
      const next = await api<Dataset>('/api/datasets/sample', { kind });
      selectDataset(next);
      await refresh();
    });
  }
  async function upload(file: File) {
    await action('upload', async () => {
      const form = new FormData();
      form.append('file', file);
      const next = await api<Dataset>('/api/datasets/upload', undefined, form);
      selectDataset(next);
      await refresh();
    });
  }
  function chooseTarget(next: string) {
    setTarget(next);
    setName(`Predict ${pretty(next)}`);
    const col = dataset?.profile.columns.find((c) => c.name === next);
    setTask(col?.type === 'number' && col.unique > 10 ? 'regression' : 'classification');
    setFeatures(
      dataset!.profile.columns.filter((c) => !c.excluded && c.name !== next).map((c) => c.name),
    );
  }
  async function suggestPlan() {
    await action('plan', async () => {
      const p = await api<Plan>('/api/plan', { dataset_id: dataset!.id, objective });
      setTarget(p.target);
      setTask(p.task);
      setFeatures(p.features);
      setName(p.name);
      setPlanNote(p.reason);
    });
  }
  async function train() {
    await action('train', async () => {
      const next = await api<Run>('/api/runs', {
        dataset_id: dataset!.id,
        target,
        features,
        task,
        name,
        objective,
        split,
        time_column: split === 'temporal' ? timeColumn : null,
      });
      setRun(next);
      setStep('train');
      await refresh();
    });
  }
  function openRun(next: Run, to: View = 'create') {
    setRun(next);
    setDataset(datasets.find((d) => d.id === next.dataset_id) || null);
    setStep('train');
    setView(to);
  }
  async function copy(value: string, label: string) {
    await action('copy', async () => {
      await navigator.clipboard.writeText(value);
      setToast(`${label} copied`);
    });
  }
  async function runPrediction() {
    await action('predict', async () => {
      setPrediction(await api<Prediction>(`/api/runs/${run!.id}/predict`, { records: [inputs] }));
      setFeedbackSaved(false);
    });
  }
  const readyRuns = runs.filter((r) => r.status === 'ready');

  const datasetPicker = (
    <>
      <div
        className="upload-zone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (!busy && e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
        }}
      >
        <span className="upload-icon">
          <Upload size={24} />
        </span>
        <h3>Start with your data</h3>
        <p>Drop a CSV here, or choose a file to explore.</p>
        <button
          className="button primary"
          disabled={!!busy || !config}
          onClick={() => fileInput.current?.click()}
        >
          {busy === 'upload' ? <Loader2 className="spin" size={16} /> : <Plus size={16} />} Choose
          CSV file
        </button>
        <span className="micro">Up to 5 MB · 50–25,000 rows · No personal or sensitive data</span>
      </div>
      <div className="section-title">
        <h3>Or try a sample</h3>
        <span>Real training. No setup.</span>
      </div>
      <div className="sample-grid">
        {samples.map((sample) => (
          <button
            key={sample.id}
            className="sample-card"
            disabled={!!busy || !config}
            onClick={() => useSample(sample.id)}
          >
            <div className={`sample-icon ${sample.color}`}>
              <sample.icon size={21} />
            </div>
            <Tag>{sample.tag}</Tag>
            <h3>{sample.title}</h3>
            <p>{sample.description}</p>
            <div className="sample-footer">
              <span>
                {sample.rows} rows <span>·</span> {sample.kind}
              </span>
              {busy === `sample-${sample.id}` ? (
                <Loader2 size={17} className="spin" />
              ) : (
                <ArrowUpRight size={17} />
              )}
            </div>
          </button>
        ))}
      </div>
      {datasets.length > 0 && (
        <div className="panel recent-data">
          <div className="panel-heading">
            <h3>Recent datasets</h3>
            <Database size={16} />
          </div>
          {datasets.slice(0, 5).map((d) => (
            <button key={d.id} onClick={() => selectDataset(d)}>
              <FileSpreadsheet size={19} />
              <span>
                {d.name}
                <small>
                  {d.profile.rows.toLocaleString()} rows · {d.profile.columns.length} columns
                </small>
              </span>
              <ChevronRight size={16} />
            </button>
          ))}
        </div>
      )}
    </>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Logo />
        <button className="workspace-switch" onClick={() => setGuide(true)}>
          <span className="workspace-avatar">W</span>
          <span>
            Your workspace<small>Supabase Select 2026</small>
          </span>
          <ChevronDown size={15} />
        </button>
        <div className="nav-label">BUILD</div>
        <nav>
          {(
            [
              { id: 'library', icon: Layers3 },
              { id: 'create', icon: Plus },
              { id: 'activity', icon: AudioLines },
              { id: 'connect', icon: Network },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              className={view === item.id ? 'active' : ''}
              onClick={() => (item.id === 'create' ? newSkill() : setView(item.id))}
            >
              <item.icon size={18} />
              {labels[item.id]}
              {item.id === 'library' && <span className="nav-count">{readyRuns.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <span className="note-icon">
              <Zap size={17} />
            </span>
            <h4>One dataset. A new capability.</h4>
            <p>Give your agent something it can actually call.</p>
            <button onClick={() => setGuide(true)}>
              See how it works <ArrowUpRight size={14} />
            </button>
          </div>
          <a
            className="supabase-credit"
            href="https://supabase.com"
            target="_blank"
            rel="noreferrer"
          >
            <Zap size={16} />
            <span>Powered by Supabase</span>
            <ArrowUpRight size={13} />
          </a>
          <button className="help-button" onClick={() => setGuide(true)}>
            <CircleHelp size={17} />
            Quick guide
            <ArrowUpRight size={14} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{labels[view]}</strong>
          </div>
          <div className="topbar-actions">
            <span className="connection-status">
              <span className={`dot ${config ? '' : 'waiting'}`} />
              {config
                ? config.mode === 'supabase'
                  ? 'Supabase connected'
                  : 'Offline demo'
                : 'Connecting…'}
            </span>
            <button className="button small-button" onClick={() => setGuide(true)}>
              <BookOpen size={15} /> Guide
            </button>
            <button
              className="user-avatar"
              onClick={() => setGuide(true)}
              aria-label="Workspace information"
            >
              W
            </button>
          </div>
        </header>
        <main>
          {error && (
            <div className="error-banner" role="alert">
              <CircleHelp size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError('')}>
                <X size={16} />
              </button>
            </div>
          )}
          {view === 'library' && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">YOUR CAPABILITY WORKSPACE</div>
                  <h1>
                    Skill library<span className="heading-count">{readyRuns.length}</span>
                  </h1>
                  <p>Small models. Real predictions. More capable agents.</p>
                </div>
                <button className="button primary" onClick={newSkill}>
                  <Plus size={17} /> New skill
                </button>
              </div>
              <section className="hero">
                <div className="hero-copy">
                  <Tag color="purple">
                    <Sparkles size={12} /> BUILT FROM YOUR DATA
                  </Tag>
                  <h2>
                    Give your agent
                    <br />a new <span>skill.</span>
                  </h2>
                  <p>
                    Turn a dataset into a tested prediction tool.
                    <br />
                    Your agent asks. A specialized model answers.
                  </p>
                  <button className="button dark" onClick={newSkill}>
                    Create a skill <ArrowRight size={17} />
                  </button>
                  <div className="hero-footnote">
                    <ShieldCheck size={14} /> Tested before your agent uses it.
                  </div>
                </div>
                <SkillGraphic />
              </section>
              <div className="stat-strip">
                <div>
                  <span className="stat-icon">
                    <Layers3 size={19} />
                  </span>
                  <span>
                    <strong>{readyRuns.length}</strong>
                    <small>Ready-to-call skills</small>
                  </span>
                </div>
                <div>
                  <span className="stat-icon">
                    <Database size={19} />
                  </span>
                  <span>
                    <strong>{datasets.length}</strong>
                    <small>Connected datasets</small>
                  </span>
                </div>
                <div>
                  <span className="stat-icon">
                    <FlaskConical size={19} />
                  </span>
                  <span>
                    <strong>{runs.length}</strong>
                    <small>Experiments run</small>
                  </span>
                </div>
                <div>
                  <span className="stat-icon green">
                    <Zap size={19} />
                  </span>
                  <span>
                    <strong>0 tokens</strong>
                    <small>Per ML prediction</small>
                  </span>
                </div>
              </div>
              <div className="section-title library-title">
                <h3>
                  Your skills <Tag>{readyRuns.length}</Tag>
                </h3>
                <label className="search">
                  <Search size={15} />
                  <input
                    aria-label="Search skills"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search skills…"
                  />
                </label>
              </div>
              {readyRuns.length === 0 ? (
                <div className="empty-library">
                  <div className="empty-symbol">
                    <Layers3 size={26} />
                    <span>
                      <Plus size={12} />
                    </span>
                  </div>
                  <h3>Your next skill starts here</h3>
                  <p>
                    Upload a dataset or try a sample.
                    <br />
                    We’ll train, test, and package the best method.
                  </p>
                  <button className="text-button" onClick={newSkill}>
                    Create your first skill <ArrowRight size={15} />
                  </button>
                </div>
              ) : (
                <div className="skill-grid">
                  {readyRuns
                    .filter((r) => r.name.toLowerCase().includes(search.toLowerCase()))
                    .map((r) => (
                      <button className="skill-card" key={r.id} onClick={() => openRun(r)}>
                        <div className="skill-card-top">
                          <span className="sample-icon purple">
                            <Waypoints size={21} />
                          </span>
                          <Tag color="green">
                            <span className="dot" />
                            Ready
                          </Tag>
                        </div>
                        <h3>{r.name}</h3>
                        <p>{r.payload.objective || `Predict ${pretty(r.payload.target)}`}</p>
                        <div className="skill-metric">
                          <strong>{score(r.payload.result!.test_score, r.payload.result!)}</strong>
                          <span>{r.payload.result!.metric.toLowerCase()} · test set</span>
                        </div>
                        <div className="sample-footer">
                          <span>{r.payload.result!.selected_model}</span>
                          <ArrowUpRight size={16} />
                        </div>
                      </button>
                    ))}
                </div>
              )}
              <div className="section-title">
                <h3>Find your starting point</h3>
                <span>
                  Pick a sample and make it yours <ArrowDownToLine size={14} />
                </span>
              </div>
              <div className="sample-grid">
                {samples.map((s) => (
                  <button
                    key={s.id}
                    className="sample-card compact"
                    disabled={!!busy || !config}
                    onClick={() => useSample(s.id)}
                  >
                    <div className={`sample-icon ${s.color}`}>
                      <s.icon size={20} />
                    </div>
                    <h3>{s.title}</h3>
                    <p>
                      {s.rows} rows · {s.tag.toLowerCase()}
                    </p>
                    <ArrowUpRight className="card-arrow" size={17} />
                  </button>
                ))}
              </div>
            </>
          )}

          {view === 'create' && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">FROM DATA TO CAPABILITY</div>
                  <h1>{run ? run.name : 'Create a skill'}</h1>
                  <p>
                    {run
                      ? 'An observable experiment. A reusable tool.'
                      : 'Teach your agent a task it can measure.'}
                  </p>
                </div>
                {dataset && (
                  <Tag>
                    <Database size={13} />
                    {dataset.name}
                  </Tag>
                )}
              </div>
              <div className="steps">
                {['Choose data', 'Define the task', 'Train & evaluate', 'Use your skill'].map(
                  (s, i) => {
                    const current =
                      step === 'data' ? 0 : step === 'task' ? 1 : run?.status === 'ready' ? 3 : 2;
                    return (
                      <div
                        className={i === current ? 'current' : i < current ? 'complete' : ''}
                        key={s}
                      >
                        <span>{i < current ? <Check size={13} /> : i + 1}</span>
                        {s}
                        {i < 3 && <ChevronRight size={14} />}
                      </div>
                    );
                  },
                )}
              </div>
              {step === 'data' && datasetPicker}
              {step === 'task' && dataset && (
                <div className="task-layout">
                  <div>
                    <section className="panel">
                      <div className="panel-heading">
                        <h3>
                          <Sparkles size={17} /> What should this skill do?
                        </h3>
                        <Tag>
                          {config?.planner === 'anthropic'
                            ? 'Language planner'
                            : 'Schema-guided setup'}
                        </Tag>
                      </div>
                      <div className="panel-body">
                        <label className="field-label" htmlFor="objective">
                          Describe the outcome
                        </label>
                        <textarea
                          id="objective"
                          value={objective}
                          onChange={(e) => setObjective(e.target.value)}
                          placeholder="Predict whether a shipment will be late, before it leaves the warehouse."
                          rows={3}
                        />
                        <div className="objective-footer">
                          <span>Your goal guides the setup. You confirm the inputs.</span>
                          <button
                            className="button small-button"
                            disabled={!!busy || objective.length < 3}
                            onClick={suggestPlan}
                          >
                            {busy === 'plan' ? (
                              <Loader2 className="spin" size={14} />
                            ) : (
                              <Sparkles size={14} />
                            )}{' '}
                            Suggest setup
                          </button>
                        </div>
                        {planNote && (
                          <div className="info-note">
                            <Sparkles size={15} />
                            {planNote}
                          </div>
                        )}
                        <div className="form-grid">
                          <label>
                            Skill name
                            <input
                              value={name}
                              onChange={(e) => setName(e.target.value)}
                              maxLength={80}
                            />
                          </label>
                          <label>
                            Outcome column
                            <select value={target} onChange={(e) => chooseTarget(e.target.value)}>
                              {dataset.profile.columns.map((c) => (
                                <option key={c.name}>{c.name}</option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Prediction type
                            <select
                              value={task}
                              onChange={(e) => setTask(e.target.value as typeof task)}
                            >
                              <option value="classification">
                                Classification · choose a category
                              </option>
                              <option value="regression">Regression · estimate a number</option>
                            </select>
                          </label>
                          <label>
                            Evaluation split
                            <select
                              value={split}
                              onChange={(e) => setSplit(e.target.value as typeof split)}
                            >
                              <option value="random">Random · independent rows</option>
                              <option value="temporal">Chronological · future outcomes</option>
                            </select>
                          </label>
                          {split === 'temporal' && (
                            <label>
                              Time column
                              <select
                                value={timeColumn}
                                onChange={(e) => {
                                  setTimeColumn(e.target.value);
                                  setFeatures((f) => f.filter((x) => x !== e.target.value));
                                }}
                              >
                                <option value="">Choose a date column</option>
                                {dataset.profile.columns
                                  .filter((c) => c.name !== target)
                                  .map((c) => (
                                    <option key={c.name}>{c.name}</option>
                                  ))}
                              </select>
                            </label>
                          )}
                        </div>
                      </div>
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <h3>
                          <Settings2 size={17} /> Input features
                        </h3>
                        <span>{features.length} selected</span>
                      </div>
                      <div className="feature-list">
                        {dataset.profile.columns
                          .filter((c) => c.name !== target)
                          .map((c) => (
                            <label
                              className={`feature-row ${c.excluded ? 'excluded' : ''}`}
                              key={c.name}
                            >
                              <input
                                type="checkbox"
                                checked={features.includes(c.name)}
                                disabled={
                                  c.excluded || (split === 'temporal' && c.name === timeColumn)
                                }
                                onChange={(e) =>
                                  setFeatures((f) =>
                                    e.target.checked
                                      ? [...f, c.name]
                                      : f.filter((v) => v !== c.name),
                                  )
                                }
                              />
                              <span className="column-type">
                                {c.type === 'number' ? '#' : 'Aa'}
                              </span>
                              <span className="feature-name">
                                {c.name}
                                <small>
                                  {c.reason ||
                                    `${c.unique} distinct values${c.missing ? ` · ${c.missing} missing` : ''}`}
                                </small>
                              </span>
                              {c.excluded ? (
                                <Tag color="orange">Excluded</Tag>
                              ) : (
                                <Tag>{c.type}</Tag>
                              )}
                            </label>
                          ))}
                      </div>
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <h3>
                          <FileSpreadsheet size={17} /> Data preview
                        </h3>
                        <button
                          className="icon-button"
                          aria-label="Download dataset"
                          onClick={() => action('download', () => downloadDataset(dataset.id))}
                        >
                          <ArrowDownToLine size={17} />
                        </button>
                      </div>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              {dataset.profile.columns.map((c) => (
                                <th key={c.name}>
                                  {c.name === target && <span className="target-indicator" />}
                                  {c.name}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {dataset.profile.preview.slice(0, 5).map((row, i) => (
                              <tr key={i}>
                                {dataset.profile.columns.map((c) => (
                                  <td key={c.name}>
                                    {row[c.name] === null ? (
                                      <span className="null-value">null</span>
                                    ) : (
                                      String(row[c.name])
                                    )}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>
                  </div>
                  <aside className="recipe">
                    <div className="recipe-title">
                      <span className="sample-icon purple">
                        <Waypoints size={23} />
                      </span>
                      <h3>Your skill recipe</h3>
                    </div>
                    <div className="recipe-item">
                      <small>DATASET</small>
                      <strong>{dataset.name}</strong>
                      <span>
                        {dataset.profile.rows.toLocaleString()} rows ·{' '}
                        {dataset.profile.columns.length} columns
                      </span>
                    </div>
                    <div className="recipe-item">
                      <small>PREDICT</small>
                      <strong>{pretty(target)}</strong>
                      <span>Using {features.length} input features</span>
                    </div>
                    <div className="recipe-item">
                      <small>METHODS TO COMPARE</small>
                      <span>Simple baseline</span>
                      <span>
                        {task === 'classification' ? 'Logistic regression' : 'Ridge regression'}
                      </span>
                      <span>Random forest</span>
                    </div>
                    <div className="split-viz">
                      <i />
                      <i />
                      <i />
                    </div>
                    <div className="split-labels">
                      <span>60% train</span>
                      <span>20% val</span>
                      <span>20% test</span>
                    </div>
                    <div className="recipe-note">
                      <ShieldCheck size={16} />
                      <p>The final test set stays untouched until a method is selected.</p>
                    </div>
                    <button
                      className="button primary full"
                      disabled={
                        !!busy ||
                        !features.length ||
                        !name.trim() ||
                        (split === 'temporal' && !timeColumn)
                      }
                      onClick={train}
                    >
                      {busy === 'train' ? (
                        <Loader2 className="spin" size={16} />
                      ) : (
                        <FlaskConical size={16} />
                      )}{' '}
                      Train & evaluate <ArrowRight size={15} />
                    </button>
                    <button className="text-button back-link" onClick={() => setStep('data')}>
                      Choose different data
                    </button>
                    <p className="source-note">{dataset.source}</p>
                  </aside>
                </div>
              )}
              {step === 'train' && run && (
                <>
                  {['training', 'queued'].includes(run.status) && (
                    <section className="training-hero">
                      <div className="orb">
                        <Waypoints size={36} />
                      </div>
                      <Tag color="purple">
                        <span className="dot pulse" />
                        EXPERIMENT RUNNING
                      </Tag>
                      <h2>Learning your new skill.</h2>
                      <p>
                        Training three methods. Selecting on validation.
                        <br />
                        Keeping the final test set separate.
                      </p>
                      <div className="training-track">
                        <i />
                      </div>
                    </section>
                  )}
                  {run.status === 'failed' && (
                    <div className="panel failure">
                      <CircleHelp size={26} />
                      <h3>This experiment needs attention</h3>
                      <p>{run.payload.error}</p>
                      <button
                        className="button"
                        onClick={() => {
                          setStep('task');
                          setRun(null);
                        }}
                      >
                        Adjust task settings
                      </button>
                    </div>
                  )}
                  {result && (
                    <>
                      <div className="result-banner">
                        <div className="success-icon">
                          <CheckCircle2 size={27} />
                        </div>
                        <div>
                          <Tag color="green">SKILL READY</Tag>
                          <h2>
                            {result.baseline_only
                              ? 'The baseline was the strongest method.'
                              : 'Your agent just learned a new skill.'}
                          </h2>
                          <p>
                            {result.selected_model} · {result.features.length} inputs · Trained in{' '}
                            {result.training_seconds.toFixed(1)}s
                          </p>
                        </div>
                        <button className="button primary" onClick={() => setView('connect')}>
                          Use this skill <ArrowRight size={16} />
                        </button>
                      </div>
                      <div className="result-stats">
                        <div className="panel metric-panel">
                          <span>FINAL TEST {result.metric.toUpperCase()}</span>
                          <strong>{score(result.test_score, result)}</strong>
                          <small>{result.splits.test} untouched test rows</small>
                          <div className="metric-spark">
                            <BarChart3 size={48} />
                          </div>
                        </div>
                        <div className="panel metric-panel">
                          <span>SIMPLE BASELINE</span>
                          <strong className="muted-value">
                            {score(result.baseline_score, result)}
                          </strong>
                          <small>
                            {result.higher_better
                              ? 'Majority-class prediction'
                              : 'Median-value prediction'}
                          </small>
                        </div>
                        <div className="panel metric-panel">
                          <span>TRAINING TIME</span>
                          <strong>
                            {result.training_seconds.toFixed(1)}
                            <em>s</em>
                          </strong>
                          <small>Three methods compared</small>
                        </div>
                      </div>
                      <div className="result-layout">
                        <section className="panel">
                          <div className="panel-heading">
                            <h3>
                              <FlaskConical size={17} /> Model comparison
                            </h3>
                            <Tag>Validation set</Tag>
                          </div>
                          <div className="model-table">
                            <div className="model-table-head">
                              <span>METHOD</span>
                              <span>{result.metric.toUpperCase()}</span>
                              <span>TRAIN TIME</span>
                            </div>
                            {result.leaderboard.map((m, i) => (
                              <div
                                className={`model-table-row ${i === 0 ? 'selected-model' : ''}`}
                                key={m.name}
                              >
                                <span>
                                  <span className="rank">{i + 1}</span>
                                  <strong>{m.name}</strong>
                                  {i === 0 && <Tag color="purple">Selected</Tag>}
                                </span>
                                <strong>{score(m.score, result)}</strong>
                                <span>{m.seconds.toFixed(2)}s</span>
                              </div>
                            ))}
                          </div>
                          <div className="panel-footnote">
                            <ShieldCheck size={14} />
                            The model was selected on validation, then evaluated once on the final
                            test set.
                          </div>
                        </section>
                        <section className="panel">
                          <div className="panel-heading">
                            <h3>
                              <BarChart3 size={17} /> What the model uses
                            </h3>
                            <Tag>Validation</Tag>
                          </div>
                          <div className="importance-list">
                            {result.importance.length ? (
                              result.importance.slice(0, 6).map((f) => (
                                <div key={f.feature}>
                                  <div>
                                    <span>{pretty(f.feature)}</span>
                                    <small>{f.value.toFixed(3)}</small>
                                  </div>
                                  <div className="importance-track">
                                    <i
                                      style={{
                                        width: `${Math.max(2, (f.value / (result.importance[0].value || 1)) * 100)}%`,
                                      }}
                                    />
                                  </div>
                                </div>
                              ))
                            ) : (
                              <p>The baseline does not use input features.</p>
                            )}
                          </div>
                          <div className="panel-footnote">
                            Score drop when shuffled. Association, not causation.
                          </div>
                        </section>
                      </div>
                      <details className="panel limitations">
                        <summary>
                          <ShieldCheck size={16} /> Evaluation details & limitations{' '}
                          <ChevronDown size={16} />
                        </summary>
                        <div>
                          <p>
                            Split: {result.splits.strategy} · {result.splits.train} train /{' '}
                            {result.splits.validation} validation / {result.splits.test} test.
                          </p>
                          {result.notes.map((note) => (
                            <p key={note}>{note}</p>
                          ))}
                          <p>{dataset?.source}</p>
                        </div>
                      </details>
                    </>
                  )}
                  <section className="panel">
                    <div className="panel-heading">
                      <h3>
                        <Radio size={17} /> Experiment trace
                      </h3>
                      <span>{run.payload.events.length} events</span>
                    </div>
                    <div className="event-list">
                      {run.payload.events.map((event, i) => (
                        <div key={`${event.at}-${i}`}>
                          <span
                            className={`event-dot ${i === run.payload.events.length - 1 && run.status === 'training' ? 'pulse' : ''}`}
                          >
                            <Check size={11} />
                          </span>
                          <span>
                            <strong>{event.title}</strong>
                            <p>{event.detail}</p>
                          </span>
                          <time>{when(event.at)}</time>
                        </div>
                      ))}
                    </div>
                  </section>
                </>
              )}
            </>
          )}

          {view === 'connect' && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">PUT YOUR CAPABILITY TO WORK</div>
                  <h1>Connect your agent</h1>
                  <p>A tested skill, ready for a tool call.</p>
                </div>
                {readyRuns.length > 0 && (
                  <select
                    className="run-select"
                    aria-label="Select skill"
                    value={run?.status === 'ready' ? run.id : ''}
                    onChange={(e) =>
                      openRun(
                        readyRuns.find((r) => r.id === e.target.value)!,
                        'connect',
                      )
                    }
                  >
                    <option value="" disabled>
                      Choose a skill
                    </option>
                    {readyRuns.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              {!result || run?.status !== 'ready' ? (
                <div className="empty-library">
                  <Network size={34} />
                  <h3>First, create a skill</h3>
                  <p>Your trained methods will be available here.</p>
                  <button className="button primary" onClick={newSkill}>
                    Create a skill <ArrowRight size={15} />
                  </button>
                </div>
              ) : (
                <>
                  <div className="connection-summary">
                    <span className="sample-icon purple">
                      <Waypoints size={22} />
                    </span>
                    <div>
                      <strong>{run.name}</strong>
                      <span>
                        {result.selected_model} · {score(result.test_score, result)} test{' '}
                        {result.metric.toLowerCase()}
                      </span>
                    </div>
                    <Tag color="green">
                      <span className="dot" />
                      Ready to call
                    </Tag>
                  </div>
                  <div className="tabs">
                    {(
                      [
                        { id: 'playground', icon: FlaskConical, label: 'Try it out' },
                        { id: 'api', icon: Code2, label: 'REST API' },
                        { id: 'mcp', icon: Network, label: 'Agent connection' },
                      ] as const
                    ).map((t) => (
                      <button
                        className={connectionTab === t.id ? 'active' : ''}
                        key={t.id}
                        onClick={() => setConnectionTab(t.id)}
                      >
                        <t.icon size={16} />
                        {t.label}
                      </button>
                    ))}
                  </div>
                  {connectionTab === 'playground' && (
                    <div className="playground-layout">
                      <section className="panel">
                        <div className="panel-heading">
                          <h3>
                            <Braces size={17} /> Give it an input
                          </h3>
                          <button
                            className="text-button"
                            onClick={() => {
                              setInputs(result.example_input);
                              setPrediction(null);
                            }}
                          >
                            Reset example
                          </button>
                        </div>
                        <div className="panel-body">
                          <div className="prediction-fields">
                            {result.input_schema.map((c) => (
                              <label key={c.name}>
                                {pretty(c.name)}
                                {c.type === 'number' ? (
                                  <input
                                    type="number"
                                    step="any"
                                    value={inputs[c.name] ?? ''}
                                    onChange={(e) =>
                                      setInputs({
                                        ...inputs,
                                        [c.name]: e.target.value === '' ? null : e.target.value,
                                      })
                                    }
                                  />
                                ) : (
                                  <select
                                    value={String(inputs[c.name] ?? '')}
                                    onChange={(e) =>
                                      setInputs({ ...inputs, [c.name]: e.target.value })
                                    }
                                  >
                                    {[
                                      ...new Set([
                                        String(inputs[c.name] ?? ''),
                                        ...c.examples.map(String),
                                      ]),
                                    ].map((v) => (
                                      <option key={v} value={v}>
                                        {pretty(v)}
                                      </option>
                                    ))}
                                  </select>
                                )}
                                <small>
                                  {c.type === 'number'
                                    ? `Observed range: ${c.min}–${c.max}`
                                    : 'Category input'}
                                </small>
                              </label>
                            ))}
                          </div>
                          <button
                            className="button primary full"
                            disabled={!!busy}
                            onClick={runPrediction}
                          >
                            {busy === 'predict' ? (
                              <Loader2 className="spin" size={17} />
                            ) : (
                              <Zap size={17} />
                            )}{' '}
                            Run prediction <ArrowRight size={16} />
                          </button>
                          <div className="inference-note">
                            <ShieldCheck size={14} /> Runs your trained model. No language-model
                            call.
                          </div>
                        </div>
                      </section>
                      <section className="panel prediction-panel">
                        <div className="panel-heading">
                          <h3>
                            <Terminal size={17} /> Model response
                          </h3>
                          <Tag>Live inference</Tag>
                        </div>
                        {prediction ? (
                          <div className="panel-body">
                            <div className="prediction-outcome">
                              <span>PREDICTED {pretty(result.target).toUpperCase()}</span>
                              <strong>
                                {typeof prediction.predictions[0].value === 'number'
                                  ? prediction.predictions[0].value.toFixed(2)
                                  : pretty(prediction.predictions[0].value)}
                              </strong>
                            </div>
                            {prediction.predictions[0].probabilities && (
                              <div className="probabilities">
                                {Object.entries(prediction.predictions[0].probabilities).map(
                                  ([label, p]) => (
                                    <div key={label}>
                                      <span>{pretty(label)}</span>
                                      <div>
                                        <i style={{ width: `${p * 100}%` }} />
                                      </div>
                                      <strong>{(p * 100).toFixed(1)}%</strong>
                                    </div>
                                  ),
                                )}
                                <small>Model probabilities; not independently calibrated.</small>
                              </div>
                            )}
                            <div className="prediction-meta">
                              <span>
                                <Clock3 size={14} />
                                {prediction.inference_ms} ms
                              </span>
                              <span>
                                <Zap size={14} />0 LLM tokens
                              </span>
                            </div>
                            {prediction.warnings.map((w) => (
                              <div className="info-note" key={w}>
                                {w}
                              </div>
                            ))}
                            <div className="feedback-box">
                              <h4>Close the loop</h4>
                              <p>When you know what happened, save the actual outcome.</p>
                              <div>
                                {result.task === 'classification' ? (
                                  <select
                                    aria-label="Actual outcome"
                                    value={actual}
                                    onChange={(e) => setActual(e.target.value)}
                                  >
                                    <option value="">Choose actual outcome</option>
                                    {result.labels.map((l) => (
                                      <option key={l} value={l}>
                                        {pretty(l)}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    type="number"
                                    step="any"
                                    aria-label="Actual outcome"
                                    value={actual}
                                    onChange={(e) => setActual(e.target.value)}
                                    placeholder="Actual measured value"
                                  />
                                )}
                                <button
                                  className="button small-button"
                                  disabled={!!busy || !actual || feedbackSaved}
                                  onClick={() =>
                                    action('feedback', async () => {
                                      await api(
                                        `/api/predictions/${prediction.prediction_id}/feedback`,
                                        { actual },
                                      );
                                      setFeedbackSaved(true);
                                      setToast('Outcome saved. The model has not changed.');
                                    })
                                  }
                                >
                                  {feedbackSaved ? <Check size={14} /> : <Plus size={14} />}{' '}
                                  {feedbackSaved ? 'Saved' : 'Save'}
                                </button>
                              </div>
                              <small>Saved for review. Retraining is a separate experiment.</small>
                            </div>
                          </div>
                        ) : (
                          <div className="prediction-empty">
                            <div className="terminal-illustration">
                              <Terminal size={32} />
                            </div>
                            <h3>Ready when you are</h3>
                            <p>
                              Change the inputs and run a prediction.
                              <br />
                              The result comes from your trained model.
                            </p>
                            <span className="code-hint">input → model.predict() → result</span>
                          </div>
                        )}
                      </section>
                    </div>
                  )}
                  {connectionTab === 'api' && (
                    <section className="panel code-panel">
                      <div className="panel-heading">
                        <h3>
                          <Code2 size={17} /> Call your skill from any agent
                        </h3>
                        <button
                          className="button small-button"
                          onClick={() =>
                            copy(
                              `curl -X POST '${window.location.origin}/api/runs/${run.id}/predict' \\\n  -H 'Authorization: Bearer YOUR_FORGE_TOKEN' \\\n  -H 'Content-Type: application/json' \\\n  -d '${JSON.stringify({ records: [inputs] })}'`,
                              'API example',
                            )
                          }
                        >
                          <Copy size={14} />
                          Copy
                        </button>
                      </div>
                      <p>Your workspace token authenticates requests. Keep it private.</p>
                      <pre>
                        <code>{`curl -X POST '${window.location.origin}/api/runs/${run.id}/predict' \\\n  -H 'Authorization: Bearer YOUR_FORGE_TOKEN' \\\n  -H 'Content-Type: application/json' \\\n  -d '${JSON.stringify({ records: [inputs] }, null, 2)}'`}</code>
                      </pre>
                      <div className="code-actions">
                        <button
                          className="button"
                          onClick={() =>
                            action('token', async () => {
                              await navigator.clipboard.writeText(await accessToken());
                              setToast('Workspace token copied. Keep it private.');
                            })
                          }
                        >
                          <Copy size={15} /> Copy workspace token
                        </button>
                        <button
                          className="button"
                          onClick={() =>
                            action('schema', async () => {
                              const schema = await api(`/api/runs/${run.id}/tool`);
                              await navigator.clipboard.writeText(JSON.stringify(schema, null, 2));
                              setToast('Tool schema copied');
                            })
                          }
                        >
                          <Braces size={15} /> Copy tool schema
                        </button>
                      </div>
                    </section>
                  )}
                  {connectionTab === 'mcp' && (
                    <section className="panel code-panel">
                      <div className="panel-heading">
                        <h3>
                          <Network size={17} /> Connect through MCP
                        </h3>
                        <Tag>Streamable HTTP · Bearer token</Tag>
                      </div>
                      <p>
                        The server lists your ready skills as tools. Each tool calls its trained
                        model.
                      </p>
                      <pre>
                        <code>
                          {JSON.stringify(
                            {
                              mcpServers: {
                                forge: {
                                  type: 'http',
                                  url: `${window.location.origin}/mcp`,
                                  headers: { Authorization: 'Bearer YOUR_FORGE_TOKEN' },
                                },
                              },
                            },
                            null,
                            2,
                          )}
                        </code>
                      </pre>
                      <div className="code-actions">
                        <button
                          className="button"
                          onClick={() =>
                            copy(
                              JSON.stringify(
                                {
                                  mcpServers: {
                                    forge: {
                                      type: 'http',
                                      url: `${window.location.origin}/mcp`,
                                      headers: { Authorization: 'Bearer YOUR_FORGE_TOKEN' },
                                    },
                                  },
                                },
                                null,
                                2,
                              ),
                              'MCP configuration',
                            )
                          }
                        >
                          <Copy size={15} /> Copy configuration
                        </button>
                        <button
                          className="button"
                          onClick={() =>
                            action('mcp-test', async () => {
                              const response = await api<{ result: { tools: unknown[] } }>('/mcp', {
                                jsonrpc: '2.0',
                                id: 1,
                                method: 'tools/list',
                              });
                              setToast(
                                `MCP server returned ${response.result.tools.length} ready tool(s)`,
                              );
                            })
                          }
                        >
                          <Radio size={15} /> Test connection
                        </button>
                      </div>
                      <div className="info-note">
                        <CircleHelp size={16} />
                        Use a client that supports custom authorization headers. Workspace tokens
                        expire; refresh or copy a current token if needed. Local URLs require a
                        client on this machine.
                      </div>
                    </section>
                  )}
                </>
              )}
            </>
          )}

          {view === 'activity' && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">EVERY EXPERIMENT, ACCOUNTED FOR</div>
                  <h1>Activity</h1>
                  <p>Follow the work behind your agent’s capabilities.</p>
                </div>
                <button className="button" onClick={() => action('refresh', refresh)}>
                  <Radio size={16} />
                  Refresh
                </button>
              </div>
              {runs.length === 0 ? (
                <div className="empty-library">
                  <AudioLines size={34} />
                  <h3>A clean slate</h3>
                  <p>Your experiments will appear here.</p>
                  <button className="button primary" onClick={newSkill}>
                    Create a skill
                  </button>
                </div>
              ) : (
                <section className="panel activity-panel">
                  {runs.map((r) => (
                    <button key={r.id} onClick={() => openRun(r)}>
                      <span
                        className={`sample-icon ${r.status === 'failed' ? 'orange' : 'purple'}`}
                      >
                        <FlaskConical size={19} />
                      </span>
                      <span>
                        <strong>{r.name}</strong>
                        <small>
                          {r.payload.events.at(-1)?.title} · {when(r.created_at)}
                        </small>
                      </span>
                      <Tag
                        color={
                          r.status === 'ready'
                            ? 'green'
                            : r.status === 'failed'
                              ? 'orange'
                              : 'purple'
                        }
                      >
                        {r.status}
                      </Tag>
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </section>
              )}
            </>
          )}
          <footer className="footer">
            <span>
              <Logo small /> A little data goes a long way.
            </span>
            <span>
              Built for Supabase Select 2026 <span className="footer-dot">·</span>{' '}
              <button onClick={() => setGuide(true)}>
                How it works <ArrowUpRight size={12} />
              </button>
            </span>
          </footer>
        </main>
      </div>
      <input
        ref={fileInput}
        type="file"
        accept=".csv,text/csv"
        className="visually-hidden"
        aria-label="Upload CSV"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload(file);
          e.target.value = '';
        }}
      />
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={17} />
          {toast}
        </div>
      )}
      {guide && (
        <div className="modal-backdrop" onClick={() => setGuide(false)}>
          <section
            className="guide-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="guide-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              aria-label="Close guide"
              onClick={() => setGuide(false)}
            >
              <X size={20} />
            </button>
            <Logo />
            <h2 id="guide-title">From data to a new skill.</h2>
            <p>Forge builds small, specialized prediction tools your agent can call.</p>
            {[
              {
                icon: Database,
                title: 'Bring a dataset',
                text: 'Upload a CSV with historical inputs and known outcomes, or try a sample.',
              },
              {
                icon: Settings2,
                title: 'Define the task',
                text: 'Choose the outcome and inputs. Only use information available before the outcome.',
              },
              {
                icon: FlaskConical,
                title: 'Train and test',
                text: 'Compare a baseline with two ML methods. Select on validation; evaluate on separate test data.',
              },
              {
                icon: Network,
                title: 'Let your agent call it',
                text: 'Use the playground, REST endpoint, or MCP server. Save actual outcomes when they become available.',
              },
            ].map((s) => (
              <div className="guide-step" key={s.title}>
                <span>
                  <s.icon size={19} />
                </span>
                <div>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                </div>
              </div>
            ))}
            <div className="info-note">
              Your workspace uses an anonymous Supabase account. Clearing browser storage loses
              access to it. Predictions are estimates, and saved feedback does not automatically
              retrain models.
            </div>
            <button
              className="button primary full"
              onClick={() => {
                setGuide(false);
                newSkill();
              }}
            >
              Create a skill <ArrowRight size={17} />
            </button>
          </section>
        </div>
      )}
    </div>
  );
}
