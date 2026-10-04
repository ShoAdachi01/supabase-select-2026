// Film our real local studio with a private, existing verification workspace.
import { chromium } from 'playwright';
import { mkdir, writeFile, copyFile } from 'node:fs/promises';
const folder = '.cutroom/verification/cutroom-launch';
await mkdir(folder, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  storageState: '.cutroom/verification/browser-session.json',
  viewport: { width: 1440, height: 810 },
  recordVideo: { dir: folder, size: { width: 1440, height: 810 } },
});
const page = await context.newPage();
const start = Date.now();
const elapsed = () => (Date.now() - start) / 1000;
const scenes = [];
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
async function shot(label, narration, action, seconds = 3.2) {
  await page.waitForTimeout(250);
  const from = elapsed();
  if (action) await action();
  await page.waitForTimeout(seconds * 1000);
  const thumbnail = `scene-${scenes.length}.jpg`;
  await page.screenshot({ path: `${folder}/${thumbnail}` });
  scenes.push({
    start: from,
    end: elapsed(),
    label,
    narration,
    thumbnail,
    focus: { x: 640, y: 360 },
    kind: 'browser',
    duration: seconds,
    transition: 'cut',
    camera: 'wide',
  });
}
try {
  await page.goto('http://127.0.0.1:5173');
  await page.getByText('Workspace connected', { exact: true }).waitFor();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: '.cutroom/verification/studio-clean.png', fullPage: true });
  await shot('A launch starts here', 'You built something great. Let people see it.', null, 3.2);
  await shot(
    'Give it a link',
    'Start with your product link.',
    async () => {
      await page
        .getByLabel('Product link')
        .pressSequentially('https://your-product.com', { delay: 30 });
    },
    2.4,
  );
  await page.getByRole('button', { name: 'Start your video' }).click();
  await page.getByLabel('Deployed app link').waitFor();
  await shot(
    'Direct the story',
    'Tell your agent what makes it special.',
    async () => {
      await page.getByPlaceholder('Meet your next favorite feature').fill('Your next launch');
      const fields = page.locator('textarea');
      await fields
        .first()
        .fill(
          'Show the project board. Focus on how quickly a team can see what needs to happen next.',
        );
    },
    3.2,
  );
  await page.getByRole('button', { name: 'Voice library', exact: true }).click();
  await shot('Give it a voice', 'Find your voice. Add a little energy.', null, 3.2);
  await page
    .getByRole('button', { name: /My videos/ })
    .first()
    .click();
  await page
    .getByRole('button', { name: /Meridian — launch/ })
    .first()
    .click();
  await page.getByRole('button', { name: 'Script', exact: true }).click();
  await page.locator('.film-player video').waitFor();
  await page.locator('.film-player video').evaluate(async (v) => {
    v.muted = true;
    v.currentTime = 2.5;
    await v.play();
  });
  await shot('The finished edit', 'Real product footage. A story that moves.', null, 3.2);
  await page.locator('.film-player video').evaluate((v) => v.pause());
  const clips = page.getByLabel('Editable scenes').getByRole('button');
  await clips.nth(2).click();
  await shot(
    'Make it yours',
    'Every word. Every cut. Still yours.',
    async () => {
      await page
        .getByLabel('Selected scene narration')
        .fill('Everything your team needs. One clear view.');
    },
    3.2,
  );
  await page
    .getByRole('button', { name: /Agent connector/ })
    .first()
    .click();
  await shot('Built for your agent', 'Create and export, right from your agent.', null, 3.2);
  await page.screenshot({ path: '.cutroom/verification/studio-clean-agent.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw new Error('Mobile layout overflows.');
  if (errors.length) throw new Error(errors.join('\n'));
  await context.close();
  await copyFile(await page.video().path(), `${folder}/raw.webm`);
  await writeFile(`${folder}/scenes.json`, JSON.stringify(scenes, null, 2));
  console.log(`Captured ${scenes.length} real Cutroom shots; desktop/mobile checks passed.`);
} finally {
  await browser.close();
}
