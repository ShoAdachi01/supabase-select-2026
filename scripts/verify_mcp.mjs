import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const origin = process.env.FORGE_URL || 'http://127.0.0.1:8000';
const config = await (await fetch(`${origin}/api/config`)).json();
assert.equal(config.mode, 'supabase', 'Run against a real Supabase stack.');
const auth = await fetch(`${config.supabase_url}/auth/v1/signup`, {
  method: 'POST',
  headers: { apikey: config.supabase_key, 'Content-Type': 'application/json' },
  body: '{}',
});
assert.equal(auth.status, 200, 'Anonymous Supabase sign-in must be enabled.');
const session = await auth.json();
const headers = {
  Authorization: `Bearer ${session.access_token}`,
  'Content-Type': 'application/json',
};
async function request(path, body) {
  const response = await fetch(`${origin}${path}`, {
    method: body ? 'POST' : 'GET',
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  assert.equal(response.ok, true, `Request failed: ${path} (${response.status})`);
  return response.json();
}

const dataset = await request('/api/datasets/sample', { kind: 'wine' });
let run = await request('/api/runs', {
  dataset_id: dataset.id,
  target: 'cultivar',
  features: dataset.profile.columns
    .filter((c) => !c.excluded && c.name !== 'cultivar')
    .map((c) => c.name),
  task: 'classification',
  name: 'MCP cultivar prediction',
});
for (let i = 0; i < 90 && ['queued', 'training'].includes(run.status); i++) {
  await new Promise((resolve) => setTimeout(resolve, 500));
  run = await request(`/api/runs/${run.id}`);
}
assert.equal(run.status, 'ready', run.payload.error || 'Training timed out.');

const client = new Client({ name: 'forge-integration-test', version: '1.0.0' });
const transport = new StreamableHTTPClientTransport(new URL(`${origin}/mcp`), {
  requestInit: { headers: { Authorization: headers.Authorization } },
});
try {
  await client.connect(transport);
  const { tools } = await client.listTools();
  assert.equal(tools.length, 1);
  const result = await client.callTool({
    name: tools[0].name,
    arguments: { records: [run.payload.result.example_input] },
  });
  assert.equal(result.isError, false);
  const prediction = JSON.parse(result.content[0].text);
  assert.equal(prediction.tokens_used_for_prediction, 0);
  assert.equal(prediction.predictions.length, 1);
  const invalid = await client.callTool({ name: tools[0].name, arguments: { records: [123] } });
  assert.equal(invalid.isError, true, 'Invalid arguments must return a tool error.');
  console.log(
    'PASS: official MCP client handshake, tool discovery, real prediction, and invalid-input handling.',
  );
} finally {
  await client.close();
}
