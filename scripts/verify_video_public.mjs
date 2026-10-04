// Exercises the URL path through MCP against Playwright's public, localStorage-only demo.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const origin = process.env.CUTROOM_URL || 'http://127.0.0.1:8000';
const config = await (await fetch(`${origin}/api/config`)).json();
assert.ok(
  config.video.reasoning && config.video.narration,
  'Live provider keys are required for this test.',
);
const session = await (
  await fetch(`${config.supabase_url}/auth/v1/signup`, {
    method: 'POST',
    headers: { apikey: config.supabase_key, 'Content-Type': 'application/json' },
    body: '{}',
  })
).json();
const client = new Client({ name: 'cutroom-public-url-test', version: '1.0.0' });
async function call(name, arguments_ = {}) {
  const result = await client.callTool({ name, arguments: arguments_ });
  assert.equal(result.isError, false, result.content?.[0]?.text);
  return JSON.parse(result.content[0].text);
}
try {
  await client.connect(
    new StreamableHTTPClientTransport(new URL(`${origin}/mcp`), {
      requestInit: { headers: { Authorization: `Bearer ${session.access_token}` } },
    }),
  );
  let job = await call('create_product_video', {
    url: 'https://demo.playwright.dev/todomvc/#/',
    title: 'From an idea to a finished task',
    brief:
      'Demonstrate adding one task named Ship the product demo, then mark it complete. This is a localStorage-only test app. Show the actual interaction, focus on a simple way to keep track of work. Do not delete anything.',
    duration: 30,
    voice: 'cedar',
    music: 'momentum',
    theme: 'paper',
    demo: false,
  });
  let stage = '';
  for (let i = 0; i < 240; i++) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    job = await call('get_video', { video_id: job.id });
    if (job.status !== stage) {
      console.log(`${job.status}: ${job.payload.events.at(-1).message}`);
      stage = job.status;
    }
    if (['complete', 'failed', 'cancelled'].includes(job.status)) break;
  }
  assert.equal(job.status, 'complete', job.payload.events.at(-1).message);
  assert.equal(job.payload.demo, false);
  assert.ok(job.payload.scenes.length >= 3);
  const film = await call('export_video', { video_id: job.id });
  const response = await fetch(new URL(film.url, origin));
  assert.equal(response.status, 200);
  await mkdir('.cutroom/verification', { recursive: true });
  await writeFile(
    '.cutroom/verification/public-app-film.mp4',
    new Uint8Array(await response.arrayBuffer()),
  );
  await writeFile(
    '.cutroom/verification/public-app-result.json',
    JSON.stringify(
      { video_id: job.id, export: job.payload.export, scenes: job.payload.scenes },
      null,
      2,
    ),
  );
  assert.ok(film.poster_url);
  assert.equal((await fetch(new URL(film.poster_url, origin))).status, 200);
  console.log(
    'PASS: deployed public URL → MCP creation → autonomous browser actions → Cedar narration + momentum music + paper styling → private MP4 export.',
  );
} finally {
  await client.close();
}
