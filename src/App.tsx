import { useEffect, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Code2,
  FileCheck2,
  Fingerprint,
  Globe2,
  ImagePlus,
  Layers3,
  LayoutDashboard,
  Plus,
  Radar,
  X,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { api, downloadEvidence, initialize, supabaseClient } from './api';
import type { Character, Config, Decision, Finding, Workspace } from './types';
import { labels, shortDate, needsReview } from './utils';
import { Mark, Badge, Loading, Stat, PageHeading, Empty } from './components/ui';
import { Discovery } from './components/Discovery';
import { AssetModal, LicenseModal, LicenseCard } from './components/Forms';
import { ReviewDrawer } from './components/ReviewDrawer';
import { AgentTools } from './components/AgentTools';

type Tab = 'overview' | 'discovery' | 'licensing' | 'evidence' | 'characters' | 'agents';
const empty: Workspace = {
  assets: [],
  scans: [],
  findings: [],
  licenses: [],
  grants: [],
  reviews: [],
};
const tabs = [
  { id: 'overview' as Tab, label: 'Overview', icon: LayoutDashboard },
  { id: 'discovery' as Tab, label: 'Discovery', icon: Radar },
  { id: 'licensing' as Tab, label: 'Licensing', icon: FileCheck2 },
  { id: 'evidence' as Tab, label: 'Evidence', icon: Fingerprint },
];
export default function App() {
  const [config, setConfig] = useState<Config>();
  const [data, setData] = useState<Workspace>(empty);
  const [tab, setTab] = useState<Tab>('overview');
  const [assetId, setAssetId] = useState('');
  const [selected, setSelected] = useState<Finding>();
  const [showAsset, setShowAsset] = useState(false);
  const [showLicense, setShowLicense] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const refreshRef = useRef<() => Promise<void>>(async () => {});
  async function refresh() {
    const workspace = await api<Workspace>('/api/workspace');
    setData(workspace);
    setAssetId((previous) => previous || workspace.assets[0]?.id || '');
    setSelected((previous) =>
      previous ? workspace.findings.find((f) => f.id === previous.id) : undefined,
    );
  }
  refreshRef.current = refresh;
  useEffect(() => {
    initialize()
      .then(async (c) => {
        setConfig(c);
        await refreshRef.current();
      })
      .catch((e) => setError(e.message));
  }, []);
  const running = data.scans.some((s) => s.status === 'queued' || s.status === 'searching');
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => refreshRef.current().catch((e) => setError(e.message)), 2000);
    return () => clearInterval(timer);
  }, [running]);
  useEffect(() => {
    const client = supabaseClient();
    if (!client || !config) return;
    const channel = client
      .channel('trace-scans')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'trace_scans' }, () =>
        refreshRef.current().catch(() => {}),
      )
      .subscribe();
    return () => {
      void client.removeChannel(channel);
    };
  }, [config]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 4500);
    return () => clearTimeout(timer);
  }, [notice]);
  const asset = data.assets.find((a) => a.id === assetId);
  async function work(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError('');
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy('');
    }
  }
  async function demo() {
    await work('demo', async () => {
      const a = await api<Character>('/api/examples/demo', {});
      setAssetId(a.id);
      await api('/api/scans', { asset_id: a.id, source: 'demo', limit: 12 });
      setTab('discovery');
      await refresh();
    });
  }
  async function publicExample() {
    await work('public-example', async () => {
      const a = await api<Character>('/api/examples/public', {});
      setAssetId(a.id);
      setTab('discovery');
      await refresh();
    });
  }
  async function exportFinding(id: string) {
    await work('export', async () => {
      await downloadEvidence(id);
      setNotice('Evidence bundle downloaded.');
    });
  }
  async function reviewFinding(
    finding: Finding,
    decision: Decision,
    note: string,
    category: string,
    territory: string,
  ) {
    await work('review', async () => {
      await api(`/api/findings/${finding.id}/review`, { decision, note, category, territory });
      await refresh();
      setNotice('Owner decision saved. Identical-image feedback is reusable.');
    });
  }
  const pending = data.licenses.filter(
    (l) => l.status === 'pending' || l.status === 'needs_information',
  ).length;
  const latestScanIds = new Set(
    data.assets.map((character) => data.scans.find((scan) => scan.asset_id === character.id)?.id),
  );
  const reviewCount = data.findings.filter(
    (finding) => latestScanIds.has(finding.scan_id) && needsReview(finding),
  ).length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setTab('overview')}>
          <Mark />
          <span>
            trace<span className="brand-dot">.</span>
          </span>
        </button>
        <div className="workspace-switch">
          <span className="workspace-avatar">S</span>
          <div>
            Studio workspace<small>Character & artwork protection</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-item ${tab === id ? 'active' : ''}`}
              onClick={() => setTab(id)}
            >
              <Icon size={18} />
              {label}
              {id === 'discovery' && reviewCount > 0 && (
                <span className="nav-count">{reviewCount}</span>
              )}
              {id === 'licensing' && pending > 0 && <span className="nav-count">{pending}</span>}
            </button>
          ))}
        </nav>
        <div className="nav-label second">LIBRARY</div>
        <button
          className={`nav-item ${tab === 'characters' ? 'active' : ''}`}
          onClick={() => setTab('characters')}
        >
          <Layers3 size={18} />
          Characters<span className="subtle-count">{data.assets.length}</span>
        </button>
        <div className="character-nav">
          {data.assets.slice(0, 5).map((a) => (
            <button
              key={a.id}
              className={assetId === a.id ? 'chosen' : ''}
              onClick={() => {
                setAssetId(a.id);
                setTab('discovery');
              }}
            >
              <img src={a.payload.references[0]?.thumbnail} alt="" />
              {a.name}
              {a.payload.demo && <span>DEMO</span>}
            </button>
          ))}
        </div>
        <button className="add-character-link" onClick={() => setShowAsset(true)}>
          <Plus size={14} />
          Add character
        </button>
        <div className="sidebar-bottom">
          <div className="agent-note">
            <span className="live-dot" />
            Built for agents, too.
            <p>Discover, review, and prepare evidence through one tool interface.</p>
            <button onClick={() => setTab('agents')}>
              Explore agent tools <ArrowUpRight size={14} />
            </button>
          </div>
          <button
            className={`nav-item ${tab === 'agents' ? 'active' : ''}`}
            onClick={() => setTab('agents')}
          >
            <Code2 size={18} />
            Agent tools
          </button>
          <div className="account">
            <span className="workspace-avatar">S</span>
            <div>
              Studio owner
              <small>
                {config?.mode === 'supabase'
                  ? 'Private Supabase workspace'
                  : 'Local demo workspace'}
              </small>
            </div>
            <ShieldCheck size={16} />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <select
            className="mobile-navigation"
            aria-label="Workspace view"
            value={tab}
            onChange={(event) => setTab(event.target.value as Tab)}
          >
            {tabs.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
            <option value="characters">Characters</option>
            <option value="agents">Agent tools</option>
          </select>
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <span>{tab === 'agents' ? 'Agent tools' : tab[0].toUpperCase() + tab.slice(1)}</span>
          </div>
          <div className="topbar-right">
            <span className="connection">
              <span className="live-dot" />
              {config ? 'Workspace connected' : 'Connecting'}
            </span>
            <button
              className="help-button"
              aria-label="How Trace works"
              onClick={() => setTab('agents')}
            >
              <CircleHelp size={18} />
            </button>
            <span className="avatar">S</span>
          </div>
        </header>
        <main>
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError('')}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="toast" role="status">
              <Check size={16} />
              {notice}
            </div>
          )}
          {!config && !error ? (
            <div className="loading-page">
              <Loading />
              Connecting your workspace…
            </div>
          ) : (
            <>
              {tab === 'overview' && (
                <>
                  <div className="page-heading">
                    <div>
                      <div className="eyebrow">
                        <span className="live-dot" />
                        CHARACTER USAGE INTELLIGENCE
                      </div>
                      <h1>
                        Every appearance.
                        <br />
                        <span>A clearer next step.</span>
                      </h1>
                      <p>
                        Find your artwork online. Understand the context.
                        <br className="desktop-break" /> Put the right evidence in the right hands.
                      </p>
                    </div>
                    <button className="button primary" onClick={() => setShowAsset(true)}>
                      <Plus size={16} />
                      Add character
                    </button>
                  </div>
                  <div className="stats-grid">
                    <Stat
                      label="Characters in your library"
                      value={data.assets.length}
                      icon={<Layers3 size={19} />}
                      foot="Reference artwork & alternate names"
                    />
                    <Stat
                      label="Appearances to review"
                      value={reviewCount}
                      icon={<Radar size={19} />}
                      foot="Candidates awaiting an owner decision"
                    />
                    <Stat
                      label="Licensing requests"
                      value={pending}
                      icon={<FileCheck2 size={19} />}
                      foot="Pending or waiting for more information"
                    />
                    <Stat
                      label="Verified owner decisions"
                      value={data.reviews.length}
                      icon={<CheckCheck size={19} />}
                      foot="Scoped feedback retained in your workspace"
                    />
                  </div>
                  <section className="intro-card">
                    <div className="intro-copy">
                      <Badge tone="green">
                        <Sparkles size={12} />
                        START WITH A CHARACTER
                      </Badge>
                      <h2>
                        Your artwork has a story.
                        <br />
                        See where it goes.
                      </h2>
                      <p>
                        Trace connects reference images with online appearances, permission records,
                        and a reviewable trail of evidence.
                      </p>
                      <div className="button-row">
                        <button className="button primary" disabled={!!busy} onClick={demo}>
                          {busy === 'demo' ? <Loading /> : <Radar size={16} />}Explore the Orbit
                          demo
                          <ArrowRight size={15} />
                        </button>
                        <button className="text-button" disabled={!!busy} onClick={publicExample}>
                          {busy === 'public-example' ? <Loading /> : <Globe2 size={15} />}Try a live
                          public example
                        </button>
                      </div>
                      <small>
                        Orbit uses fictional listings. The public example searches real image
                        collections.
                      </small>
                    </div>
                    <div className="intro-visual">
                      <div className="orbit-ring ring-one" />
                      <div className="orbit-ring ring-two" />
                      <img
                        src="/demo/reference.png"
                        alt="Orbit, an original space-cat demonstration character"
                      />
                      <div className="visual-label">
                        <span className="live-dot" />
                        <span>
                          Orbit<small>Original demo character</small>
                        </span>
                        <ShieldCheck size={18} />
                      </div>
                      <div className="floating-tag">
                        <Fingerprint size={15} />
                        Traceable by design
                      </div>
                    </div>
                  </section>
                  <div className="section-heading">
                    <h2>A connected workflow</h2>
                    <span>From discovery to a considered decision</span>
                  </div>
                  <div className="workflow-grid">
                    {[
                      {
                        n: '01',
                        icon: Radar,
                        title: 'Discover appearances',
                        text: 'Search from images and names. See exactly which sources were covered.',
                        to: 'discovery',
                      },
                      {
                        n: '02',
                        icon: FileCheck2,
                        title: 'Check permissions',
                        text: 'Compare usage with approved domains, product categories, territories, and dates.',
                        to: 'licensing',
                      },
                      {
                        n: '03',
                        icon: Fingerprint,
                        title: 'Prepare the evidence',
                        text: 'Capture the image, source, reasoning, and owner decisions in one export.',
                        to: 'evidence',
                      },
                    ].map(({ n, icon: Icon, title, text, to }) => (
                      <button className="workflow-card" key={n} onClick={() => setTab(to as Tab)}>
                        <div>
                          <Icon size={21} />
                          <span>{n}</span>
                        </div>
                        <h3>
                          {title}
                          <ArrowUpRight size={16} />
                        </h3>
                        <p>{text}</p>
                      </button>
                    ))}
                  </div>
                  {data.scans.length > 0 && (
                    <>
                      <div className="section-heading">
                        <h2>Recent searches</h2>
                        <button className="text-button" onClick={() => setTab('discovery')}>
                          View discovery
                          <ArrowRight size={14} />
                        </button>
                      </div>
                      <div className="table-card">
                        {data.scans.slice(0, 4).map((s) => (
                          <button
                            className="recent-scan"
                            key={s.id}
                            onClick={() => {
                              setAssetId(s.asset_id);
                              setTab('discovery');
                            }}
                          >
                            <Radar size={18} />
                            <strong>{data.assets.find((a) => a.id === s.asset_id)?.name}</strong>
                            <span>
                              {s.payload.request.source === 'demo'
                                ? 'Fictional demo'
                                : s.payload.request.source}
                            </span>
                            <Badge tone={s.status === 'complete' ? 'green' : ''}>{s.status}</Badge>
                            <small>{shortDate(s.created_at)}</small>
                            <ChevronRight size={15} />
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}
              {tab === 'discovery' && (
                <Discovery
                  data={data}
                  asset={asset}
                  setAssetId={setAssetId}
                  config={config}
                  busy={busy}
                  work={work}
                  refresh={refresh}
                  onAdd={() => setShowAsset(true)}
                  onDemo={demo}
                  onSelect={setSelected}
                />
              )}
              {tab === 'characters' && (
                <>
                  <PageHeading
                    eyebrow="REFERENCE LIBRARY"
                    title="Your characters"
                    description="A few good reference images give every search a stronger starting point."
                    action={
                      <button className="button primary" onClick={() => setShowAsset(true)}>
                        <Plus size={16} />
                        Add character
                      </button>
                    }
                  />
                  <div className="character-grid">
                    {data.assets.map((a) => (
                      <button
                        key={a.id}
                        className="library-card"
                        onClick={() => {
                          setAssetId(a.id);
                          setTab('discovery');
                        }}
                      >
                        <img src={a.payload.references[0]?.thumbnail} alt={a.name} />
                        <div>
                          <h3>
                            {a.name}
                            {a.payload.demo && <Badge>Demo</Badge>}
                          </h3>
                          <p>{a.payload.description}</p>
                          <span>
                            {a.payload.references.length} reference image
                            {a.payload.references.length > 1 ? 's' : ''}
                            <ArrowUpRight size={16} />
                          </span>
                        </div>
                      </button>
                    ))}
                    <button className="library-add" onClick={() => setShowAsset(true)}>
                      <ImagePlus size={30} />
                      <strong>Add a character</strong>
                      <span>Artwork, names, and context</span>
                    </button>
                  </div>
                </>
              )}
              {tab === 'licensing' && (
                <>
                  <PageHeading
                    eyebrow="PERMISSION WORKSPACE"
                    title="Less back-and-forth."
                    description="Collect the scope once. Keep approved permissions connected to discovery."
                    action={
                      <button
                        className="button primary"
                        disabled={!data.assets.length}
                        onClick={() => setShowLicense(true)}
                      >
                        <Plus size={16} />
                        New request
                      </button>
                    }
                  />
                  <div className="mini-stats">
                    <span>
                      <strong>{pending}</strong>Open requests
                    </span>
                    <span>
                      <strong>{data.grants.length}</strong>Approved permission records
                    </span>
                    <span>
                      <strong>{data.licenses.filter((l) => l.status === 'approved').length}</strong>
                      Requests approved here
                    </span>
                  </div>
                  <div className="section-heading">
                    <h2>Licensing requests</h2>
                    <span>Recording approval adds a scoped permission record</span>
                  </div>
                  {data.licenses.length ? (
                    <div className="license-list">
                      {data.licenses.map((l) => (
                        <LicenseCard
                          key={l.id}
                          license={l}
                          character={data.assets.find((a) => a.id === l.asset_id)}
                          busy={!!busy}
                          onDecision={(decision, note) =>
                            work('license-decision', async () => {
                              await api(`/api/licenses/${l.id}/decision`, { decision, note });
                              await refresh();
                              setNotice(
                                decision === 'approved'
                                  ? 'Approval recorded. Discovery now checks this permission scope.'
                                  : 'Request updated.',
                              );
                            })
                          }
                        />
                      ))}
                    </div>
                  ) : (
                    <Empty
                      icon={<FileCheck2 size={28} />}
                      title="The next collaboration starts here."
                      text="Record an inquiry with the applicant, product category, territory, and dates. A pending inquiry does not establish permission."
                      action={
                        <button
                          className="button primary"
                          disabled={!data.assets.length}
                          onClick={() => setShowLicense(true)}
                        >
                          <Plus size={16} />
                          Create a request
                        </button>
                      }
                    />
                  )}
                  <div className="section-heading">
                    <h2>Permission records</h2>
                    <span>Exact domain and scope checks; unknown context stays unresolved</span>
                  </div>
                  <div className="table-card">
                    {data.grants.length ? (
                      data.grants.map((g) => (
                        <div className="grant-row" key={g.id}>
                          <ShieldCheck size={20} />
                          <div>
                            <strong>{g.payload.applicant}</strong>
                            <small>{g.payload.domain}</small>
                          </div>
                          <span>{data.assets.find((a) => a.id === g.asset_id)?.name}</span>
                          <Badge>{g.payload.category}</Badge>
                          <span>{g.payload.territory}</span>
                          <small>
                            {g.payload.starts_on} → {g.payload.ends_on}
                          </small>
                        </div>
                      ))
                    ) : (
                      <p className="empty-inline">No approved permissions have been recorded.</p>
                    )}
                  </div>
                </>
              )}
              {tab === 'evidence' && (
                <>
                  <PageHeading
                    eyebrow="REVIEW & HANDOFF"
                    title="Evidence, with context."
                    description="Export captured images, source details, permission context, and the complete review history."
                  />
                  <div className="info-strip">
                    <Fingerprint size={18} />
                    <span>
                      Each bundle includes a captured-image SHA-256 digest and reference artwork. It
                      supports review; it does not establish infringement or financial loss.
                    </span>
                  </div>
                  {data.findings.length ? (
                    <div className="evidence-list">
                      {data.findings
                        .filter((f) => f.payload.evidence_path)
                        .map((f) => (
                          <div className="evidence-row" key={f.id}>
                            <img src={f.payload.thumbnail} alt="" />
                            <div>
                              <strong>{f.payload.title}</strong>
                              <small>
                                {f.payload.domain} · {shortDate(f.payload.captured_at)}
                                {f.payload.demo ? ' · Fictional demo' : ''}
                              </small>
                            </div>
                            <Badge>{labels[f.payload.review.decision]}</Badge>
                            <button
                              className="button secondary"
                              disabled={!!busy}
                              onClick={() => exportFinding(f.id)}
                            >
                              <ArrowDownToLine size={15} />
                              Export bundle
                            </button>
                          </div>
                        ))}
                    </div>
                  ) : (
                    <Empty
                      icon={<Fingerprint size={28} />}
                      title="A clear trail starts with discovery."
                      text="Run a search and review an appearance. Trace preserves the evidence alongside your reasoning."
                      action={
                        <button className="button primary" onClick={() => setTab('discovery')}>
                          Go to discovery
                          <ArrowRight size={15} />
                        </button>
                      }
                    />
                  )}
                </>
              )}
              {tab === 'agents' && (
                <AgentTools assets={data.assets} asset={asset} notify={setNotice} />
              )}
              <footer className="page-footer">
                <span>
                  <Mark small />
                  Trace the appearance. Keep the context.
                </span>
                <span>Owner-reviewed · Permission-aware · Agent-accessible</span>
              </footer>
            </>
          )}
        </main>
      </div>
      {showAsset && (
        <AssetModal
          busy={!!busy}
          onClose={() => setShowAsset(false)}
          onSubmit={(form, body) =>
            work('asset', async () => {
              const a = await api<Character>(
                form ? '/api/assets/upload' : '/api/assets',
                body,
                form,
              );
              setAssetId(a.id);
              setShowAsset(false);
              setTab('discovery');
              await refresh();
              setNotice('Character added. Choose a source to start discovery.');
            })
          }
        />
      )}
      {showLicense && (
        <LicenseModal
          assets={data.assets}
          assetId={assetId}
          busy={!!busy}
          onClose={() => setShowLicense(false)}
          onSubmit={(body) =>
            work('license', async () => {
              await api('/api/licenses', body);
              setShowLicense(false);
              await refresh();
              setNotice('Request recorded for owner review.');
            })
          }
        />
      )}
      {selected && (
        <ReviewDrawer
          finding={selected}
          asset={data.assets.find((a) => a.id === selected.asset_id)}
          related={data.findings.filter(
            (f) =>
              f.scan_id === selected.scan_id &&
              f.payload.image_sha256 &&
              f.payload.image_sha256 === selected.payload.image_sha256,
          )}
          busy={!!busy}
          onClose={() => setSelected(undefined)}
          onReview={reviewFinding}
          onExport={exportFinding}
        />
      )}
    </div>
  );
}
