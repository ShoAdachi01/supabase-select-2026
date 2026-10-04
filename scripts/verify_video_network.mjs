import assert from 'node:assert/strict';
import { createURLValidator } from './video_network.mjs';

const { validate, hostCache } = createURLValidator();
for (const url of [
  'https://8.8.8.8/',
  'https://[2606:4700:4700::1111]/',
  'https://[::ffff:8.8.8.8]/',
])
  await validate(url);
assert.equal(hostCache.get('8.8.8.8'), '8.8.8.8');
for (const url of [
  'http://127.0.0.1/',
  'http://169.254.169.254/',
  'http://10.0.0.1/',
  'http://[::1]/',
  'http://[::ffff:127.0.0.1]/',
  'https://8.8.8.8:9999/',
  'https://user:password@8.8.8.8/',
  'file:///etc/passwd',
])
  await assert.rejects(validate(url));
const mixed = createURLValidator(null, async () => [
  { address: '8.8.8.8', family: 4 },
  { address: '127.0.0.1', family: 4 },
]);
await assert.rejects(mixed.validate('https://example.com/'));
const local = createURLValidator('http://127.0.0.1:8000');
await local.validate('http://127.0.0.1:8000/sample/');
await assert.rejects(local.validate('http://127.0.0.1:9000/'));
console.log(
  'PASS: public IPv4/IPv6/mapped IPv4, private/reserved address rejection, mixed DNS rejection, and exact sample-origin restriction.',
);
