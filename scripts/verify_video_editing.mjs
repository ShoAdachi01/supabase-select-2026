// Uses the Supabase workspace/capture saved by test:video:e2e.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const origin = process.env.CUTROOM_URL || 'http://127.0.0.1:5173';
const folder = '.cutroom/verification';
const result = JSON.parse(await readFile(`${folder}/result.json`, 'utf8'));
const browser = await chromium.launch();
const context = await browser.newContext({
  storageState: `${folder}/browser-session.json`,
  viewport: { width: 1440, height: 1050 },
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
try {
  await page.goto(origin);
  await page.getByText('Workspace connected', { exact: true }).waitFor();
  const token = await page.evaluate(() => {
    const key = Object.keys(localStorage).find(
      (k) => k.startsWith('sb-') && k.endsWith('-auth-token'),
    );
    return JSON.parse(localStorage.getItem(key)).access_token;
  });
  const headers = { Authorization: `Bearer ${token}` };
  const before = await (await fetch(`${origin}/api/videos/${result.video_id}`, { headers })).json();
  assert.equal(before.status, 'complete');
  await page
    .getByRole('button', { name: new RegExp(before.title) })
    .first()
    .click();
  await page.getByRole('button', { name: 'Script', exact: true }).click();
  await page.getByRole('button', { name: 'Add launch sequence', exact: true }).click();
  await page.getByLabel('Animation headline').waitFor({ timeout: 120000 });
  await page.getByLabel('Animation headline').fill('Launch with clarity.');
  await page
    .getByLabel('Selected scene narration')
    .fill('Meet Meridian. One clear place for projects, boards, and team progress.');
  await page.getByRole('button', { name: 'Move scene later', exact: true }).click();
  await page.getByRole('button', { name: 'Move scene earlier', exact: true }).click();
  const list = page.getByLabel('Editable scenes');
  await list.getByRole('button').nth(1).click();
  if (await page.getByRole('button', { name: 'Restore scene', exact: true }).count())
    await page.getByRole('button', { name: 'Restore scene', exact: true }).click();
  await page.getByRole('button', { name: 'Cut scene', exact: true }).click();
  await list.getByRole('button').nth(2).click();
  await page.getByLabel('Trim start').fill('0.2');
  await list.getByRole('button').first().click();
  await page.screenshot({ path: `${folder}/studio-timeline.png`, fullPage: true });
  await page.getByRole('button', { name: 'Render changes', exact: true }).click();
  let job;
  for (let i = 0; i < 180; i++) {
    await page.waitForTimeout(2000);
    job = await (await fetch(`${origin}/api/videos/${result.video_id}`, { headers })).json();
    if (['complete', 'failed', 'cancelled'].includes(job.status)) break;
  }
  assert.equal(job.status, 'complete', job.payload.events.at(-1).message);
  assert.equal(job.payload.revision, before.payload.revision + 1);
  assert.equal(job.payload.timeline[0].headline, 'Launch with clarity.');
  assert.equal(job.payload.timeline[1].enabled, false);
  assert.equal(job.payload.timeline[2].trim_start, 0.2);
  assert.deepEqual(job.payload.scenes, before.payload.scenes, 'Capture remains immutable.');
  assert.equal(
    job.payload.rendered_scenes.length,
    job.payload.timeline.filter((c) => c.enabled).length,
  );
  assert.equal(job.payload.rendered_scenes[0].kind, 'title');
  assert.ok(job.payload.rendered_scenes[1].timeline_start > 0);
  const playback = await (
    await fetch(`${origin}/api/videos/${job.id}/playback`, { headers })
  ).json();
  const film = await fetch(new URL(playback.url, origin));
  assert.equal(film.status, 200);
  await writeFile(`${folder}/launch-film.mp4`, new Uint8Array(await film.arrayBuffer()));
  await writeFile(
    `${folder}/launch-result.json`,
    JSON.stringify(
      {
        video_id: job.id,
        export: job.payload.export,
        timeline: job.payload.timeline,
        scenes: job.payload.rendered_scenes,
      },
      null,
      2,
    ),
  );
  await page.locator('.film-player video').waitFor();
  await page.locator('.film-player video').evaluate(
    (video) =>
      new Promise((resolve) => {
        video.addEventListener('seeked', resolve, { once: true });
        if (video.readyState >= 2) video.currentTime = 1.8;
        else
          video.onloadeddata = () => {
            video.currentTime = 1.8;
          };
      }),
  );
  await page.getByRole('button', { name: 'Script', exact: true }).click();
  await page.screenshot({ path: `${folder}/studio-launch.png`, fullPage: true });
  await page.getByRole('button', { name: 'Animation', exact: true }).click();
  await page.getByRole('button', { name: 'Generate animation', exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.deepEqual(errors, []);
  console.log(
    'PASS: UI launch planning, edited exact words, cut/reorder/trim controls, immutable footage, animated opening, smooth transitions, private narrated MP4 and mobile layout.',
  );
} finally {
  await browser.close();
}
