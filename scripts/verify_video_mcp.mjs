import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const origin = process.env.CUTROOM_URL || 'http://127.0.0.1:8000';
const config = await (await fetch(`${origin}/api/config`)).json();
async function session() {
  if (config.mode === 'local-demo') return 'local-demo';
  const response = await fetch(`${config.supabase_url}/auth/v1/signup`, {
    method: 'POST',
    headers: { apikey: config.supabase_key, 'Content-Type': 'application/json' },
    body: '{}',
  });
  assert.equal(response.status, 200);
  return (await response.json()).access_token;
}
const token = await session();
const client = new Client({ name: 'cutroom-integration-test', version: '1.0.0' });
const transport = new StreamableHTTPClientTransport(new URL(`${origin}/mcp`), {
  requestInit: { headers: { Authorization: `Bearer ${token}` } },
});
try {
  await client.connect(transport);
  const { tools } = await client.listTools();
  assert.equal(tools.length, 9);
  for (const name of [
    'create_product_video',
    'get_video',
    'list_videos',
    'list_voices',
    'render_video',
    'export_video',
    'cancel_video',
    'plan_launch_video',
    'generate_animation',
  ])
    assert.ok(tools.some((t) => t.name === name));
  const voices = await client.callTool({ name: 'list_voices', arguments: {} });
  assert.equal(voices.isError, false);
  assert.ok(JSON.parse(voices.content[0].text).some((v) => v.id === 'marin'));
  const invalid = await client.callTool({ name: 'get_video', arguments: { video_id: 'invalid' } });
  assert.equal(invalid.isError, true);
  const forbidden = await client.callTool({
    name: 'create_product_video',
    arguments: { url: 'http://169.254.169.254/', brief: 'Show the cloud instance metadata.' },
  });
  assert.equal(forbidden.isError, true);
  const rows = await client.callTool({ name: 'list_videos', arguments: {} });
  assert.equal(rows.isError, false);
  assert.deepEqual(JSON.parse(rows.content[0].text), []);
  console.log(
    'PASS: official MCP handshake, nine tools, voice selection, workspace listing, invalid input, and private-network rejection.',
  );
} finally {
  await client.close();
}
