import { useState, type FormEvent } from 'react';
import { Check, FileCheck2, ImagePlus, Plus } from 'lucide-react';
import type { Character, License } from '../types';
import { Badge, Loading, Modal } from './ui';

export function AssetModal({
  busy,
  onClose,
  onSubmit,
}: {
  busy: boolean;
  onClose: () => void;
  onSubmit: (form?: FormData, body?: unknown) => Promise<void>;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState('upload');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (mode === 'upload') {
      form.delete('files');
      files.forEach((f) => form.append('files', f));
      await onSubmit(form);
    } else
      await onSubmit(undefined, {
        name: form.get('name'),
        description: form.get('description'),
        aliases: String(form.get('aliases') || '')
          .split(',')
          .map((x) => x.trim())
          .filter(Boolean),
        reference_urls: [form.get('reference_url')],
      });
  }
  return (
    <Modal title="Add a character" eyebrow="REFERENCE LIBRARY" onClose={onClose}>
      <p>Start with clear artwork and the names people might use online.</p>
      <form onSubmit={submit}>
        <label>
          Character name
          <input name="name" required maxLength={100} placeholder="e.g. Orbit" />
        </label>
        <label>
          Alternate names
          <input
            name="aliases"
            maxLength={500}
            placeholder="Comma-separated names, spellings, or franchise names"
          />
        </label>
        <label>
          Visual description
          <textarea
            name="description"
            rows={3}
            maxLength={1500}
            placeholder="Distinctive colors, clothing, features, and versions…"
          />
        </label>
        <div className="filter-tabs small-tabs">
          <button
            type="button"
            className={mode === 'upload' ? 'active' : ''}
            onClick={() => setMode('upload')}
          >
            Upload artwork
          </button>
          <button
            type="button"
            className={mode === 'url' ? 'active' : ''}
            onClick={() => setMode('url')}
          >
            Public image URL
          </button>
        </div>
        {mode === 'upload' ? (
          <label className="upload-zone">
            <ImagePlus size={27} />
            <strong>
              {files.length ? `${files.length} image(s) selected` : 'Choose reference images'}
            </strong>
            <span>PNG, JPEG, WebP, GIF · up to 5 images · 5 MB each</span>
            <input
              type="file"
              name="files"
              accept="image/png,image/jpeg,image/webp,image/gif"
              multiple
              required
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
            />
          </label>
        ) : (
          <label>
            Direct public image URL
            <input
              type="url"
              name="reference_url"
              required
              placeholder="https://example.com/character.png"
            />
            <small>Required for Lens discovery. Uploads work with Google Web Detection.</small>
          </label>
        )}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? <Loading /> : <Plus size={16} />}Add character
          </button>
        </div>
      </form>
    </Modal>
  );
}
export function LicenseModal({
  assets,
  assetId,
  busy,
  onClose,
  onSubmit,
}: {
  assets: Character[];
  assetId: string;
  busy: boolean;
  onClose: () => void;
  onSubmit: (body: unknown) => Promise<void>;
}) {
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    await onSubmit(Object.fromEntries(new FormData(e.currentTarget)));
  }
  return (
    <Modal title="Record a licensing request" eyebrow="LICENSING INTAKE" onClose={onClose}>
      <p>Capture the proposed scope for review by the IP owner.</p>
      <form onSubmit={submit}>
        <label>
          Character
          <select name="asset_id" defaultValue={assetId}>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <div className="form-row">
          <label>
            Applicant / company
            <input name="applicant" required maxLength={120} placeholder="Studio name" />
          </label>
          <label>
            Contact email
            <input name="email" type="email" maxLength={200} placeholder="hello@studio.com" />
          </label>
        </div>
        <label>
          Applicant website domain
          <input name="domain" required maxLength={200} placeholder="studio.com" />
        </label>
        <div className="form-row">
          <label>
            Product category
            <input name="category" required maxLength={80} placeholder="e.g. apparel" />
          </label>
          <label>
            Territory
            <input name="territory" required maxLength={80} placeholder="e.g. US" />
          </label>
        </div>
        <div className="form-row">
          <label>
            Starts on
            <input
              name="starts_on"
              type="date"
              required
              defaultValue={new Date().toISOString().slice(0, 10)}
            />
          </label>
          <label>
            Ends on
            <input name="ends_on" type="date" required />
          </label>
        </div>
        <label>
          Proposed usage
          <textarea
            name="description"
            maxLength={2000}
            rows={3}
            placeholder="Product, channels, quantities, and questions for the owner…"
          />
        </label>
        <small className="form-footnote">
          This records an inquiry. Approval records the owner's decision; Trace does not issue a
          legal license or contact the applicant.
        </small>
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? <Loading /> : <FileCheck2 size={16} />}Record request
          </button>
        </div>
      </form>
    </Modal>
  );
}
export function LicenseCard({
  license: l,
  character,
  busy,
  onDecision,
}: {
  license: License;
  character?: Character;
  busy: boolean;
  onDecision: (decision: string, note: string) => Promise<void>;
}) {
  const [note, setNote] = useState('');
  const p = l.payload;
  return (
    <div className="license-card">
      <div className="license-card-top">
        <span className="request-icon">
          <FileCheck2 size={20} />
        </span>
        <div>
          <h3>{p.applicant}</h3>
          <small>
            {p.domain} · {character?.name}
          </small>
        </div>
        <Badge tone={l.status === 'approved' ? 'green' : l.status === 'pending' ? 'amber' : ''}>
          {l.status.replaceAll('_', ' ')}
        </Badge>
      </div>
      <div className="license-scope">
        <span>
          <small>Product category</small>
          {p.category}
        </span>
        <span>
          <small>Territory</small>
          {p.territory}
        </span>
        <span>
          <small>Period</small>
          {p.starts_on} → {p.ends_on}
        </span>
      </div>
      <p>{p.description || 'No additional usage description supplied.'}</p>
      {l.status === 'pending' || l.status === 'needs_information' ? (
        <div className="license-actions">
          <input
            aria-label={`Decision note for ${p.applicant}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Owner decision note…"
            maxLength={2000}
          />
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => onDecision('needs_information', note)}
          >
            Needs information
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => onDecision('declined', note)}
          >
            Decline
          </button>
          <button
            className="button primary"
            disabled={busy}
            onClick={() => onDecision('approved', note)}
          >
            <Check size={15} />
            Record approval
          </button>
        </div>
      ) : (
        <small className="decision-note">{p.decision_note || 'Owner decision recorded.'}</small>
      )}
    </div>
  );
}
