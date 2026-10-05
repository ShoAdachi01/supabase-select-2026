// Capture only directed takes. Browser-frame timestamps and interaction events share one clock.
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

export async function createDirectedCapture(page, directory) {
  const session = await page.context().newCDPSession(page);
  await mkdir(join(directory, 'capture-frames'), { recursive: true });
  let active = false,
    frames = [],
    count = 0,
    position = 0,
    bytes = 0;
  let writing = Promise.resolve(),
    failure,
    firstFrame;
  const manifest = [];
  session.on('Page.screencastFrame', (event) => {
    void session.send('Page.screencastFrameAck', { sessionId: event.sessionId }).catch(() => {});
    if (!active || failure) return;
    const buffer = Buffer.from(event.data, 'base64');
    bytes += buffer.length;
    if (++count > 12000 || bytes > 350 * 1024 * 1024) {
      failure = new Error(
        'The directed recording exceeded its capture budget. Try fewer features.',
      );
      firstFrame?.();
      return;
    }
    const name = `capture-frames/${String(count).padStart(6, '0')}.jpg`;
    frames.push({ name, time: event.metadata.timestamp });
    writing = writing
      .then(() => writeFile(join(directory, name), buffer))
      .catch((e) => {
        failure = e;
      });
    firstFrame?.();
  });
  return {
    async begin() {
      frames = [];
      active = true;
      const ready = new Promise((done) => {
        firstFrame = done;
      });
      await session.send('Page.startScreencast', {
        format: 'jpeg',
        quality: 90,
        maxWidth: 1920,
        maxHeight: 1080,
        everyNthFrame: 1,
      });
      let timer;
      try {
        await Promise.race([
          ready,
          new Promise((_, reject) => {
            timer = setTimeout(
              () => reject(new Error('The browser did not produce a video frame.')),
              10000,
            );
          }),
        ]);
      } finally {
        clearTimeout(timer);
        firstFrame = undefined;
      }
      if (failure) throw failure;
      return position;
    },
    time() {
      return position + Math.max(0, Date.now() / 1000 - frames[0].time);
    },
    async end() {
      const end = Date.now() / 1000;
      await session.send('Page.stopScreencast');
      active = false;
      await writing;
      if (failure) throw failure;
      const start = frames[0].time;
      for (let i = 0; i < frames.length; i++) {
        const next = frames[i + 1]?.time ?? end;
        manifest.push({ name: frames[i].name, duration: Math.max(0.001, next - frames[i].time) });
      }
      position += manifest.slice(-frames.length).reduce((sum, f) => sum + f.duration, 0);
      if (!Number.isFinite(start) || end - start > 60)
        throw new Error('Invalid directed take timing.');
      return position;
    },
    async finish() {
      await writeFile(join(directory, 'capture.json'), JSON.stringify(manifest));
      await session.detach();
    },
  };
}
