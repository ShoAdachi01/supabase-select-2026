import { chromium } from 'playwright';
import { createInterface } from 'node:readline';
import { createURLValidator } from './video_network.mjs';
import { resolve } from 'node:path';

// One process and fresh browser per job. stdin carries secrets; stdout carries observations.
const lines = createInterface({ input: process.stdin })[Symbol.asyncIterator]();
const receive = async () => {
  const next = await lines.next();
  if (next.done) throw new Error('Director disconnected.');
  return JSON.parse(next.value);
};
const send = (value) => process.stdout.write(JSON.stringify(value) + '\n');

let browser;
let transientCredentials;
try {
  const input = await receive();
  transientCredentials = input.credentials;
  const allowedLocalOrigin = input.demo ? new URL(input.url).origin : null;
  const { validate, hostCache } = createURLValidator(allowedLocalOrigin);
  await validate(input.url);
  if (input.credentials?.login_url) await validate(input.credentials.login_url);
  browser = await chromium.launch({
    headless: true,
    args: [
      '--disable-dev-shm-usage',
      ...(hostCache.size
        ? [
            '--host-resolver-rules=' +
              [...hostCache].map(([host, address]) => `MAP ${host} ${address}`).join(','),
          ]
        : []),
    ],
  });
  async function protect(context) {
    await context.route('**/*', async (route) => {
      try {
        const url = route.request().url();
        if (!url.startsWith('data:') && !url.startsWith('blob:')) await validate(url);
        await route.continue();
      } catch {
        await route.abort('blockedbyclient');
      }
    });
    context.on('page', (p) => {
      if (context.pages().length > 1) p.close().catch(() => {});
    });
  }
  const loginContext = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    acceptDownloads: false,
    serviceWorkers: 'block',
  });
  await protect(loginContext);
  const login = await loginContext.newPage();
  login.setDefaultTimeout(12000);
  await login.goto(input.credentials?.login_url || input.url, {
    waitUntil: 'domcontentloaded',
    timeout: 30000,
  });
  await login.waitForTimeout(1100);
  const password = login.locator('input[type="password"]:visible');
  if (await password.count()) {
    if (!input.credentials?.username || !input.credentials?.password)
      throw new Error('This app needs demo login credentials.');
    const credentialOrigins = new Set([
      new URL(input.url).origin,
      new URL(input.credentials.login_url || input.url).origin,
    ]);
    if (!credentialOrigins.has(new URL(login.url()).origin))
      throw new Error('The login redirected to another domain. Supply its login URL explicitly.');
    const username = login
      .locator(
        'input[type="email"]:visible, input[autocomplete="username"]:visible, input[name*="email" i]:visible, input[name*="user" i]:visible, input[type="text"]:visible',
      )
      .first();
    await username.fill(input.credentials.username);
    await password.first().fill(input.credentials.password);
    const button = login
      .getByRole('button', { name: /^(sign in|log in|login|continue|sign in to.*)$/i })
      .first();
    if (await button.count()) await button.click();
    else await password.first().press('Enter');
    await login.waitForTimeout(1800);
    if (await login.locator('input[type="password"]:visible').count())
      throw new Error(
        'Login did not complete. Check the credentials; MFA and CAPTCHA need an interactive login.',
      );
  }
  const state = await loginContext.storageState();
  const context = await browser.newContext({
    storageState: state,
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: input.directory, size: { width: 1280, height: 720 } },
    acceptDownloads: false,
    serviceWorkers: 'block',
  });
  await protect(context);
  await context.addInitScript(() => {
    const attach = () => {
      if (!document.body) return;
      const style = document.createElement('style');
      style.textContent =
        '*{cursor:none!important}html{scroll-behavior:smooth!important}[data-cutroom-cursor]{position:fixed;left:0;top:0;width:22px;height:28px;z-index:2147483647;pointer-events:none;filter:drop-shadow(0 2px 3px #0005);transition:transform 650ms cubic-bezier(.22,1,.36,1)}';
      document.head.append(style);
      const cursor = document.createElement('div');
      cursor.dataset.cutroomCursor = 'true';
      cursor.innerHTML =
        '<svg viewBox="0 0 22 28"><path d="M2 2v22l5-6 5 8 4-2-5-8h8z" fill="white" stroke="#172020" stroke-width="1.6"/></svg>';
      cursor.style.transform = 'translate(1000px, 620px)';
      document.body.append(cursor);
    };
    document.addEventListener('DOMContentLoaded', attach);
  });
  const page = await context.newPage();
  const started = Date.now();
  page.setDefaultTimeout(10000);
  await page.goto(input.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(1500);
  await loginContext.close();
  const scenes = [];
  const elapsed = () => (Date.now() - started) / 1000;
  async function observe() {
    if (await page.locator('input[type="password"]:visible').count())
      throw new Error(
        'The recording session needs login again. This app may use sessionStorage; use a demo account with a persistent session.',
      );
    const elements = await page.evaluate(() =>
      [...document.querySelectorAll('button,a,input,textarea,select,[role="button"],[role="tab"]')]
        .filter((el) => {
          const r = el.getBoundingClientRect();
          return (
            r.width > 0 &&
            r.height > 0 &&
            r.top < innerHeight &&
            r.bottom > 0 &&
            el.getAttribute('type') !== 'password'
          );
        })
        .slice(0, 100)
        .map((el, id) => {
          el.setAttribute('data-cutroom-id', String(id));
          return {
            id,
            tag: el.tagName.toLowerCase(),
            label: (
              el.getAttribute('aria-label') ||
              el.innerText ||
              el.getAttribute('placeholder') ||
              el.getAttribute('name') ||
              ''
            )
              .trim()
              .slice(0, 150),
            type: el.getAttribute('type'),
          };
        }),
    );
    const text = (await page.locator('body').innerText()).slice(0, 9000);
    const screenshot = (await page.screenshot({ type: 'jpeg', quality: 65 })).toString('base64');
    return {
      type: 'observation',
      url: page.url(),
      text,
      elements,
      screenshot,
      scenes: scenes.length,
    };
  }
  async function snapshot(scene) {
    scene.thumbnail = `scene-${scenes.length}.jpg`;
    await page.screenshot({
      path: resolve(input.directory, scene.thumbnail),
      type: 'jpeg',
      quality: 85,
    });
    scenes.push(scene);
  }
  const overviewStart = elapsed();
  await page.waitForTimeout(2200);
  await snapshot({
    start: overviewStart,
    end: elapsed(),
    label: 'The big picture',
    focus: { x: 640, y: 360 },
    action: 'overview',
  });
  send(await observe());
  for (let count = 0; count < 10; count++) {
    const action = await receive();
    if (action.type === 'done') break;
    const scene = {
      start: elapsed(),
      label: String(action.label || 'Feature detail').slice(0, 100),
      focus: { x: 640, y: 360 },
      action: action.type,
    };
    try {
      if (['click', 'fill', 'select'].includes(action.type)) {
        if (!Number.isInteger(action.id)) throw new Error('Choose a visible element ID.');
        const el = page.locator(`[data-cutroom-id="${action.id}"]`).first();
        const label = await el.innerText().catch(() => '');
        const inputType = await el.getAttribute('type');
        if (inputType === 'password')
          throw new Error('Password entry is not part of a filmed feature.');
        if (
          /\b(delete|remove account|purchase|buy now|pay now|send|invite|sign out|log out)\b/i.test(
            label,
          )
        )
          throw new Error('That action is outside the demo recording scope.');
        await el.scrollIntoViewIfNeeded();
        const box = await el.boundingBox();
        if (box) {
          scene.focus = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
          await page.evaluate(({ x, y }) => {
            const c = document.querySelector('[data-cutroom-cursor]');
            if (c) c.style.transform = `translate(${x}px,${y}px)`;
          }, scene.focus);
          await page.waitForTimeout(750);
        }
        if (action.type === 'click') await el.click();
        else if (action.type === 'select')
          await el.selectOption(String(action.value || '').slice(0, 500));
        else {
          await el.fill('');
          await el.pressSequentially(String(action.value || '').slice(0, 500), { delay: 35 });
        }
      } else if (action.type === 'scroll') {
        await page.evaluate(
          (amount) => window.scrollBy({ top: amount, behavior: 'smooth' }),
          Math.max(-600, Math.min(600, Number(action.amount) || 400)),
        );
      } else if (action.type === 'press' && ['Enter', 'Escape', 'Tab'].includes(action.key)) {
        await page.keyboard.press(action.key);
      } else if (action.type !== 'hold') throw new Error('Unsupported browser action.');
      await page.waitForTimeout(1800);
      scene.end = elapsed();
      await snapshot(scene);
      send(await observe());
    } catch (error) {
      send({ ...(await observe()), action_error: String(error.message).slice(0, 300) });
    }
  }
  await context.close();
  send({ type: 'complete', scenes, video: await page.video().path() });
} catch (error) {
  let message = String(error.message);
  // Playwright call logs can echo the value passed to fill() on a failed login.
  for (const secret of [transientCredentials?.password, transientCredentials?.username])
    if (secret) message = message.split(secret).join('[redacted]');
  send({ type: 'error', message: message.slice(0, 400) });
  process.exitCode = 1;
} finally {
  await browser?.close();
  process.stdin.destroy();
}
