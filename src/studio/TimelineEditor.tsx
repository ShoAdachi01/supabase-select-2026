import {
  ArrowDown,
  ArrowUp,
  Copy,
  Film,
  Mic,
  Play,
  Plus,
  Scissors,
  Type,
  Undo2,
} from 'lucide-react';
import { useState } from 'react';
import type { Scene, TimelineClip } from './types';

export function newTitle(layout: TimelineClip['layout'] = 'hook'): TimelineClip {
  return {
    id: crypto.randomUUID(),
    kind: 'title',
    label: 'Animated title',
    narration: '',
    headline: 'Your next big thing.',
    subtitle: '',
    layout,
    duration: 4,
    trim_start: 0,
    enabled: true,
    transition: 'cut',
    camera: 'wide',
    motion: layout === 'outro' ? 'resolve' : layout === 'benefit' ? 'panels' : 'reveal',
  };
}

export function initialClips(scenes: Scene[]): TimelineClip[] {
  return scenes.map((s, i) => ({
    ...newTitle(),
    id: `take-${i}`,
    kind: 'browser',
    motion: 'none',
    scene_id: s.thumbnail || `capture-${i}`,
    label: s.label,
    narration: s.narration,
    headline: '',
  }));
}

export default function TimelineEditor({
  clips,
  scenes,
  onChange,
  onPlan,
  onPreview,
  disabled,
  planning,
  previewing,
}: {
  clips: TimelineClip[];
  scenes: Scene[];
  onChange: (clips: TimelineClip[]) => void;
  onPlan: () => void;
  onPreview: (text: string) => void;
  disabled: boolean;
  planning: boolean;
  previewing: boolean;
}) {
  const [selected, setSelected] = useState('');
  const clip = clips.find((c) => c.id === selected) || clips[0];
  const index = clips.indexOf(clip);
  const source = scenes.find((s, i) => (s.thumbnail || `capture-${i}`) === clip?.scene_id);
  const available = source ? Math.max(0.25, source.end - source.start) : 0;
  const patch = (change: Partial<TimelineClip>) =>
    onChange(clips.map((c) => (c.id === clip.id ? { ...c, ...change } : c)));
  function move(direction: number) {
    const next = [...clips];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    setSelected(clip.id);
    onChange(next);
  }
  return (
    <div className="timeline-editor">
      <div className="inspector-intro">
        <Scissors size={16} />
        <h3>Shape the story.</h3>
        <p>Edit the words. Cut the pauses. Give the launch a little rhythm.</p>
      </div>
      <div className="timeline-actions">
        <button
          className="text-button"
          disabled={disabled || planning || clips.length > 20}
          onClick={onPlan}
        >
          <Type size={13} />
          {planning ? 'Planning launch…' : 'Add launch sequence'}
        </button>
        <button
          className="text-button"
          disabled={disabled || clips.length >= 24}
          onClick={() => {
            const title = newTitle();
            onChange([...clips, title]);
            setSelected(title.id);
          }}
        >
          <Plus size={13} />
          Title
        </button>
      </div>
      <div className="edit-clip-list" aria-label="Editable scenes">
        {clips.map((c, i) => (
          <button
            key={c.id}
            disabled={disabled}
            className={`edit-clip ${c.id === clip?.id ? 'selected' : ''} ${!c.enabled ? 'excluded' : ''}`}
            onClick={() => setSelected(c.id)}
          >
            <span>{c.kind === 'browser' ? <Film size={13} /> : <Type size={13} />}</span>
            <span>
              <b>
                {String(i + 1).padStart(2, '0')} · {c.label}
              </b>
              <small>
                {!c.enabled
                  ? 'Cut from film'
                  : c.kind === 'browser'
                    ? 'Product footage'
                    : c.kind === 'generated'
                      ? 'Generated animation'
                      : 'Animated typography'}
              </small>
            </span>
          </button>
        ))}
      </div>
      {clip && (
        <div className="clip-controls">
          <div className="clip-toolbar">
            <button
              aria-label="Move scene earlier"
              title="Move earlier"
              disabled={disabled || index === 0}
              onClick={() => move(-1)}
            >
              <ArrowUp size={14} />
            </button>
            <button
              aria-label="Move scene later"
              title="Move later"
              disabled={disabled || index === clips.length - 1}
              onClick={() => move(1)}
            >
              <ArrowDown size={14} />
            </button>
            <button
              aria-label="Duplicate scene"
              title="Duplicate"
              disabled={disabled || clips.length >= 24}
              onClick={() => {
                const duplicate = { ...clip, id: crypto.randomUUID() };
                onChange([...clips.slice(0, index + 1), duplicate, ...clips.slice(index + 1)]);
                setSelected(duplicate.id);
              }}
            >
              <Copy size={14} />
            </button>
            <button
              className={!clip.enabled ? 'restore' : ''}
              disabled={disabled}
              onClick={() => patch({ enabled: !clip.enabled })}
            >
              {clip.enabled ? <Scissors size={14} /> : <Undo2 size={14} />}
              {clip.enabled ? 'Cut scene' : 'Restore scene'}
            </button>
          </div>
          <label>
            Scene name
            <input
              value={clip.label}
              maxLength={100}
              disabled={disabled}
              onChange={(e) => patch({ label: e.target.value })}
            />
          </label>
          {clip.kind !== 'browser' && (
            <>
              <label>
                Headline
                <textarea
                  aria-label="Animation headline"
                  rows={2}
                  value={clip.headline}
                  maxLength={180}
                  disabled={disabled}
                  onChange={(e) => patch({ headline: e.target.value })}
                />
              </label>
              <label>
                Supporting line
                <input
                  value={clip.subtitle}
                  maxLength={240}
                  disabled={disabled}
                  onChange={(e) => patch({ subtitle: e.target.value })}
                />
              </label>
              {clip.kind === 'title' && (
                <label>
                  Motion layout
                  <select
                    value={clip.layout}
                    disabled={disabled}
                    onChange={(e) => patch({ layout: e.target.value as TimelineClip['layout'] })}
                  >
                    <option value="hook">Product reveal</option>
                    <option value="benefit">Feature spotlight</option>
                    <option value="outro">Closing invitation</option>
                  </select>
                </label>
              )}
            </>
          )}
          <label>
            Shot duration (seconds)
            <input
              aria-label="Shot duration"
              type="number"
              min={1}
              max={clip.kind === 'generated' ? clip.duration : 15}
              step={0.1}
              value={clip.duration}
              disabled={disabled}
              onChange={(e) => patch({ duration: Number(e.target.value) })}
            />
          </label>
          {clip.kind !== 'generated' && (
            <label>
              Motion treatment
              <select
                aria-label="Motion treatment"
                value={clip.motion || 'none'}
                disabled={disabled}
                onChange={(e) => patch({ motion: e.target.value as TimelineClip['motion'] })}
              >
                <option value="none">Original footage / classic title</option>
                {clip.kind === 'browser' ? (
                  <option value="detail">Detail → overview</option>
                ) : (
                  <>
                    <option value="reveal">Continuous product reveal</option>
                    <option value="panels">Layered product details</option>
                    <option value="resolve">Kinetic closing line</option>
                  </>
                )}
              </select>
            </label>
          )}
          {clip.kind === 'browser' && (!clip.motion || clip.motion === 'none') && (
            <label>
              Camera
              <select
                value={clip.camera || 'wide'}
                disabled={disabled}
                onChange={(e) => patch({ camera: e.target.value as TimelineClip['camera'] })}
              >
                <option value="wide">Full screen · steady</option>
                <option value="push">Gentle push toward action</option>
              </select>
            </label>
          )}
          {source && (
            <>
              <div className="trim-fields">
                <label>
                  Trim in (s)
                  <input
                    aria-label="Trim start"
                    type="number"
                    min={0}
                    max={Math.max(0, (clip.trim_end ?? available) - 0.25)}
                    step={0.1}
                    value={clip.trim_start}
                    disabled={disabled}
                    onChange={(e) => patch({ trim_start: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Trim out (s)
                  <input
                    aria-label="Trim end"
                    type="number"
                    min={clip.trim_start + 0.25}
                    max={Number(available.toFixed(3))}
                    step={0.1}
                    value={clip.trim_end ?? Number(available.toFixed(3))}
                    disabled={disabled}
                    onChange={(e) => patch({ trim_end: Number(e.target.value) })}
                  />
                </label>
              </div>
              <small className="field-hint">
                Trims are relative to this {available.toFixed(1)}s capture. Shorten the voiceover to
                keep the edit tight; longer speech extends the shot.
              </small>
            </>
          )}
          <label>
            <span className="narration-label">
              <Mic size={13} />
              Narration
            </span>
            <textarea
              aria-label="Selected scene narration"
              rows={4}
              value={clip.narration}
              maxLength={1000}
              disabled={disabled}
              placeholder="Write the exact words to speak. Leave blank for music only."
              onChange={(e) => patch({ narration: e.target.value })}
            />
          </label>
          {clip.narration.trim().split(/\s+/).length > clip.duration * 2.5 && (
            <small className="field-hint">
              This script may run past the shot. Aim for about {Math.floor(clip.duration * 2.3)}{' '}
              words.
            </small>
          )}
          <button
            className="text-button"
            disabled={disabled || !clip.narration.trim() || previewing}
            onClick={() => onPreview(clip.narration)}
          >
            <Play size={12} />
            {previewing ? 'Playing…' : 'Hear these words'}
          </button>
          <label>
            Transition to next scene
            <select
              value={clip.transition}
              disabled={disabled}
              onChange={(e) => patch({ transition: e.target.value as TimelineClip['transition'] })}
            >
              <option value="dissolve">Smooth dissolve</option>
              <option value="cut">Clean cut</option>
              <option value="fade">Dip to black</option>
            </select>
          </label>
        </div>
      )}
      {!clips.length && <p className="inspector-empty">Captured scenes will appear here.</p>}
    </div>
  );
}
