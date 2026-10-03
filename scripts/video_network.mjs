import { lookup } from 'node:dns/promises';
import { BlockList, isIP } from 'node:net';

const blocked = new BlockList();
for (const [base, bits] of [
  ['0.0.0.0', 8],
  ['10.0.0.0', 8],
  ['127.0.0.0', 8],
  ['169.254.0.0', 16],
  ['172.16.0.0', 12],
  ['192.168.0.0', 16],
  ['100.64.0.0', 10],
  ['192.0.0.0', 24],
  ['192.0.2.0', 24],
  ['198.18.0.0', 15],
  ['198.51.100.0', 24],
  ['203.0.113.0', 24],
  ['224.0.0.0', 4],
  ['240.0.0.0', 4],
])
  blocked.addSubnet(base, bits, 'ipv4');
// BlockList already maps IPv4 subnets to IPv6 internally. Blocking the entire
// ::ffff:0:0/96 range would accidentally deny every ordinary public IPv4 address.
for (const [base, bits] of [
  ['::', 128],
  ['::1', 128],
  ['fc00::', 7],
  ['fe80::', 10],
  ['ff00::', 8],
  ['2001:db8::', 32],
])
  blocked.addSubnet(base, bits, 'ipv6');

export function createURLValidator(allowedLocalOrigin = null, resolver = lookup) {
  const hostCache = new Map();
  async function validate(raw) {
    const url = new URL(raw);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
      throw new Error('Unsupported URL.');
    if (allowedLocalOrigin === url.origin) return;
    if (url.port && !['80', '443'].includes(url.port))
      throw new Error('Use a deployed app on a standard HTTP port.');
    const hostname = url.hostname.replace(/^\[|\]$/g, '');
    const addresses = isIP(hostname)
      ? [{ address: hostname, family: isIP(hostname) }]
      : await resolver(hostname, { all: true });
    if (
      !addresses.length ||
      addresses.some((a) => blocked.check(a.address, a.family === 6 ? 'ipv6' : 'ipv4'))
    )
      throw new Error('Private network access is blocked.');
    const preferred = addresses.find((a) => a.family === 4) || addresses[0];
    hostCache.set(hostname, preferred.address);
  }
  return { validate, hostCache };
}
