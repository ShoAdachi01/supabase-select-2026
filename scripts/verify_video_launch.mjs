// Live integration: the entire launch film is requested and exported through MCP.
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const origin = process.env.CUTROOM_URL || 'http://127.0.0.1:5173';
const folder = '.cutroom/verification';
const musicLed = process.env.CUTROOM_MUSIC_LED === '1';
const artifact = musicLed ? 'music-led' : 'polished';
await mkdir(folder, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  storageState: `${folder}/browser-session.json`,
  viewport: { width: 1440, height: 1050 },
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const agent = new Client({ name: 'cutroom-launch-check', version: '1.0.0' });
try {
  await page.goto(origin);
  await page.getByText('Workspace connected', { exact: true }).waitFor();
  const token = await page.evaluate(() => {
    const key = Object.keys(localStorage).find(
      (k) => k.startsWith('sb-') && k.endsWith('-auth-token'),
    );
    return key ? JSON.parse(localStorage.getItem(key)).access_token : 'local-demo';
  });
  await agent.connect(
    new StreamableHTTPClientTransport(new URL(`${origin}/mcp`), {
      requestInit: { headers: { Authorization: `Bearer ${token}` } },
    }),
  );
  async function call(name, args) {
    const result = await agent.callTool({ name, arguments: args });
    assert.equal(result.isError, false, result.content?.[0]?.text);
    return JSON.parse(result.content[0].text);
  }
  let job;
  if (process.env.CUTROOM_REVISE) {
    const previous = JSON.parse(await readFile(`${folder}/${artifact}-result.json`, 'utf8'));
    const plan = process.env.CUTROOM_REUSE_PLAN
      ? { clips: (await call('get_video', { video_id: previous.video_id })).payload.timeline }
      : await call('plan_launch_video', { video_id: previous.video_id });
    job = await call('render_video', {
      video_id: previous.video_id,
      clips: plan.clips,
      voice: musicLed ? 'none' : 'cedar',
      music: 'momentum',
      theme: 'midnight',
    });
  } else
    job = await call('create_product_video', {
      url: 'https://example.com',
      demo: true,
      title: musicLed ? 'Meridian — music-led launch' : 'Meridian — launch',
      brief:
        'Show projects, open Website refresh, switch to the board, then show analytics. A punchy launch film about clarity and team progress. Keep four feature shots and avoid repeated navigation.',
      voice: musicLed ? 'none' : 'cedar',
      music: 'momentum',
      theme: 'midnight',
    });
  const id = job.id;
  let stage = '';
  for (let i = 0; i < 240; i++) {
    await page.waitForTimeout(2000);
    job = await call('get_video', { video_id: id });
    if (job.status !== stage) {
      stage = job.status;
      console.log(`${stage}: ${job.payload.events.at(-1).message}`);
    }
    if (['complete', 'failed', 'cancelled'].includes(stage)) break;
  }
  assert.equal(job.status, 'complete', job.payload.events.at(-1).message);
  assert.equal(job.payload.duration, 30);
  assert.ok(
    job.payload.export.duration_seconds <= 32,
    'Launch film stays within its short edit budget.',
  );
  assert.ok(
    job.payload.scenes.some((s) => (musicLed ? s.interactions?.length > 0 : s.shot === 'result')),
    'Navigation is removed from at least one shot.',
  );
  for (const scene of job.payload.scenes.filter((s) => s.shot === 'result')) {
    assert.ok(scene.alignment_error <= 2.5, 'Result footage matches its verified screen.');
    assert.ok(scene.end - scene.start >= 0.25, 'Matched footage has a usable duration.');
  }
  assert.ok(
    job.payload.timeline.some((c) => !c.enabled),
    'Overview is cut but restorable.',
  );
  assert.ok(job.payload.rendered_scenes.every((s) => s.duration <= 8));
  if (musicLed) {
    assert.equal(job.payload.narration_source, 'Music and interaction sounds');
    assert.ok(job.payload.rendered_scenes.every((s) => !s.narration));
  }
  const exported = await call('export_video', { video_id: id });
  const film = await fetch(new URL(exported.url, origin));
  assert.equal(film.status, 200);
  await writeFile(`${folder}/${artifact}-film.mp4`, new Uint8Array(await film.arrayBuffer()));
  await writeFile(
    `${folder}/${artifact}-result.json`,
    JSON.stringify(
      {
        video_id: id,
        export: job.payload.export,
        timeline: job.payload.timeline,
        scenes: job.payload.rendered_scenes,
      },
      null,
      2,
    ),
  );
  await page.reload();
  await page
    .getByRole('button', { name: musicLed ? /Meridian — music-led launch/ : /Meridian — launch/ })
    .first()
    .click();
  await page.getByRole('button', { name: 'Script', exact: true }).click();
  await page.getByLabel('Shot duration').waitFor();
  const footage = job.payload.rendered_scenes.find((s) => s.kind === 'browser');
  await page.locator('.film-player video').evaluate(
    (video, time) =>
      new Promise((resolve) => {
        video.addEventListener('seeked', resolve, { once: true });
        if (video.readyState >= 2) video.currentTime = time;
        else
          video.onloadeddata = () => {
            video.currentTime = time;
          };
      }),
    footage.timeline_start + 0.5,
  );
  await page.locator('.film-player video').evaluate((video) => {
    video.pause();
    video.controls = false;
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${folder}/studio-polished.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.deepEqual(errors, []);
  await context.storageState({ path: `${folder}/browser-session.json` });
  console.log(
    `PASS: MCP create → real capture → motion reveals → narration/music → private export; ${job.payload.export.duration_seconds}s. ${folder}/${artifact}-film.mp4`,
  );
} finally {
  await agent.close();
  await browser.close();
}
