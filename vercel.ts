// Keep browser capture and rendering on the persistent worker. Vercel serves the studio.
const configuredOrigin = process.env.CUTROOM_WORKER_ORIGIN?.trim();
let worker: string | undefined;
if (configuredOrigin) {
  const url = new URL(configuredOrigin);
  if (
    url.protocol !== 'https:' ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash ||
    ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  ) {
    throw new Error('CUTROOM_WORKER_ORIGIN must be a public HTTPS origin without a path.');
  }
  worker = url.origin;
}

export const config = {
  framework: 'vite',
  installCommand: 'npm ci',
  buildCommand: 'npm run build',
  outputDirectory: 'dist',
  rewrites: [
    ...['/api/:path*', '/mcp', '/media/:path*'].map((source) => ({
      source,
      destination: worker ? `${worker}${source}` : '/api/unavailable',
    })),
    { source: '/((?!api/|media/|mcp(?:/|$)).*)', destination: '/index.html' },
  ],
};
