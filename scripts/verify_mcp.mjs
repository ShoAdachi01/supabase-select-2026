import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const origin = process.env.TRACE_URL || 'http://127.0.0.1:8000';
const config = await (await fetch(`${origin}/api/config`)).json();
assert.equal(config.mode, 'supabase', 'Run against a real Supabase stack.');
const auth = await fetch(`${config.supabase_url}/auth/v1/signup`, {
  method: 'POST',
  headers: { apikey: config.supabase_key, 'Content-Type': 'application/json' },
  body: '{}',
});
assert.equal(auth.status, 200);
const session = await auth.json();
const headers = {
  Authorization: `Bearer ${session.access_token}`,
  'Content-Type': 'application/json',
};
const response = await fetch(`${origin}/api/examples/demo`, {
  method: 'POST',
  headers,
  body: '{}',
});
assert.equal(response.ok, true);
const asset = await response.json();
const client = new Client({ name: 'trace-integration-test', version: '1.0.0' });
const transport = new StreamableHTTPClientTransport(new URL(`${origin}/mcp`), {
  requestInit: { headers: { Authorization: headers.Authorization } },
});
async function call(name, args = {}) {
  const result = await client.callTool({ name, arguments: args });
  assert.equal(result.isError, false, JSON.stringify(result));
  return JSON.parse(result.content[0].text);
}
try {
  await client.connect(transport);
  const { tools } = await client.listTools();
  assert.equal(tools.length, 7);
  assert.equal((await call('list_characters')).length, 1);
  let scan = await call('find_character_usage', { asset_id: asset.id, source: 'demo', limit: 12 });
  for (let i = 0; i < 60 && ['queued', 'searching'].includes(scan.status); i++) {
    await new Promise((resolve) => setTimeout(resolve, 300));
    scan = await call('get_scan', { scan_id: scan.id });
  }
  assert.equal(scan.status, 'complete');
  assert.equal(scan.payload.finding_count, 6);
  const findings = await call('list_usage_findings', { asset_id: asset.id });
  assert.equal(findings.length, 6);
  assert.equal(findings[0].payload.thumbnail, undefined);
  assert.ok(findings[0].payload.image_download_path);
  const image = await fetch(`${origin}${findings[0].payload.image_download_path}`, { headers });
  assert.equal(image.status, 200);
  assert.equal(image.headers.get('content-type'), 'image/png');
  const reviewed = await call('record_usage_review', {
    finding_id: findings[0].id,
    decision: 'investigate',
    note: 'Owner-directed review.',
  });
  assert.equal(reviewed.payload.review.decision, 'investigate');
  const evidence = await call('prepare_evidence', { finding_id: findings[0].id });
  const bundle = await fetch(`${origin}${evidence.download_path}`, { headers });
  assert.equal(bundle.status, 200);
  assert.equal(bundle.headers.get('content-type'), 'application/zip');
  assert.ok((await bundle.arrayBuffer()).byteLength > 1000);
  const invalid = await client.callTool({
    name: 'find_character_usage',
    arguments: { asset_id: 'invalid' },
  });
  assert.equal(invalid.isError, true);
  console.log(
    'PASS: official MCP client handshake, seven tools, discovery, owner review, evidence download, and invalid-input handling.',
  );
} finally {
  await client.close();
}
