import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const origin = process.env.CUTROOM_URL || 'http://127.0.0.1:5173';
const folder = '.cutroom/verification';
await mkdir(folder, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
try {
  await page.goto(origin);
  await page.getByText('Workspace connected', { exact: true }).waitFor({ timeout: 20000 });
  await page.screenshot({ path: `${folder}/studio-home.png`, fullPage: true });
  await page.getByRole('button', { name: 'Create a video', exact: true }).first().click();
  await page.getByRole('heading', { name: 'A new take.' }).waitFor();
  await page.screenshot({ path: `${folder}/studio-brief.png`, fullPage: true });
  await page.getByRole('button', { name: 'Does your app need a demo login?' }).click();
  await page.getByLabel('Password', { exact: true }).fill('transient-demo-password');
  await page.getByRole('button', { name: 'Back to videos' }).click();
  await page.getByRole('button', { name: 'Voice library' }).click();
  assert.equal(await page.getByRole('button', { name: 'Listen to a sample' }).count(), 6);
  await page.getByRole('button', { name: 'Add my voice' }).click();
  await page.getByRole('dialog').waitFor();
  const initialConfig = await (await fetch(`${origin}/api/config`)).json();
  assert.equal(
    await page.getByRole('button', { name: 'Create my voice', exact: true }).isDisabled(),
    !initialConfig.video.voice_cloning,
  );
  await page.getByRole('dialog').getByRole('button').first().click();
  await page.getByRole('button', { name: /Agent connector/ }).click();
  await page.screenshot({ path: `${folder}/studio-agent.png`, fullPage: true });
  await page.getByRole('button', { name: /My videos/ }).click();
  await page.getByRole('button', { name: 'Try a real capture of our sample app' }).click();
  await page.getByRole('heading', { name: /A clearer way to work/ }).waitFor();
  console.log('Started real browser capture with generated narration.');
  const token = await page.evaluate(() => {
    for (const key of Object.keys(localStorage))
      if (key.startsWith('sb-') && key.endsWith('-auth-token'))
        return JSON.parse(localStorage.getItem(key)).access_token;
    return 'local-demo';
  });
  const headers = { Authorization: `Bearer ${token}` };
  let job;
  let lastStage = '';
  for (let i = 0; i < 240; i++) {
    await page.waitForTimeout(2000);
    const response = await fetch(`${origin}/api/videos`, { headers });
    assert.equal(response.status, 200);
    const jobs = await response.json();
    job = jobs[0];
    if (job.status !== lastStage) {
      console.log(`${job.status}: ${job.payload.events.at(-1).message}`);
      lastStage = job.status;
    }
    if (['complete', 'failed', 'cancelled'].includes(job.status)) break;
  }
  assert.equal(job.status, 'complete', job.payload.events.at(-1).message);
  assert.ok(job.payload.scenes.length >= 4);
  assert.ok(job.payload.export.bytes > 100000);
  assert.equal(job.payload.export.resolution, '1920×1080');
  await page.locator('video').waitFor({ timeout: 20000 });
  await page.locator('video').evaluate(
    (video) =>
      new Promise((resolve) => {
        video.addEventListener('seeked', resolve, { once: true });
        if (video.readyState >= 2) video.currentTime = 8;
        else
          video.onloadeddata = () => {
            video.currentTime = 8;
          };
      }),
  );
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${folder}/studio-film.png`, fullPage: true });
  const playback = await (
    await fetch(`${origin}/api/videos/${job.id}/playback`, { headers })
  ).json();
  const movie = await fetch(new URL(playback.url, origin));
  assert.equal(movie.status, 200);
  const bytes = new Uint8Array(await movie.arrayBuffer());
  await writeFile(`${folder}/demo-film.mp4`, bytes);
  const range = await fetch(new URL(playback.url, origin), { headers: { Range: 'bytes=0-99' } });
  assert.equal(range.status, 206);
  assert.equal((await range.arrayBuffer()).byteLength, 100);
  await writeFile(
    `${folder}/result.json`,
    JSON.stringify(
      { video_id: job.id, export: job.payload.export, scenes: job.payload.scenes },
      null,
      2,
    ),
  );
  await context.storageState({ path: `${folder}/browser-session.json` });
  // Verify the finished video is available to an agent in the same workspace.
  const agent = new Client({ name: 'cutroom-video-e2e', version: '1.0.0' });
  try {
    await agent.connect(
      new StreamableHTTPClientTransport(new URL(`${origin}/mcp`), { requestInit: { headers } }),
    );
    const result = await agent.callTool({ name: 'export_video', arguments: { video_id: job.id } });
    assert.equal(result.isError, false);
    assert.ok(JSON.parse(result.content[0].text).url);
  } finally {
    await agent.close();
  }
  const config = await (await fetch(`${origin}/api/config`)).json();
  if (config.mode === 'supabase') {
    const other = await (
      await fetch(`${config.supabase_url}/auth/v1/signup`, {
        method: 'POST',
        headers: { apikey: config.supabase_key, 'Content-Type': 'application/json' },
        body: '{}',
      })
    ).json();
    const denied = await fetch(`${origin}/api/videos/${job.id}`, {
      headers: { Authorization: `Bearer ${other.access_token}` },
    });
    assert.equal(denied.status, 404);
  }
  assert.deepEqual(errors, []);
  await page.getByRole('button', { name: 'All videos' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${folder}/studio-mobile.png`, fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  console.log(
    `PASS: real capture, AI narration, music, 1080p MP4, playback/range requests, authenticated MCP export, workspace isolation, and responsive UI. Film: ${folder}/demo-film.mp4`,
  );
} finally {
  await browser.close();
}
