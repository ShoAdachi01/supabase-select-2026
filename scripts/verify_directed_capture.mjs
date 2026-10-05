// Live browser verification: real keystrokes and clicks, with director idle time excluded.
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { createDirectedCapture } from './video_capture.mjs';

const directory = '.cutroom/verification/interaction-clock';
await mkdir(directory, { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.setContent(
    '<body style="background:#eddddd"><input aria-label="Name"><button onclick="document.body.style.background=\'#ddeddd\'">Save</button></body>',
  );
  const recorder = await createDirectedCapture(page, directory);
  const scenes = [];
  const first = { kind: 'browser', start: await recorder.begin(), interactions: [] };
  for (const character of 'Cutroom') {
    first.interactions.push({ kind: 'key', time: recorder.time(), x: 100 });
    await page.getByLabel('Name').pressSequentially(character, { delay: 60 });
  }
  await page.waitForTimeout(300);
  first.end = await recorder.end();
  scenes.push(first);
  await page.waitForTimeout(1500);
  const second = { kind: 'browser', start: await recorder.begin(), interactions: [] };
  assert.equal(second.start, first.end);
  await page.waitForTimeout(300);
  second.interactions.push({ kind: 'click', time: recorder.time(), x: 200 });
  await page.getByRole('button', { name: 'Save' }).click();
  await page.waitForTimeout(400);
  second.end = await recorder.end();
  scenes.push(second);
  await recorder.finish();
  assert.ok(second.end < 3, 'Agent idle time is omitted from the recording clock.');
  assert.equal(await page.getByLabel('Name').inputValue(), 'Cutroom');
  await writeFile(`${directory}/scenes.json`, JSON.stringify(scenes, null, 2));
  console.log('PASS: directed capture includes 7 real keys and 1 click and excludes idle time.');
} finally {
  await browser.close();
}
