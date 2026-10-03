import { useEffect, useState, type FormEvent } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  ChevronDown,
  Globe2,
  ImagePlus,
  Layers3,
  Plus,
  Radar,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { api } from '../api';
import type { Character, Config, Finding, Workspace } from '../types';
import { labels, shortDate, needsReview } from '../utils';
import { Badge, Loading, PageHeading, Empty } from './ui';

export function Discovery({
  data,
  asset,
  setAssetId,
  config,
  busy,
  work,
  refresh,
  onAdd,
  onDemo,
  onSelect,
}: {
  data: Workspace;
  asset?: Character;
  setAssetId: (id: string) => void;
  config?: Config;
  busy: string;
  work: (label: string, action: () => Promise<void>) => Promise<void>;
  refresh: () => Promise<void>;
  onAdd: () => void;
  onDemo: () => Promise<void>;
  onSelect: (finding: Finding) => void;
}) {
  const [source, setSource] = useState('public');
  const [query, setQuery] = useState('');
  const [urls, setUrls] = useState('');
  const [semantic, setSemantic] = useState(false);
  const [filter, setFilter] = useState('all');
  const [group, setGroup] = useState(true);
  useEffect(() => {
    setSource(asset?.payload.demo ? 'demo' : 'public');
    setQuery(asset ? asset.payload.aliases[0] || asset.name : '');
  }, [asset?.id]);
  const scans = data.scans.filter((s) => s.asset_id === asset?.id);
  const latest = scans[0];
  const active = latest?.status === 'queued' || latest?.status === 'searching';
  const findings = data.findings.filter((f) => f.scan_id === latest?.id);
  const filtered = findings.filter(
    (f) =>
      filter === 'all' ||
      (filter === 'review'
        ? needsReview(f)
        : filter === 'authorized'
          ? f.payload.review.decision === 'authorized' ||
            f.payload.permission.status === 'recorded_permission'
          : filter === 'dismissed'
            ? f.payload.review.decision === 'not_a_match' ||
              f.payload.match.kind === 'owner_rejected'
            : f.payload.review.decision === 'confirmed_match' ||
              f.payload.review.decision === 'investigate'),
  );
  const groups = new Map<string, Finding[]>();
  for (const f of filtered) {
    const key = group ? f.payload.image_sha256 || f.id : f.id;
    groups.set(key, [...(groups.get(key) || []), f]);
  }
  const rows = [...groups.values()].sort(
    (a, b) =>
      (a.some((f) => f.payload.priority === 'high') ? 0 : 1) -
      (b.some((f) => f.payload.priority === 'high') ? 0 : 1),
  );
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!asset) return;
    await work('scan', async () => {
      await api('/api/scans', {
        asset_id: asset.id,
        source,
        query,
        urls: urls
          .split('\n')
          .map((u) => u.trim())
          .filter(Boolean),
        limit: 12,
        semantic_review: semantic,
      });
      await refresh();
    });
  }
  return (
    <>
      <PageHeading
        eyebrow="IMAGE + TEXT DISCOVERY"
        title="Find the appearances."
        description="Search from reference artwork. Review the evidence before choosing an action."
        action={
          <button className="button secondary" onClick={onAdd}>
            <Plus size={16} />
            Add character
          </button>
        }
      />
      {!asset ? (
        <Empty
          icon={<Radar size={28} />}
          title="Who are we looking for?"
          text="Add reference artwork and a character name, or explore an original character with fictional listings."
          action={
            <div className="button-row">
              <button className="button primary" onClick={onAdd}>
                Add a character
              </button>
              <button className="button secondary" disabled={!!busy} onClick={onDemo}>
                Explore demo
              </button>
            </div>
          }
        />
      ) : (
        <>
          <div className="search-workspace">
            <div className="reference-card">
              <div className="reference-top">
                <span className="eyebrow">REFERENCE CHARACTER</span>
                {asset.payload.demo && <Badge>Demo</Badge>}
              </div>
              <img
                className="reference-image"
                src={asset.payload.references[0].thumbnail}
                alt={`${asset.name} reference artwork`}
              />
              <select
                aria-label="Character"
                value={asset.id}
                onChange={(e) => setAssetId(e.target.value)}
              >
                {data.assets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
              <span className="reference-caption">
                {asset.payload.references.length} reference image
                {asset.payload.references.length > 1 ? 's' : ''} · {asset.payload.aliases.length}{' '}
                alternate names
              </span>
            </div>
            <form className="search-form" onSubmit={submit}>
              <div className="section-heading">
                <h2>Start a discovery run</h2>
                <Radar size={18} />
              </div>
              <label>
                Search context
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  maxLength={250}
                  placeholder="Character name, alternate names, product terms…"
                />
              </label>
              <div className="form-row">
                <label>
                  Discovery source
                  <select
                    aria-label="Discovery source"
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                  >
                    {asset.payload.demo && <option value="demo">Fictional Orbit demo</option>}
                    <option value="public">Public collections · no key needed</option>
                    <option value="urls">Inspect supplied URLs</option>
                    <option value="google" disabled={!config?.providers.google}>
                      Google Web Detection{!config?.providers.google ? ' · key needed' : ''}
                    </option>
                    <option value="serpapi" disabled={!config?.providers.serpapi}>
                      Google Lens / SerpAPI{!config?.providers.serpapi ? ' · key needed' : ''}
                    </option>
                  </select>
                </label>
                <div className="search-limit">
                  <span>Bounded search</span>
                  <strong>12 candidates</strong>
                  <small>Up to 5 reference images</small>
                </div>
              </div>
              {source === 'urls' && (
                <label>
                  Public page or image URLs
                  <textarea
                    required
                    value={urls}
                    onChange={(e) => setUrls(e.target.value)}
                    placeholder="https://example.com/product\nOne URL per line, up to 10"
                    rows={3}
                  />
                </label>
              )}
              <div className="source-explanation">
                <Globe2 size={16} />
                <span>
                  {source === 'demo'
                    ? 'Six local fictional listings demonstrate review, permissions, and evidence export. No live search is performed.'
                    : source === 'public'
                      ? 'Searches Wikimedia Commons and Openverse by text, then compares returned images. These collections do not provide broad marketplace coverage.'
                      : source === 'urls'
                        ? 'Inspects the supplied pages or images. HTML pages use their social-preview image or first image; dynamic pages may need a direct image URL.'
                        : source === 'google'
                          ? 'Searches Google’s image index using the first reference image, then compares returned candidates against all references.'
                          : 'Searches Google Lens through SerpAPI using the first public reference URL and your search context. Uploaded private images need Google Web Detection instead.'}
                </span>
              </div>
              {config?.providers.gemini && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={semantic}
                    onChange={(e) => setSemantic(e.target.checked)}
                  />
                  Add Gemini character comparison<span>Images will be sent to Gemini</span>
                </label>
              )}
              <div className="search-form-bottom">
                <span>
                  <ShieldCheck size={14} />
                  Private reference storage
                </span>
                <button className="button primary" disabled={!!busy || active}>
                  {active || busy === 'scan' ? <Loading /> : <Search size={16} />}
                  {active ? 'Searching…' : 'Find appearances'}
                  <ArrowRight size={15} />
                </button>
              </div>
            </form>
          </div>
          {latest && (
            <div className={`coverage-bar ${latest.status === 'failed' ? 'failed' : ''}`}>
              <span className="coverage-icon">{active ? <Loading /> : <Globe2 size={18} />}</span>
              <div>
                <strong>
                  {active
                    ? latest.payload.events.at(-1)?.message || 'Searching sources…'
                    : latest.status === 'failed'
                      ? 'Search could not complete'
                      : `${latest.payload.finding_count} candidate appearances found`}
                </strong>
                <small>
                  {latest.payload.error ||
                    latest.payload.coverage.map((c) => `${c.source}: ${c.status}`).join(' · ') ||
                    'Waiting for source results'}
                </small>
                {!!latest.payload.reused_corrections && (
                  <small className="green-text">
                    {latest.payload.reused_corrections} identical-image correction(s) reused from
                    owner feedback
                  </small>
                )}
              </div>
              <Badge tone={latest.status === 'complete' ? 'green' : ''}>
                {latest.status === 'complete' ? 'Ready for review' : latest.status}
              </Badge>
            </div>
          )}
          <div className="results-toolbar">
            <div className="filter-tabs">
              {[
                ['all', 'All appearances'],
                ['review', 'Needs review'],
                ['confirmed', 'Confirmed'],
                ['authorized', 'Authorized'],
                ['dismissed', 'Dismissed'],
              ].map(([id, label]) => (
                <button
                  key={id}
                  className={filter === id ? 'active' : ''}
                  onClick={() => setFilter(id)}
                >
                  {label}
                  {id === 'all' && <span>{findings.length}</span>}
                </button>
              ))}
            </div>
            <label className="group-toggle">
              <input type="checkbox" checked={group} onChange={(e) => setGroup(e.target.checked)} />
              <Layers3 size={14} />
              Group identical images
            </label>
          </div>
          {rows.length ? (
            <div className="finding-grid">
              {rows.map((items) => {
                const f = items.find((row) => row.payload.priority === 'high') || items[0];
                const p = f.payload;
                return (
                  <button key={f.id} className="finding-card" onClick={() => onSelect(f)}>
                    <div className="finding-image">
                      {p.thumbnail ? (
                        <img src={p.thumbnail} alt={p.title} />
                      ) : (
                        <div className="missing-image">
                          <ImagePlus size={28} />
                          Image unavailable
                        </div>
                      )}
                      <Badge
                        tone={
                          p.match.kind === 'same_image' || p.match.kind === 'owner_confirmed'
                            ? 'green'
                            : ''
                        }
                      >
                        {labels[p.match.kind] || p.match.kind}
                      </Badge>
                      {items.length > 1 && (
                        <span className="duplicate-label">
                          <Layers3 size={12} />
                          {items.length} appearances
                        </span>
                      )}
                    </div>
                    <div className="finding-body">
                      <div className="domain-row">
                        <span>
                          <Globe2 size={12} />
                          {p.domain}
                        </span>
                        <ArrowUpRight size={15} />
                      </div>
                      <h3>{p.title}</h3>
                      <div className="finding-tags">
                        <Badge tone={p.priority === 'high' ? 'amber' : ''}>
                          {p.priority === 'high'
                            ? 'Priority review'
                            : p.priority === 'low'
                              ? 'Low priority'
                              : 'Review candidate'}
                        </Badge>
                        <span>{p.demo ? 'Fictional demo' : p.provider}</span>
                      </div>
                      <div className="finding-status">
                        <span
                          className={`status-dot ${p.permission.status === 'recorded_permission' || p.review.decision === 'authorized' ? 'green' : ''}`}
                        />
                        {p.review.decision !== 'unreviewed'
                          ? labels[p.review.decision]
                          : labels[p.permission.status]}
                        {p.reused_correction && <CheckCheck size={14} />}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <Empty
              icon={<Search size={26} />}
              title={
                latest
                  ? active
                    ? 'Following the trail…'
                    : 'No appearances in this view.'
                  : 'Your next search starts above.'
              }
              text={
                latest
                  ? active
                    ? 'Candidate images are being fetched and compared. Results will appear automatically.'
                    : 'Change the filter or search context. No results from these sources does not mean no online usage exists.'
                  : 'Choose the scope, run discovery, and inspect the returned candidates side by side.'
              }
            />
          )}
          {latest && (
            <details className="coverage-details">
              <summary>
                Source coverage & search history
                <ChevronDown size={15} />
              </summary>
              {latest.payload.coverage.map((c, i) => (
                <div key={i}>
                  <strong>
                    {c.source}
                    <Badge>{c.status}</Badge>
                  </strong>
                  <p>{c.detail}</p>
                  <small>Query: {c.query}</small>
                </div>
              ))}
              <h3>Previous runs</h3>
              {scans.map((s) => (
                <p key={s.id}>
                  {shortDate(s.created_at)} · {s.payload.request.source} · {s.status} ·{' '}
                  {s.payload.finding_count} candidates
                </p>
              ))}
            </details>
          )}
        </>
      )}
    </>
  );
}
