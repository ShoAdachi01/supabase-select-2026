import { useState } from 'react';
import { Code2, Copy, ShieldCheck } from 'lucide-react';
import { accessToken, api } from '../api';
import type { Character } from '../types';
import { Badge, Loading, PageHeading } from './ui';

export function AgentTools({
  assets,
  asset,
  notify,
}: {
  assets: Character[];
  asset?: Character;
  notify: (value: string) => void;
}) {
  const [result, setResult] = useState('');
  const [busy, setBusy] = useState(false);
  const origin = window.location.origin;
  const example = JSON.stringify(
    {
      name: 'find_character_usage',
      arguments: {
        asset_id: asset?.id || 'YOUR_CHARACTER_ID',
        source: asset?.payload.demo ? 'demo' : 'public',
        query: asset?.payload.aliases[0] || asset?.name || 'Character name',
        limit: 12,
      },
    },
    null,
    2,
  );
  async function inspect() {
    setBusy(true);
    try {
      const response = await api<{ result: unknown }>('/mcp', {
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/list',
      });
      setResult(JSON.stringify(response.result, null, 2));
    } catch (e) {
      setResult(e instanceof Error ? e.message : 'Unable to list tools.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="BUILD WHAT AGENTS WANT"
        title="Give your agent a trail."
        description="A callable discovery capability, with source coverage and evidence an agent can inspect."
      />
      <div className="agent-hero">
        <span className="agent-symbol">
          <Code2 size={30} />
        </span>
        <div>
          <Badge tone="green">STREAMABLE HTTP MCP</Badge>
          <h2>Artwork in. Reviewable appearances out.</h2>
          <p>
            Seven tools connect character references, online search, licensing intake, owner
            feedback, and evidence handoff.
          </p>
        </div>
      </div>
      <div className="agent-columns">
        <section className="code-card">
          <div className="section-heading">
            <h3>Connect your agent</h3>
            <Badge>Bearer authentication</Badge>
          </div>
          <label>
            Endpoint
            <div className="endpoint">
              <code>{origin}/mcp</code>
              <button
                aria-label="Copy MCP endpoint"
                onClick={async () => {
                  await navigator.clipboard.writeText(`${origin}/mcp`);
                  notify('MCP endpoint copied.');
                }}
              >
                <Copy size={15} />
              </button>
            </div>
          </label>
          <p>
            Use this workspace's session token in the Authorization header. Tokens expire; this
            prototype does not provide a public OAuth connector.
          </p>
          <button
            className="button secondary"
            onClick={async () => {
              await navigator.clipboard.writeText(await accessToken());
              notify('Session token copied. Keep it private.');
            }}
          >
            <Copy size={14} />
            Copy workspace session token
          </button>
          <h3>Example tool call</h3>
          <pre>{example}</pre>
          <small>{assets.length} character(s) available in this workspace.</small>
        </section>
        <section className="tool-card">
          <h3>Tools your agent can call</h3>
          {[
            ['list_characters', 'Read reference artwork and character context.'],
            ['find_character_usage', 'Start a scoped, bounded search.'],
            ['get_scan', 'Poll progress and inspect source coverage.'],
            ['list_usage_findings', 'Read evidence, priorities, and permission context.'],
            ['submit_license_request', 'Record an inquiry for owner review.'],
            ['record_usage_review', 'Persist an owner-directed decision.'],
            ['prepare_evidence', 'Get an authenticated evidence export path.'],
          ].map(([name, description]) => (
            <div className="tool-row" key={name}>
              <code>{name}</code>
              <span>{description}</span>
            </div>
          ))}
          <button className="button secondary" disabled={busy} onClick={inspect}>
            {busy ? <Loading /> : <Code2 size={15} />}Inspect live tool schemas
          </button>
        </section>
      </div>
      {result && <pre className="schema-result">{result}</pre>}
      <div className="info-strip">
        <ShieldCheck size={19} />
        <span>
          Trace searches accessible sources and preserves uncertainty. Owner decisions are required
          for authorization and action; the tools do not send notices or file claims.
        </span>
      </div>
    </>
  );
}
