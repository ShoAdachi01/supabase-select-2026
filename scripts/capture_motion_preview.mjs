// Directed, real Cutroom footage for comparing motion treatments on identical source material.
import { chromium } from 'playwright';
import { mkdir, writeFile, copyFile } from 'node:fs/promises';
const folder = '.cutroom/verification/motion-v2/source';
await mkdir(folder, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  storageState: '.cutroom/verification/browser-session.json',
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 2,
  recordVideo: { dir: folder, size: { width: 1920, height: 1080 } },
});
const page = await context.newPage();
const start = Date.now();
const elapsed = () => (Date.now() - start) / 1000;
try {
  await page.goto('http://127.0.0.1:5173');
  await page.getByText('Workspace connected', { exact: true }).waitFor();
  await page
    .getByRole('button', { name: /Meridian — launch/ })
    .first()
    .click();
  await page.getByRole('button', { name: 'Script', exact: true }).click();
  await page.getByLabel('Editable scenes').getByRole('button').nth(2).click();
  await page.locator('.film-player video').evaluate(async (video) => {
    video.controls = false;
    video.muted = true;
    await new Promise((done) => {
      video.addEventListener('seeked', done, { once: true });
      video.currentTime = 7;
    });
  });
  const narration = page.getByLabel('Selected scene narration');
  await narration.scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(20, 1000);
  await page.waitForTimeout(300);
  const box = await narration.boundingBox();
  const from = elapsed();
  await page.waitForTimeout(500);
  await narration.fill('Every word. Every cut. Still yours.');
  await page.waitForTimeout(2200);
  const to = elapsed();
  const details = [];
  for (const [i, selector] of [
    '.film-player',
    '.clip-controls label:has(textarea)',
    '.scene-strip',
  ].entries()) {
    const name = `detail-0-${i}.png`;
    await page.locator(selector).screenshot({ path: `${folder}/${name}` });
    details.push(name);
  }
  await page.screenshot({ path: `${folder}/scene-0.jpg` });
  await writeFile(
    `${folder}/scenes.json`,
    JSON.stringify(
      [
        {
          kind: 'browser',
          start: from,
          end: to,
          viewport: { width: 1920, height: 1080 },
          focus: { x: box.x + box.width / 2, y: box.y + box.height / 2 },
          label: 'Every word. Yours.',
          narration: 'Every word. Every cut. Still yours.',
          details,
          thumbnail: 'scene-0.jpg',
          duration: 3.2,
          motion: 'detail',
        },
      ],
      null,
      2,
    ),
  );
  await context.close();
  await copyFile(await page.video().path(), `${folder}/raw.webm`);
  console.log('Captured the real editor and three isolated product elements.');
} finally {
  await browser.close();
}
