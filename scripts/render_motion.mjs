// Render only fixed, reviewed compositions. No model-generated executable code or remote assets.
import { bundle } from '@remotion/bundler';
import { openBrowser, selectComposition, renderMedia, renderStill } from '@remotion/renderer';
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { readFile, mkdir, readdir, rm, rename, stat } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { resolve, dirname, join } from 'node:path';

const manifest = JSON.parse(await readFile(process.argv[2], 'utf8'));
const folder = dirname(resolve(process.argv[2]));
const root = resolve(import.meta.dirname, '..');
const hash = createHash('sha256');
for (const name of (await readdir(join(root, 'src/video'))).sort())
  hash.update(await readFile(join(root, 'src/video', name)));
hash.update(await readFile(join(root, 'package-lock.json')));
const bundleKey = hash.digest('hex').slice(0, 16);
const cache = join(
  process.env.CUTROOM_DATA_DIR || join(root, '.cutroom'),
  'motion-bundles',
  bundleKey,
);
try {
  await stat(join(cache, 'index.html'));
} catch {
  const staging = `${cache}-${randomUUID()}`;
  await mkdir(dirname(cache), { recursive: true });
  try {
    await bundle({
      entryPoint: join(root, 'src/video/index.tsx'),
      outDir: staging,
      publicDir: null,
      enableCaching: false,
    });
    try {
      await rename(staging, cache);
    } catch (error) {
      if (!['ENOTEMPTY', 'EEXIST'].includes(error.code)) throw error;
    }
  } finally {
    await rm(staging, { recursive: true, force: true });
  }
}

const token = randomUUID();
const assets = new Map();
for (const job of manifest.jobs) {
  for (const name of [job.product, job.footage, ...job.details].filter(Boolean)) {
    if (!/^(motion-product|motion-detail|motion-footage)-[\d-]+\.(png|mp4)$/.test(name))
      throw Error('Invalid motion asset');
    assets.set(`/${token}/${name}`, join(folder, name));
  }
}
const server = createServer(async (req, res) => {
  const path = assets.get(req.url);
  if (!path) {
    res.writeHead(404).end();
    return;
  }
  try {
    const { size } = await stat(path);
    const range = req.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
    const start = range ? Number(range[1]) : 0;
    const end = range && range[2] ? Math.min(size - 1, Number(range[2])) : size - 1;
    if (start > end || start >= size) {
      res.writeHead(416).end();
      return;
    }
    res.writeHead(range ? 206 : 200, {
      'Content-Type': path.endsWith('.png') ? 'image/png' : 'video/mp4',
      'Content-Length': end - start + 1,
      'Accept-Ranges': 'bytes',
      ...(range ? { 'Content-Range': `bytes ${start}-${end}/${size}` } : {}),
    });
    createReadStream(path, { start, end }).pipe(res);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const origin = `http://127.0.0.1:${server.address().port}/${token}/`;
let browser;
try {
  browser = await openBrowser('chrome', {
    browserExecutable: chromium.executablePath(),
    logLevel: 'error',
  });
  for (const job of manifest.jobs) {
    const digest = createHash('sha256').update(bundleKey).update(JSON.stringify(job));
    for (const name of [job.product, job.footage, ...job.details].filter(Boolean))
      digest.update(await readFile(join(folder, name)));
    const signature = digest.digest('hex');
    const signaturePath = join(folder, `motion-${job.index}.sha256`);
    try {
      if ((await readFile(signaturePath, 'utf8')) === signature) {
        await stat(join(folder, `motion-${job.index}.mp4`));
        await stat(join(folder, `edit-${job.index}.jpg`));
        console.log(JSON.stringify({ reused: job.index }));
        continue;
      }
    } catch {
      /* First render or missing artifact. */
    }
    const props = {
      ...job,
      product: job.product ? origin + job.product : '',
      details: job.details.map((a) => origin + a),
      footage: job.footage ? origin + job.footage : undefined,
    };
    const composition = await selectComposition({
      serveUrl: cache,
      id: 'LaunchShot',
      inputProps: props,
      puppeteerInstance: browser,
      logLevel: 'error',
    });
    await renderMedia({
      composition,
      serveUrl: cache,
      inputProps: props,
      outputLocation: join(folder, `motion-${job.index}.mp4`),
      codec: 'h264',
      crf: 18,
      concurrency: 2,
      puppeteerInstance: browser,
      logLevel: 'error',
      muted: true,
      x264Preset: 'veryfast',
    });
    await renderStill({
      composition,
      serveUrl: cache,
      inputProps: props,
      output: join(folder, `edit-${job.index}.jpg`),
      frame: Math.min(job.frames - 1, Math.round(job.frames * 0.35)),
      imageFormat: 'jpeg',
      puppeteerInstance: browser,
      logLevel: 'error',
    });
    console.log(JSON.stringify({ rendered: job.index }));
    await (await import('node:fs/promises')).writeFile(signaturePath, signature);
  }
} finally {
  await browser?.close({ silent: true });
  server.closeAllConnections();
  await new Promise((done) => server.close(done));
}
