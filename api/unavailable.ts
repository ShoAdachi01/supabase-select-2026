import type { IncomingMessage, ServerResponse } from 'node:http';

export default function handler(_request: IncomingMessage, response: ServerResponse) {
  response.statusCode = 503;
  response.setHeader('Content-Type', 'application/json');
  response.setHeader('Cache-Control', 'no-store');
  response.end(
    JSON.stringify({ detail: 'The video service is not connected yet. Please try again later.' }),
  );
}
