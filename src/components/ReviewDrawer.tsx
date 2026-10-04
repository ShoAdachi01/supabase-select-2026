import { useEffect, useState } from 'react';
import {
  ArrowDownToLine,
  Check,
  ExternalLink,
  Fingerprint,
  Globe2,
  Sparkles,
  X,
} from 'lucide-react';
import type { Character, Decision, Finding } from '../types';
import { labels, shortDate } from '../utils';
import { Badge } from './ui';

export function ReviewDrawer({
  finding: f,
  asset,
  related,
  busy,
  onClose,
  onReview,
  onExport,
}: {
  finding: Finding;
  asset?: Character;
  related: Finding[];
  busy: boolean;
  onClose: () => void;
  onReview: (
    finding: Finding,
    decision: Decision,
    note: string,
    category: string,
    territory: string,
  ) => Promise<void>;
  onExport: (id: string) => Promise<void>;
}) {
  const p = f.payload;
  const [note, setNote] = useState(p.review.note || '');
  const [category, setCategory] = useState(p.category);
  const [territory, setTerritory] = useState(p.territory);
  useEffect(() => {
    setNote(p.review.note || '');
    setCategory(p.category);
    setTerritory(p.territory);
  }, [f.id]);
  const reference = asset?.payload.references[p.match.reference_index || 0];
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="review-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Review appearance"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="drawer-top">
          <div className="eyebrow">APPEARANCE REVIEW</div>
          <button className="close-button" aria-label="Close review" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <h2>{p.title}</h2>
        <div className="drawer-subtitle">
          <Globe2 size={14} />
          {p.domain}
          {p.demo && <Badge>Fictional demo</Badge>}
        </div>
        <div className="comparison">
          <div>
            <span>REFERENCE · {asset?.name}</span>
            <img src={reference?.thumbnail} alt="Reference artwork" />
          </div>
          <div>
            <span>DISCOVERED IMAGE</span>
            {p.thumbnail ? (
              <img src={p.thumbnail} alt="Discovered candidate" />
            ) : (
              <div className="missing-image">Image unavailable</div>
            )}
          </div>
        </div>
        <div className="assessment">
          <div>
            <Fingerprint size={18} />
            <strong>{labels[p.match.kind] || p.match.kind}</strong>
          </div>
          <p>{p.match.reason}</p>
          <small>
            Method: {p.match.method}
            {p.match.distance !== undefined
              ? ` · fingerprint distance ${p.match.distance}/63 (not a probability)`
              : ''}
          </small>
        </div>
        {p.semantic_review && (
          <div className="assessment">
            <div>
              <Sparkles size={18} />
              <strong>{labels[p.semantic_review.kind]}</strong>
            </div>
            <p>{p.semantic_review.reason}</p>
            <small>{p.semantic_review.provider} · model assessment, owner review required</small>
          </div>
        )}
        {p.semantic_review_error && <p className="form-footnote">{p.semantic_review_error}</p>}
        <div className="drawer-section">
          <h3>Permission & priority</h3>
          <div className="button-row">
            <Badge tone={p.permission.status === 'recorded_permission' ? 'green' : ''}>
              {labels[p.permission.status]}
            </Badge>
            <Badge tone={p.priority === 'high' ? 'amber' : ''}>{p.priority} priority</Badge>
          </div>
          <p>{p.permission.reason}</p>
          <small>{p.priority_reason}</small>
        </div>
        <div className="drawer-section">
          <h3>Source evidence</h3>
          {p.demo ? (
            <span className="source-link">
              {p.url} <Badge>Fictional URL</Badge>
            </span>
          ) : (
            <a className="source-link" href={p.url} target="_blank" rel="noreferrer">
              Open source page
              <ExternalLink size={14} />
            </a>
          )}
          <dl>
            <dt>Captured</dt>
            <dd>{shortDate(p.captured_at)}</dd>
            <dt>Source</dt>
            <dd>{p.provider || 'Fictional demo fixtures'}</dd>
            <dt>Image digest</dt>
            <dd className="digest">{p.capture_sha256 || 'No image capture available'}</dd>
          </dl>
          {related.length > 1 && (
            <details>
              <summary>{related.length} appearances use identical image pixels</summary>
              {related.map((row) => (
                <p key={row.id}>
                  {row.payload.domain} · {row.payload.title}
                </p>
              ))}
            </details>
          )}
        </div>
        <div className="drawer-section">
          <h3>Your decision</h3>
          <p>
            A matching image establishes an appearance. Record the usage context and the decision
            you can support.
          </p>
          <div className="form-row">
            <label>
              Product category
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                maxLength={80}
              />
            </label>
            <label>
              Territory
              <input
                value={territory}
                onChange={(e) => setTerritory(e.target.value)}
                maxLength={80}
              />
            </label>
          </div>
          <label>
            Review note
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="What did you verify? What still needs investigation?"
            />
          </label>
          <div className="decision-grid">
            {(['confirmed_match', 'authorized', 'not_a_match', 'investigate'] as Decision[]).map(
              (d) => (
                <button
                  key={d}
                  className={`button ${p.review.decision === d ? 'primary' : 'secondary'}`}
                  disabled={busy}
                  onClick={() => onReview(f, d, note, category, territory)}
                >
                  {p.review.decision === d && <Check size={14} />}
                  {labels[d]}
                </button>
              ),
            )}
          </div>
          {p.review.at && (
            <small className="decision-note">
              Last owner decision: {labels[p.review.decision]} · {shortDate(p.review.at)}
            </small>
          )}
        </div>
        <div className="drawer-export">
          <span>Reference artwork + capture + review history</span>
          <button className="button primary" disabled={busy} onClick={() => onExport(f.id)}>
            <ArrowDownToLine size={16} />
            Export evidence bundle
          </button>
        </div>
      </aside>
    </div>
  );
}
