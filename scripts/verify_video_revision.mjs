// Run after test:video:e2e; revises its film through the official MCP client.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const origin = process.env.CUTROOM_URL || 'http://127.0.0.1:8000';
const folder = '.cutroom/verification';
const result = JSON.parse(await readFile(`${folder}/result.json`, 'utf8'));
const state = JSON.parse(await readFile(`${folder}/browser-session.json`, 'utf8'));
const stored = state.origins
  .flatMap((o) => o.localStorage)
  .find((s) => s.name.endsWith('-auth-token'));
assert.ok(stored, 'Run test:video:e2e with Supabase first.');
const session = JSON.parse(stored.value);
const client = new Client({ name: 'cutroom-revision-test', version: '1.0.0' });
async function call(name, arguments_) {
  const response = await client.callTool({ name, arguments: arguments_ });
  assert.equal(response.isError, false, response.content?.[0]?.text);
  return JSON.parse(response.content[0].text);
}
try {
  await client.connect(
    new StreamableHTTPClientTransport(new URL(`${origin}/mcp`), {
      requestInit: { headers: { Authorization: `Bearer ${session.access_token}` } },
    }),
  );
  const before = await call('get_video', { video_id: result.video_id });
  const capture = before.payload.scenes.map(({ start, end, thumbnail }) => ({
    start,
    end,
    thumbnail,
  }));
  const narration = before.payload.scenes.map((s) => s.narration);
  narration[0] =
    'Meet Meridian. Open a project, see its board, and check progress in one shared workspace.';
  let job = await call('render_video', {
    video_id: result.video_id,
    narration,
    voice: 'cedar',
    music: 'none',
    theme: 'paper',
  });
  for (let i = 0; i < 180; i++) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    job = await call('get_video', { video_id: result.video_id });
    if (['complete', 'failed', 'cancelled'].includes(job.status)) break;
  }
  assert.equal(job.status, 'complete', job.payload.events.at(-1).message);
  assert.equal(job.payload.revision, before.payload.revision + 1);
  assert.equal(job.payload.voice, 'cedar');
  assert.equal(job.payload.music, 'none');
  assert.equal(job.payload.theme, 'paper');
  assert.deepEqual(
    job.payload.scenes.map((s) => s.narration),
    narration,
  );
  assert.deepEqual(
    job.payload.scenes.map(({ start, end, thumbnail }) => ({ start, end, thumbnail })),
    capture,
  );
  const film = await call('export_video', { video_id: result.video_id });
  assert.ok(film.url.startsWith('http'), 'MCP export must return an absolute URL.');
  const response = await fetch(film.url);
  assert.equal(response.status, 200);
  await writeFile(`${folder}/revised-film.mp4`, new Uint8Array(await response.arrayBuffer()));
  console.log(
    'PASS: narration, voice, music and theme edits through MCP; new private MP4 revision reuses the original captured scenes.',
  );
} finally {
  await client.close();
}
