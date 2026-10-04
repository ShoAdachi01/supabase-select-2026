import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, stat } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createServer } from 'node:http';

const origin = process.env.CUTROOM_URL || 'http://127.0.0.1:8000';
const directory = resolve('.cutroom/verification/login');
await mkdir(directory, { recursive: true });
async function capture(input) {
  return new Promise((resolveResult, reject) => {
    const worker = spawn('node', ['scripts/video_browser.mjs'], {
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const messages = [];
    let buffered = '';
    const timeout = setTimeout(() => {
      worker.kill();
      reject(new Error('Login capture timed out.'));
    }, 60000);
    worker.stdout.on('data', (data) => {
      buffered += data.toString();
      for (;;) {
        const index = buffered.indexOf('\n');
        if (index < 0) break;
        const value = JSON.parse(buffered.slice(0, index));
        buffered = buffered.slice(index + 1);
        messages.push(value);
        if (value.type === 'observation')
          worker.stdin.write(JSON.stringify({ type: 'done' }) + '\n');
      }
    });
    worker.on('error', reject);
    worker.on('close', () => {
      clearTimeout(timeout);
      resolveResult(messages);
    });
    worker.stdin.write(JSON.stringify(input) + '\n');
  });
}
const success = await capture({
  url: `${origin}/sample/`,
  directory,
  demo: true,
  credentials: {
    username: 'demo@meridian.app',
    password: 'demo',
    login_url: `${origin}/sample/login.html`,
  },
});
assert.ok(
  success.some((m) => m.type === 'observation'),
  success.find((m) => m.type === 'error')?.message,
);
const observation = success.find((m) => m.type === 'observation');
assert.ok(!observation.text.includes('demo@meridian.app'));
assert.ok(!observation.elements.some((e) => e.type === 'password'));
const complete = success.find((m) => m.type === 'complete');
assert.ok(complete);
assert.ok((await stat(complete.video)).size > 1000);
const failed = await capture({
  url: `${origin}/sample/`,
  directory,
  demo: true,
  credentials: {
    username: 'demo@meridian.app',
    password: 'wrong-password',
    login_url: `${origin}/sample/login.html`,
  },
});
assert.ok(failed.some((m) => m.type === 'error' && m.message.includes('Login did not complete')));
assert.ok(!failed.some((m) => m.type === 'observation'));
const privateTarget = await capture({ url: 'http://169.254.169.254/', directory, demo: false });
assert.ok(privateTarget.some((m) => m.type === 'error' && m.message.includes('Private network')));
// Force Playwright's fill() error path, whose call log normally echoes its input.
const fixture = createServer((_, response) => {
  response.setHeader('Content-Type', 'text/html');
  response.end('<input type="email"><input type="password" disabled><button>Sign in</button>');
});
await new Promise((resolveListening) => fixture.listen(0, '127.0.0.1', resolveListening));
try {
  const address = fixture.address();
  const failedFill = await capture({
    url: `http://127.0.0.1:${address.port}/`,
    directory,
    demo: true,
    credentials: { username: 'canary@example.test', password: 'private-canary-password' },
  });
  assert.ok(failedFill.some((m) => m.type === 'error'));
  const output = JSON.stringify(failedFill);
  assert.ok(!output.includes('private-canary-password'));
  assert.ok(!output.includes('canary@example.test'));
} finally {
  await new Promise((resolveClosed) => fixture.close(resolveClosed));
}
console.log(
  'PASS: demo login, session transfer, recording starts after login, incorrect credentials, private network rejection, and secret redaction in browser error logs.',
);
